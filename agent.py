"""
Personal computer-use agent: drives your real desktop via OpenAI's `computer` tool.

Usage:
    export OPENAI_API_KEY=sk-...
    python agent.py "Open Notes and write today's date at the top"
    python agent.py "..." --auto          # skip the per-turn confirmation prompt
    python agent.py "..." --max-steps 15  # default is 25

    # Voice routing (orchestrator → may call this agent via start_task):
    python orchestrator.py
    python agent.py --voice --auto

SAFETY NOTES (read before running):
  - This controls your actual mouse and keyboard. Keep your hands off the mouse/
    keyboard while it runs, and don't leave it unattended on a task that touches
    anything sensitive (payments, deleting files, sending messages) without --auto
    turned OFF, i.e. confirming every step.
  - Slam your mouse to any screen corner at any time to trigger pyautogui's
    fail-safe and abort immediately.
  - Ctrl+C in the terminal also stops the loop between turns.
  - Grant your terminal app "Screen Recording", "Accessibility", and (for voice)
    "Microphone" permissions in macOS System Settings > Privacy & Security.
"""

from envfile import load_dotenv

load_dotenv()

import argparse
import base64
import json
import os
import re
import sys
import threading
import uuid

from openai import OpenAI

from actions import DesktopController, list_monitors
from accessibility import read_ui_text
from app_status import (
    consume_mark_done,
    is_mark_done_utterance,
    register_agent_process,
    remove_agent,
    unregister_agent_process,
    upsert_agent,
)
from evaluator import (
    EVAL_EVERY,
    EVAL_MODEL,
    coach_agent,
    resolve_agent_model,
    screenshot_b64_from_computer_output,
)
from context import assemble_context
from memory import maybe_extract_run_memories
from mcp_client import start_mcp, stop_mcp
from session import Session, bind_session, get_session
from skills import (
    discover_skills,
    format_skill_catalog,
    get_skill,
    list_skill_files,
    read_skill_file,
    write_skill,
)
from status_tray import ensure_tray_running, stop_tray
from stt import ask_user, voice_confirm
from task_log import TaskLog
from terminal import run_command
from tools_registry import SHARED_TOOL_NAMES, agent_tools, run_shared_tool
from traces import maybe_save_trace, try_replay
from tts import speak, speak_later

# Manual override only — leave unset to let the difficulty router choose.
MODEL_OVERRIDE = (os.environ.get("AGENT_MODEL") or "").strip() or None
# Used when routing is disabled / skill review fallback.
MODEL = MODEL_OVERRIDE or os.environ.get("AGENT_MODEL_HARD", "gpt-5.6")


class TaskMarkedDone(Exception):
    """Raised when the model or user ends the computer-use run."""

    def __init__(self, summary: str = "Task complete."):
        self.summary = (summary or "Task complete.").strip()
        super().__init__(self.summary)


def confirm(actions: list, *, client: OpenAI | None = None, voice: bool = False) -> bool:
    print("\nProposed actions:")
    for a in actions:
        print(f"  - {a}")

    if voice and client is not None:
        labels = []
        for a in actions:
            if hasattr(a, "type"):
                labels.append(str(a.type))
            elif isinstance(a, dict):
                labels.append(str(a.get("type", a)))
            else:
                labels.append(str(a))
        summary = ", ".join(labels[:8])
        if len(labels) > 8:
            summary += f", and {len(labels) - 8} more"
        speak(
            client,
            f"I want to run {len(labels)} action{'s' if len(labels) != 1 else ''}: "
            f"{summary}. Say yes to run them, no to skip, or quit to stop.",
        )
        decision = voice_confirm(
            client,
            "Should I run these actions?",
            allow_quit=True,
        )
        if decision == "quit":
            print("Stopped by user.")
            speak(client, "Stopping.")
            sys.exit(0)
        return decision == "yes"

    reply = input("Run these? [y/N/q]: ").strip().lower()
    if reply == "q":
        print("Stopped by user.")
        sys.exit(0)
    return reply == "y"


def _action_summary(actions) -> list:
    out = []
    for a in actions:
        if hasattr(a, "model_dump"):
            out.append(a.model_dump())
        elif isinstance(a, dict):
            out.append(a)
        else:
            out.append(str(a))
    return out


