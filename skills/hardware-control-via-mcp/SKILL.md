---
name: hardware-control-via-mcp
description: >-
  Control physical hardware devices through MCP tools only: discover the right hardware server/tools, resolve target device names, confirm risky actions, execute via mcp_call, and verify outcome without desktop-UI fallbacks.
---

## When to use

Use this skill for user requests that act on physical devices, including:

- lights / switches / plugs
- AC / thermostat / fans
- TVs / speakers / media boxes
- locks / garage / doors
- sensors or scenes/automations

## Rules

1. Use MCP (`mcp_call`) for hardware actions. Do not automate vendor websites or apps if MCP can do the action.
2. Never call raw MQTT topics/payloads directly from the LLM path.
3. For potentially risky actions (unlock/open door, disable alarm, power off unknown device), ask for explicit confirmation if the request is ambiguous.
4. Prefer idempotent reads/checks before writes when practical (fetch state, then change).

## Steps

1. **Identify intent**
   - Parse action (`turn_on`, `turn_off`, `set`, `open`, `close`, `lock`, `unlock`, etc.).
   - Parse target device/area from user language ("bedroom lamp", "living room AC").

2. **Check MCP options first**
   - Use available MCP catalog context.
   - If the right hardware server/tool is not obvious, use `mcp_call` discovery/list tools path on the connected hardware server.

3. **Resolve target device**
   - Find the best matching entity by name/alias/room.
   - If multiple plausible matches exist, call `ask_user` with one short clarification.

4. **Confirm if needed**
   - Confirm only for risky/destructive/irreversible actions or when target ambiguity remains.

5. **Execute action via MCP**
   - Call the specific hardware MCP tool with minimally required arguments.
   - Avoid extra side effects.

6. **Verify and report**
   - Read back state when possible (e.g., `is_on`, setpoint, lock state).
   - Give a short spoken status summary with target + resulting state.
   - If execution fails, report exact MCP error and ask one focused follow-up question.

## Fallback behavior

- If no connected hardware MCP server can perform the request, tell the user clearly and ask whether to proceed with a manual desktop flow.
- Do not silently switch to browser/UI automation for hardware control without user approval.
