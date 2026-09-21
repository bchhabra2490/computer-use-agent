# Jev fast computer-use loop

Optional TypeSafe **Jev** policy that can take a few high-confidence desktop
actions before the existing vision computer-use agent continues. Jev is **not**
a planner replacement: the generative agent still owns planning, free-form text,
ambiguity, recovery, and completion verification.

## How it fits

```text
planner / agent session
  -> structured AX snapshot (local)
  -> legal grounded candidates (local)
  -> Jev Choice/Noul request (TypeSafe; no screenshots)
  -> confidence + margin + safety + freshness gates (local)
  -> one local action
  -> meaningful-state-change wait (bounded poll)
  -> repeat or fallback to vision agent
```

Jev is **not** polled at 60 Hz. A 150 ms decision budget is ~6.7 decisions/s;
this loop calls Jev only after a cycle completes (snapshot → decision → optional
action → state wait). Local AX observation may poll more often while waiting for
a revision change; provider calls stay event-driven after meaningful UI changes.

## Modes

| Mode | Env | Behavior |
|------|-----|----------|
| Off | `JEV_FAST_LOOP=0` | Existing agent unchanged (tool may still be on) |
| Shadow | `JEV_FAST_LOOP=1` `JEV_SHADOW_MODE=1` | Evaluate/log only; vision executes |
| Active | `JEV_FAST_LOOP=1` `JEV_SHADOW_MODE=0` | Execute supported high-confidence actions |
| Agent tool | `JEV_CHOOSE_TOOL=1` (default) | Vision agent calls `jev_choose` mid-task |

## Agent tool: `jev_choose`

Inspired by
[jev-ax-pilot](https://github.com/dabit3/jev-experiments/tree/main/jev-ax-pilot):
code owns text candidates and arithmetic facts; Jev only selects; destructive
judgement is a Noul gated in code; pseudo-actions (`ask_user`, `use_vision`,
`stuck`, `done`) sit beside real options.

| `source` | Behavior |
|----------|----------|
| `agent` | You pass options; pseudos are auto-injected |
| `ax` | Frontmost Accessibility tree → ≤60 grounded candidates + pseudos |

Returns Choice + complete/stuck/`is_destructive` probabilities and a
recommendation (`proceed`, `ask_user`, `use_vision`, `verify_then_done`).
**Never clicks** — the vision agent executes. Independent of `JEV_FAST_LOOP`
(needs `TYPESAFE_API_KEY` + `typesafe-sdk`).

## Safety

- Candidates are generated locally; unknown Jev IDs are rejected.
- No screenshots are sent to Jev by this loop.
- Structured accessibility state is sent when enabled; **secure-field values are
  redacted** and never intentionally transmitted.
- Credential- or secret-bearing **goals/subgoals** bypass Jev entirely (privacy
  gate) so raw secrets are never sent to TypeSafe; the vision agent continues.
- Confidence / margin / stuck gates and stale-element freshness are local.
- Destructive or externally consequential actions still require the existing
  confirmation path (`NEEDS_CONFIRMATION` → `confirm_fn` → re-gate). Jev
  confidence never overrides safety policy.
- Global scroll targets a **safe interior point** (never display corners / fail-safe).
- Same-label controls with distinct frames are retained with disambiguated
  descriptions; nested/overlapping duplicates still collapse.
- Choice criteria are hard-capped (`JEV_CHOICE_MAX_OPTIONS=255`, configured
  candidates ≤ 253, default 220).
- Completion (`done` / high complete Noul) always returns to the vision agent for
  independent verification — never silent success.

## Supported initial actions

Native AX press/click, focus, Enter / Escape / Tab, bounded scroll, wait,
conservative deterministic typing, escalate. Dragging, canvas/WebGL, file upload,
secure fields, unlabeled/ambiguous controls, and multi-window ambiguity fall back.

## Fallback triggers (non-exhaustive)

Low confidence, narrow margin, stuck probability, empty AX, unsupported action,
unresolved confirmation, repeated freshness failure, two no-effect actions,
repeated unchanged action, consecutive provider failures, step budget, free-form
text that cannot be grounded, completion needing verification.

## Configuration

See `.env.example`. Keys: `TYPESAFE_API_KEY`, `JEV_FAST_LOOP`, `JEV_SHADOW_MODE`,
`JEV_CHOOSE_TOOL`, `JEV_MODEL`, `JEV_MIN_CONFIDENCE`, `JEV_MIN_MARGIN`,
`JEV_COMPLETE_THRESHOLD`, `JEV_STUCK_THRESHOLD`, `JEV_MAX_STEPS`,
`JEV_MAX_CANDIDATES`, `JEV_REQUEST_TIMEOUT_SECONDS`,
`JEV_MAX_CONSECUTIVE_FAILURES`.

Set the API key **locally** (`.env` or shell). Never paste it into chat or commit it.

Optional dependency: `pip install 'typesafe-sdk>=0.7.0,<1'` (also in
`requirements-optional.txt`). Missing SDK/key falls back cleanly.

## Observability

TaskLog events: `jev_decision`, `jev_step`, `jev_session`. Latency marks:
`jev_decision`, `jev_first_action`, `jev_session_complete` (and
`first_computer_action` when Jev acts first). Payloads are scrubbed of API keys
and secret-looking fields. Compare per-step: snapshot_ms, candidate_gen_ms,
jev_latency_ms, gate_ms, freshness_ms, execute_ms, wait_ms, step_total_ms, plus
session rates (fallback / no-effect / repeated / safety).

## Rollout

Shadow:

```bash
export TYPESAFE_API_KEY="..."   # set locally; do not commit
export JEV_FAST_LOOP=1
export JEV_SHADOW_MODE=1
```

Active:

```bash
export TYPESAFE_API_KEY="..."
export JEV_FAST_LOOP=1
export JEV_SHADOW_MODE=0
```

Rollback:

```bash
export JEV_FAST_LOOP=0
```

## Code map

| Module | Role |
|--------|------|
| `jev/config.py` | Env parsing |
| `jev/models.py` | Typed snapshot / action / decision |
| `accessibility.py` | `capture_ui_snapshot` |
| `jev/actions.py` | Candidates, gates, execute adapter |
| `jev/client.py` | Lazy TypeSafe wrapper |
| `jev/shadow.py` | Shadow evaluation |
| `jev/loop.py` | Active one-action loop + agent handoff |
| `jev/diagnostics.py` | Safe log scrub + session stats |
| `agent.py` | Narrow hook after recipes |
