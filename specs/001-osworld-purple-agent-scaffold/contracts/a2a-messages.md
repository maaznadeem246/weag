# Contract: A2A Message Format

**Phase 1 output for**: `001-osworld-purple-agent-scaffold`  
**Date**: 2026-04-03  
**Protocol**: A2A (Agent-to-Agent) v0.3.x — `a2a-sdk>=0.3.20`  
**Contract owner**: OSWorld Green Agent (`ghcr.io/rdi-foundation/osworld-green:latest`)

This contract is **fixed by the green agent** — the purple agent MUST conform to it exactly.
Any deviation causes evaluation failure.

---

## Incoming: Green → Purple (per evaluation step)

The green agent calls the purple agent's A2A task endpoint with a `Message` containing
the following parts in order:

### Part 1 — TextPart (instruction)

```json
{
  "type": "text",
  "text": "Open LibreOffice Calc and create a bar chart from the data in column A."
}
```

- Always present.
- Contains the full task instruction for this step.
- May be repeated identically across steps (green agent resends the goal each step).

### Part 2 — DataPart (env_config)

```json
{
  "type": "data",
  "data": {
    "env_config": {
      "action_space": "pyautogui",
      "observation_type": "screenshot"
    }
  }
}
```

- Always present.
- `action_space` is always `"pyautogui"` for this green agent.
- `observation_type` can be `"screenshot"`, `"a11y_tree"`, or `"screenshot_a11y_tree"`.

### Part 3 — FilePart (screenshot)

```json
{
  "type": "file",
  "file": {
    "name": "screenshot.png",
    "mime_type": "image/png",
    "bytes": "<base64-encoded PNG>"
  }
}
```

- Present when `observation_type` includes `"screenshot"` (default).
- `bytes` is standard base64-encoded raw PNG data of the full Ubuntu desktop (1280×800 typically).
- May be absent if the green agent has not yet taken a screenshot (rare edge case).

### Part 4 — DataPart (accessibility_tree) — optional

```json
{
  "type": "data",
  "data": {
    "accessibility_tree": "Name\tRole\tPosition\n..."
  }
}
```

- Present when `observation_type` includes `"a11y_tree"`.
- Absent in default `"screenshot"` mode.
- Value is a tab-separated text representation of the desktop accessibility tree.

### Part 5 — DataPart (terminal) — optional

```json
{
  "type": "data",
  "data": {
    "terminal": "$ ls -la\ntotal 24\ndrwxr-xr-x ..."
  }
}
```

- Present when the green agent has terminal output to share.
- Absent in most steps.

---

## Outgoing: Purple → Green (per evaluation step)

The purple agent MUST respond with a `Message` containing exactly two parts:

### Part 1 — TextPart (reasoning)

```json
{
  "type": "text",
  "text": "I can see the LibreOffice Calc window is open. Column A contains 5 numeric values. I will select the data and insert a bar chart using the Insert menu."
}
```

- MUST be present.
- Contains the LLM's chain-of-thought reasoning for this step.
- On LLM failure: use a descriptive error message (e.g., `"LLM call failed: rate limit exceeded"`).

### Part 2 — DataPart (actions)

```json
{
  "type": "data",
  "data": {
    "actions": [
      "pyautogui.click(150, 200)",
      "import time; time.sleep(0.5)",
      "pyautogui.hotkey('ctrl', 'a')"
    ]
  }
}
```

- MUST be present.
- `actions` MUST be a non-empty list of strings.
- Each string is either a valid pyautogui Python expression or one of the special values below.
- The green agent executes these sequentially on the Ubuntu VM.

### Special action values

| Value | Meaning |
|-------|---------|
| `"WAIT"` | Pause — green agent waits and sends the next observation without executing anything |
| `"DONE"` | Task completed successfully — green agent ends the evaluation and scores it |
| `"FAIL"` | Task cannot be completed — green agent ends the evaluation with score 0 |

### Error response (on LLM failure)

```json
[
  {"type": "text", "text": "LLM call failed: <error description>"},
  {"type": "data", "data": {"actions": ["FAIL"]}}
]
```

---

## Agent Card Contract

The purple agent's discovery endpoint (`GET /`) MUST return an agent card conforming to:

```json
{
  "name": "OSWorld Purple Agent",
  "version": "0.1.0",
  "description": "A2A purple agent for OSWorld computer use benchmark",
  "url": "http://<host>:<port>/",
  "capabilities": {
    "streaming": false,
    "pushNotifications": false
  },
  "skills": [
    {
      "id": "osworld_task",
      "name": "OSWorld Task Execution",
      "description": "Executes computer use tasks on Ubuntu desktop via pyautogui actions",
      "inputModes": ["text", "file", "data"],
      "outputModes": ["text", "data"]
    }
  ]
}
```

- `skills[0].id` MUST be `"osworld_task"` — this is the identifier the green agent searches for.
- `inputModes` and `outputModes` MUST include at least `"text"` and `"data"`.

---

## Error Handling Matrix

| Situation | Purple Agent Response |
|-----------|-----------------------|
| No screenshot part in message | Log WARNING, proceed with text-only context |
| LLM timeout or API error | Return `{"actions": ["FAIL"]}` + error text part |
| Empty LLM response | Return `{"actions": ["FAIL"]}` + `"Empty LLM response"` text |
| Unparseable LLM output | Return `{"actions": ["FAIL"]}` + `"Could not parse actions"` text |
| Unknown `context_id` | Create new empty session, proceed normally |
| Missing `LLM_PROVIDER` env var | Default to `litellm`; log INFO |
| Invalid `LLM_PROVIDER` value | Default to `litellm`; log WARNING |
| Missing required API key | Log ERROR, exit with code 1 at startup |