def _print_and_log_messages(response, log: TaskLog) -> list[str]:
    texts: list[str] = []
    for item in response.output:
        if item.type == "message":
            for part in item.content:
                if getattr(part, "type", None) == "output_text":
                    print(f"\n[agent] {part.text}")
                    log.record("message", part.text[:200], {"text": part.text})
                    texts.append(part.text)
    return texts


def _handle_ask_user(client: OpenAI, call, log: TaskLog, ask_user_bridge=None) -> dict:
    args = json.loads(call.arguments or "{}")
    question = (args.get("question") or "").strip()
    if not question:
        answer = "Error: ask_user was called without a question."
    elif ask_user_bridge is not None:
        # Route through orchestrator so the main thread owns TTS + mic.
        answer = ask_user_bridge.ask(question)
    else:
        answer = ask_user(client, question)
    log.record(
        "ask_user",
        f"Q: {question[:120]}",
        {"question": question, "answer": answer},
    )
    return {
        "type": "function_call_output",
        "call_id": call.call_id,
        "output": answer,
    }


def _handle_list_skills(call, log: TaskLog) -> dict:
    skills = discover_skills()
    if not skills:
        output = "No skills found under skills/."
    else:
        lines = [f"{s.name}: {s.description}" for s in skills]
        output = "\n".join(lines)
    print(f"[skills] listed {len(skills)} skill(s)")
    log.record("list_skills", f"{len(skills)} skill(s)", {"skills": [s.name for s in skills]})
    return {
        "type": "function_call_output",
        "call_id": call.call_id,
        "output": output,
    }


def _handle_read_skill(call, log: TaskLog) -> dict:
    args = json.loads(call.arguments or "{}")
    name = (args.get("name") or "").strip()
    rel_file = args.get("file")
    if isinstance(rel_file, str):
        rel_file = rel_file.strip() or None
    else:
        rel_file = None

    if not name:
        output = "Error: read_skill requires a skill name."
    elif rel_file:
        try:
            text = read_skill_file(name, rel_file)
            output = f"# {name} / {rel_file}\n\n{text}"
            print(f"[skills] read {name}/{rel_file}")
            log.record("read_skill", f"{name}/{rel_file}", {"name": name, "file": rel_file})
        except (FileNotFoundError, PermissionError) as e:
            extras = list_skill_files(name)
            hint = f" Available files: {', '.join(extras)}" if extras else ""
            output = f"Error: {e}.{hint}"
            print(f"[skills] failed to read {name}/{rel_file}: {e}")
            log.record("read_skill", f"error {name}/{rel_file}", {"error": str(e)})
    else:
        skill = get_skill(name)
        if skill is None:
            available = ", ".join(s.name for s in discover_skills()) or "(none)"
            output = f"Unknown skill {name!r}. Available: {available}"
            print(f"[skills] unknown skill {name!r}")
            log.record("read_skill", f"unknown {name}", {"name": name})
        else:
            extras = list_skill_files(name)
            extra_note = f"\n\nCompanion files (read_skill with file=…): {', '.join(extras)}" if extras else ""
            output = skill.full_text + extra_note
            print(f"[skills] loaded {skill.name}")
            log.record("read_skill", skill.name, {"name": skill.name})

    return {
        "type": "function_call_output",
        "call_id": call.call_id,
        "output": output,
    }


def _handle_read_ui_text(call, log: TaskLog) -> dict:
    args = json.loads(call.arguments or "{}")
    app = args.get("app")
    if isinstance(app, str):
        app = app.strip() or None
    else:
        app = None
    output = read_ui_text(app=app)
    summary_app = app or "frontmost"
    print(f"[ax] read_ui_text ({summary_app}) → {len(output)} chars")
    log.record(
        "read_ui_text",
        f"{summary_app}: {len(output)} chars",
        {"app": summary_app, "chars": len(output), "preview": output[:500]},
    )
    return {
        "type": "function_call_output",
        "call_id": call.call_id,
        "output": output,
    }


def _confirm_terminal(
    command: str,
    *,
    client: OpenAI | None = None,
    voice: bool = False,
) -> bool:
    print(f"\nProposed terminal command:\n  $ {command}")
    if voice and client is not None:
        speak(
            client,
            f"I want to run this terminal command: {command[:180]}. "
            "Say yes to run it, no to skip, or quit to stop.",
        )
        decision = voice_confirm(
            client,
            "Should I run this command?",
            allow_quit=True,
        )
        if decision == "quit":
            print("Stopped by user.")
            speak(client, "Stopping.")
            sys.exit(0)
        return decision == "yes"

    reply = input("Run this command? [y/N/q]: ").strip().lower()
    if reply == "q":
        print("Stopped by user.")
        sys.exit(0)
    return reply == "y"


def _handle_run_terminal(
    call,
    log: TaskLog,
    *,
    auto: bool,
    client: OpenAI | None = None,
    voice: bool = False,
) -> dict:
    args = json.loads(call.arguments or "{}")
    command = (args.get("command") or "").strip()
    cwd = args.get("cwd")
    if isinstance(cwd, str):
        cwd = cwd.strip() or None
    else:
        cwd = None
    timeout_raw = args.get("timeout_seconds")
    timeout_seconds: float | None
    if timeout_raw is None:
        timeout_seconds = None
    else:
        try:
            timeout_seconds = float(timeout_raw)
        except (TypeError, ValueError):
            timeout_seconds = None

    if not command:
        output = "Error: run_terminal requires a command."
    elif not auto and not _confirm_terminal(command, client=client, voice=voice):
        output = "User declined to run this command."
        print("[terminal] skipped by user")
        log.record(
            "run_terminal_skipped",
            command[:120],
            {"command": command, "cwd": cwd},
        )
    else:
        print(f"[terminal] $ {command}" + (f"  (cwd={cwd})" if cwd else ""))
        output = run_command(
            command,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
        )
        # Keep console readable; full text goes to the model + log.
        preview = output if len(output) <= 1200 else output[:1200] + "\n…"
        print(preview)
        log.record(
            "run_terminal",
            command[:120],
            {
                "command": command,
                "cwd": cwd,
                "timeout_seconds": timeout_seconds,
                "output_chars": len(output),
                "preview": output[:1000],
            },
        )

    return {
        "type": "function_call_output",
        "call_id": call.call_id,
        "output": output,
    }


def _handle_function_call(
    client: OpenAI,
    call,
    log: TaskLog,
    ask_user_bridge=None,
    *,
    auto: bool = False,
    voice: bool = False,
) -> dict:
    if call.name == "ask_user":
        return _handle_ask_user(client, call, log, ask_user_bridge=ask_user_bridge)
    if call.name == "list_skills":
        return _handle_list_skills(call, log)
    if call.name == "read_skill":
        return _handle_read_skill(call, log)
    if call.name == "read_ui_text":
        return _handle_read_ui_text(call, log)
    if call.name == "run_terminal":
        return _handle_run_terminal(call, log, auto=auto, client=client, voice=voice)
    if call.name in SHARED_TOOL_NAMES:
        args = json.loads(call.arguments or "{}")
        output = run_shared_tool(call.name, args, client=client)
        preview = output.replace("\n", " ")[:160]
        print(f"[{call.name}] {preview}")
        log.record(call.name, preview, {"args": args, "output": output[:2000]})
        return {
            "type": "function_call_output",
            "call_id": call.call_id,
            "output": output,
        }
    if call.name == "mark_done":
        args = json.loads(call.arguments or "{}")
        summary = (args.get("summary") or "Task complete.").strip()
        print(f"[agent] mark_done: {summary[:160]}")
        log.record("mark_done", summary[:200], {"summary": summary})
        raise TaskMarkedDone(summary)
    log.record("unsupported_tool", call.name, {"name": call.name})
    return {
        "type": "function_call_output",
        "call_id": call.call_id,
        "output": f"Unsupported tool: {call.name}",
    }


def _handle_computer_call(
    desktop: DesktopController,
    call,
    auto: bool,
    log: TaskLog,
    *,
    client: OpenAI | None = None,
    voice: bool = False,
) -> dict | None:
    actions = _action_summary(call.actions)
    if not auto and not confirm(call.actions, client=client, voice=voice):
        log.record("computer_skipped", "user declined actions", {"actions": actions})
        print("Skipped this batch. Ending run.")
        return None

    log.record("computer_actions", f"{len(actions)} action(s)", {"actions": actions})
    desktop.run_actions(call.actions)
    screenshot_bytes = desktop.capture_screenshot()
    screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
    log.record(
        "screenshot",
        f"{len(screenshot_bytes)} bytes",
        {"bytes": len(screenshot_bytes)},
    )
    return {
        "type": "computer_call_output",
        "call_id": call.call_id,
        "output": {
            "type": "computer_screenshot",
            "image_url": f"data:image/png;base64,{screenshot_b64}",
            "detail": "original",
        },
    }


def _extract_json_object(text: str) -> dict | None:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def maybe_create_skill(
    client: OpenAI,
    log: TaskLog,
    *,
    voice: bool = False,
    background: bool = True,
) -> None:
    """After a successful run, propose a reusable skill. Default: daemon thread.

    Does not block the agent loop or the last TTS. Pass ``background=False``
    to run inline (tests / non-voice). Interactive save prompts are skipped
    in the background path.
    """
    if background:
        def _work() -> None:
            try:
                _maybe_create_skill_impl(client, log, voice=voice, prompt_user=False)
            except Exception as e:
                print(f"[skills] review failed: {e}", flush=True)

        threading.Thread(target=_work, name="skill-review", daemon=True).start()
        print("[skills] reviewing run for a new skill in background…", flush=True)
        return
    _maybe_create_skill_impl(client, log, voice=voice, prompt_user=True)


def _maybe_create_skill_impl(
    client: OpenAI,
    log: TaskLog,
    *,
    voice: bool = False,
    prompt_user: bool = True,
) -> None:
    """After a successful run, propose a reusable skill and save it automatically."""
    existing = format_skill_catalog()
    prompt = f"""You review a completed desktop computer-use task and decide whether to
save a new reusable skill for future runs.

Create a skill ONLY when:
- The workflow is reusable for similar future tasks
- It is not already covered well by an existing skill
- Steps are concrete enough to follow on a Mac desktop

Do NOT create a skill for one-off tasks, trivial single clicks, or when an
existing skill already covers it.
Never write steps that sleep for a song/video duration, use macOS `say`,
or wait in run_terminal until media finishes.

Existing skills:
{existing}

Original task:
{log.task}

Steps taken:
{log.steps_for_prompt()}

Respond with JSON only (no markdown fences):
{{
  "create": true or false,
  "reason": "short explanation",
  "name": "lowercase-hyphen-name or null",
  "description": "third-person what+when description or null",
  "body": "markdown instructions with ## Steps and ## Tips, or null"
}}
"""
    print("\n[skills] reviewing run for a new skill…")
    response = client.responses.create(
        model=EVAL_MODEL,
        input=prompt,
    )

    text = ""
    for item in response.output:
        if item.type == "message":
            for part in item.content:
                if getattr(part, "type", None) == "output_text":
                    text += part.text

    proposal = _extract_json_object(text)
    if not proposal:
        print("[skills] could not parse skill proposal; skipping.")
        log.record("skill_proposal", "parse_failed", {"raw": text[:2000]})
        return

    log.record("skill_proposal", proposal.get("reason", ""), proposal)

    if not proposal.get("create"):
        print(f"[skills] no new skill ({proposal.get('reason', 'not needed')})")
        return

    name = proposal.get("name")
    description = proposal.get("description")
    body = proposal.get("body")
    if not (name and description and body):
        print("[skills] proposal missing fields; skipping.")
        return

    if get_skill(name):
        print(f"[skills] {name!r} already exists; skipping create.")
        return

    auto_save = os.environ.get("SKILL_AUTO_SAVE", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    print(f"\nProposed new skill: {name}")
    print(f"  {description}")

    if not auto_save:
        if not prompt_user:
            print("[skills] not saved (SKILL_AUTO_SAVE=0; background review cannot prompt).")
            log.record("skill_create", "skipped_background_no_prompt", {"name": name})
            return
        if voice:
            speak(
                client,
                f"I can save a new skill called {name}. {description} " "Say yes to save it, or no to skip.",
            )
            decision = voice_confirm(client, "Save this skill?")
            approved = decision == "yes"
        else:
            reply = input("Save this skill? [Y/n]: ").strip().lower()
            approved = reply in ("", "y", "yes")
        if not approved:
            print("[skills] not saved.")
            log.record("skill_create", "declined_by_user", {"name": name})
            return

    try:
        path = write_skill(name, description, body)
    except (ValueError, FileExistsError) as e:
        print(f"[skills] failed to write skill: {e}")
        log.record("skill_create", "error", {"error": str(e)})
        return

    print(f"[skills] wrote {path}")
    if voice:
        speak_later(client, f"Saved skill {name}.")
    log.record("skill_create", f"wrote {name}", {"path": str(path)})


def _extract_memories_from_log(_client: OpenAI, log: TaskLog, task: str) -> None:
    transcript = (
        f"User input:\n{task}\n\n"
        f"LLM steps and tool context:\n{log.steps_for_prompt(max_chars=20_000, snippet_chars=2000)}"
    )
    maybe_extract_run_memories(user_input=task, transcript=transcript)


def run(
    task: str,
    auto: bool,
    max_steps: int,
    *,
    voice: bool = False,
    message_inbox=None,
    ask_user_bridge=None,
    status_agent_id: str | None = None,
) -> str:
    """Run the computer-use loop. Returns a status string for the orchestrator.

    If `message_inbox` is provided (ZeroMQ AgentMessageInbox), pending user
    directives are drained at the start of each turn and injected into context.
    If `ask_user_bridge` is provided, ask_user is routed through the orchestrator
    (main-thread TTS/STT) instead of capturing the mic from this worker thread.
    `status_agent_id` ties this run to the menu-bar "In Progress" list.
    """
    client = OpenAI()
    ensure_tray_running()
    standalone = ask_user_bridge is None and message_inbox is None
    own_session = False
    if standalone:
        register_agent_process()
        try:
            start_mcp()
        except BaseException as e:
            print(f"[agent] MCP start error: {e}", flush=True)
        bind_session(Session())
        own_session = True

    desktop = DesktopController()
    log = TaskLog(task)
    agent_id = (status_agent_id or "").strip() or f"agent-{uuid.uuid4().hex[:8]}"
    upsert_agent(
        agent_id,
        task=task,
        kind="computer-agent",
        status="running",
        log_dir=str(log.dir),
    )
    get_session().enter_and_log("agent", f"Starting: {task[:120]}", task=task, log_dir=str(log.dir))

    monitors = list_monitors()
    primary = next((m for m in monitors if m["main"]), monitors[0])
    shot_w, shot_h = primary["native_width"], primary["native_height"]
    if shot_w > desktop.screenshot_max_width:
        ratio = desktop.screenshot_max_width / shot_w
        shot_w = desktop.screenshot_max_width
        shot_h = round(shot_h * ratio)

    bundle = assemble_context(
        monitors=monitors,
        screenshot_size=(shot_w, shot_h),
        include_geometry=True,
    )
    display_ctx = bundle.desktop_block()
    skills = discover_skills()
    skill_catalog = bundle.skills
    memory_catalog = bundle.memories
    mcp_catalog = bundle.mcp
    not_to_do = bundle.not_to_do

    print(f"\nTask: {task}")
    print(display_ctx)
    print(skill_catalog)
    print(memory_catalog)
    if mcp_catalog:
        print(mcp_catalog)
    if not_to_do:
        print(not_to_do)
    log.record(
        "start",
        task,
        {"display": display_ctx, "skills": [s.name for s in skills], "voice": voice},
    )

    def _pending_user_context() -> str | None:
        if message_inbox is None:
            return None
        try:
            pending = message_inbox.drain()
        except Exception as e:
            print(f"[agent] inbox drain failed: {e}", flush=True)
            log.record("zmq_error", str(e), {"error": str(e)})
            return None
        if not pending:
            return None
        if any(is_mark_done_utterance(m) for m in pending):
            raise TaskMarkedDone("User marked the task done.")
        for i, msg in enumerate(pending, 1):
            print(f"[agent] ZeroMQ → context [{i}/{len(pending)}]: {msg!r}", flush=True)
            log.record("zmq_message", msg[:200], {"text": msg, "index": i})
        lines = "\n".join(f"- {m}" for m in pending)
        blob = (
            "IMPORTANT — mid-task user messages received via Jarvis / ZeroMQ "
            "while you were working. Treat these as updated instructions and "
            "adapt immediately (do not ignore):\n"
            f"{lines}"
        )
        print(
            f"[agent] injecting {len(pending)} ZeroMQ message(s) into model context",
            flush=True,
        )
        log.record(
            "zmq_context",
            f"inject {len(pending)} message(s)",
            {"messages": pending, "chars": len(blob)},
        )
        return blob

    def _user_input_item(text: str) -> dict:
        return {
            "role": "user",
            "content": [{"type": "input_text", "text": text}],
        }

    try:
        replayed = try_replay(task, desktop=desktop)
        if replayed:
            log.record("trace_replay", replayed.split("\n", 1)[0], {"result": replayed})
            log.finish("completed", "Replayed saved action trace.")
            if voice:
                speak_later(client, "Done.")
            return replayed

        model = resolve_agent_model(client, task, log)
        print(f"[agent] model={model} eval_every={EVAL_EVERY}")
        if message_inbox is not None:
            print(f"[agent] ZeroMQ inbox connected ({message_inbox.endpoint})")

        response = client.responses.create(
            model=model,
            tools=agent_tools(),
            input=(
                f"{task}\n\n"
                f"Desktop display configuration:\n{display_ctx}\n\n"
                f"{skill_catalog}\n\n"
                f"{memory_catalog}\n\n"
                f"{mcp_catalog}\n\n"
                f"{not_to_do}\n\n"
                "Workflow:\n"
                "1. If a skill matches this task, call read_skill for it (and any "
                "companion files you need) before using the computer tool. For "
                "accounts, names, or app preferences, call read_memory first "
                "(skill read-memory).\n"
                "2. If they ask who you are, what you can do, or about this agent, "
                "call who_am_i then mark_done with a short spoken summary from the "
                "README (do not drive the desktop or read the README aloud).\n"
                "3. If an MCP server can search, fetch, or change the data, call "
                "mcp_call before using the computer tool or scraping with "
                "run_terminal.\n"
                "3b. For physical hardware/device control (lights, switches, TV, "
                "AC, locks, sensors), use hardware MCP via mcp_call. Do not use "
                "desktop UI clicks as a workaround when MCP can do it.\n"
                "3c. Open windows, running apps, and browser tabs are listed in "
                "the occupancy block. Call list_open_apps for a fresh snapshot "
                "(do not scrape the tab bar with the computer tool).\n"
                "4. Follow the skill’s steps; adapt to what you see on screen.\n"
                "5. Use run_terminal for shell/CLI work (files, git, scripts, "
                "path checks) when that is faster than the GUI. Never sleep for "
                "media duration or use macOS say for spoken updates.\n"
                "6. Use the computer tool for UI actions on this real desktop. "
                "If Open windows by display lists the target app on another monitor, "
                "activate or move to that screen — do not hunt only in the primary "
                "screenshot.\n"
                "7. Prefer read_ui_text (Accessibility) to read labels/values/menus "
                "cheaply; use screenshots when AX returns little or for layout/graphics.\n"
                "8. Anything the user will hear (mark_done summary, ask_user, on-screen "
                "status) should sound like a person speaking, not a written report. "
                "Say titles and names (“the Linear checkout issue”, “the AC/DC video”) "
                "instead of raw URLs, slugs, or https links.\n"
                "9. When you need clarification or information only the human knows, "
                "call ask_user instead of guessing — unless read_memory already has it. "
                "save_memory when they state a durable fact. "
                "If they want the current display remembered, call save_screen_memory "
                "(screenshot + description) — do not use the computer tool for that.\n"
                "10. Before each turn, you may receive new user messages that arrived "
                "via ZeroMQ / Jarvis while you were working — follow them immediately.\n"
                "11. You may periodically receive evaluator coaching — treat it as "
                "advisory guidance and adapt.\n"
                "12. When the request is complete and no other action is required, "
                "call mark_done (do not keep using the computer tool)."
            ),
        )

        steps = 0
        last_messages: list[str] = []
        while steps < max_steps:
            if consume_mark_done(agent_id):
                raise TaskMarkedDone("User marked the task done.")
            last_messages = _print_and_log_messages(response, log) or last_messages

            computer_calls = [i for i in response.output if i.type == "computer_call"]
            function_calls = [i for i in response.output if i.type == "function_call"]

            if not computer_calls and not function_calls:
                # If the user sent mid-task guidance as we finished, keep going.
                leftover = _pending_user_context()
                if leftover:
                    print(
                        "[agent] model stopped but ZeroMQ messages pending — continuing",
                        flush=True,
                    )
                    response = client.responses.create(
                        model=model,
                        tools=agent_tools(),
                        previous_response_id=response.id,
                        input=[_user_input_item(leftover)],
                    )
                    continue

                print("\nDone — no further actions.")
                if voice:
                    speak_later(client, "Done.")
                log.finish("completed")
                maybe_create_skill(client, log, voice=voice)
                maybe_save_trace(log, task)
                _extract_memories_from_log(client, log, task)
                summary = "\n".join(last_messages).strip()
                if summary:
                    return f"completed\nResult:\n{summary}"
                return "completed"

            tool_outputs: list[dict] = []
            last_shot_b64: str | None = None

            for call in function_calls:
                tool_outputs.append(
                    _handle_function_call(
                        client,
                        call,
                        log,
                        ask_user_bridge=ask_user_bridge,
                        auto=auto,
                        voice=voice,
                    )
                )

            for call in computer_calls:
                output = _handle_computer_call(desktop, call, auto, log, client=client, voice=voice)
                if output is None:
                    log.finish("aborted", "User skipped a computer action batch.")
                    return "aborted"

                tool_outputs.append(output)
                shot = screenshot_b64_from_computer_output(output)
                if shot:
                    last_shot_b64 = shot

            steps += 1

            # Drain Jarvis / ZeroMQ messages; inject into next model turn.
            next_input: list = list(tool_outputs)
            mid_turn = _pending_user_context()
            if mid_turn:
                next_input.append(_user_input_item(mid_turn))
                print(
                    f"[agent] next API input includes ZeroMQ context " f"(+{len(tool_outputs)} tool output(s))",
                    flush=True,
                )

            # Periodic coach after every EVAL_EVERY computer turns.
            if EVAL_EVERY > 0 and computer_calls and steps % EVAL_EVERY == 0:
                tip = coach_agent(
                    client,
                    task=task,
                    log=log,
                    screenshot_b64=last_shot_b64,
                    step_n=steps,
                )
                if tip:
                    next_input.append(_user_input_item(tip))

            response = client.responses.create(
                model=model,
                tools=agent_tools(),
                previous_response_id=response.id,
                input=next_input,
            )

        print(f"\nStopped: hit max-steps ({max_steps}) without finishing.")
        log.finish("max_steps", f"Hit max-steps ({max_steps}).")
        _extract_memories_from_log(client, log, task)
        summary = "\n".join(last_messages).strip()
        if summary:
            return f"max_steps\nPartial result:\n{summary}"
        return "max_steps"
    except TaskMarkedDone as e:
        print(f"\nDone — {e.summary}")
        if voice:
            speak_later(client, "Done.")
        log.finish("completed", e.summary)
        maybe_create_skill(client, log, voice=voice)
        maybe_save_trace(log, task)
        _extract_memories_from_log(client, log, task)
        return f"completed\nResult:\n{e.summary}"
    except KeyboardInterrupt:
        log.finish("interrupted", "KeyboardInterrupt")
        raise
    except Exception as e:
        log.finish("error", str(e))
        raise
    finally:
        remove_agent(agent_id)
        if standalone:
            unregister_agent_process()
            stop_tray()
            if own_session:
                bind_session(None)
            try:
                stop_mcp()
            except BaseException:
                pass
        if message_inbox is not None:
            try:
                message_inbox.close()
            except Exception:
                pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Personal computer-use agent")
    parser.add_argument(
        "task",
        nargs="?",
        default=None,
        help="Natural-language task (required for direct runs; use orchestrator.py for voice)",
    )
    parser.add_argument(
        "--voice",
        "-v",
        action="store_true",
        help="Launch the voice orchestrator instead",
    )
    parser.add_argument("--auto", action="store_true", help="Skip per-turn confirmation")
    parser.add_argument("--max-steps", type=int, default=25)
    args = parser.parse_args()

    if args.voice or not args.task:
        # Voice UX lives in the orchestrator (routing + tools), not here.
        from orchestrator import main as orch_main

        argv = []
        if args.auto:
            argv.append("--auto")
        if args.max_steps != 25:
            argv.extend(["--max-steps", str(args.max_steps)])
        orch_main(argv)
    else:
        run(args.task, args.auto, args.max_steps, voice=False)
