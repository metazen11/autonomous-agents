---
name: capture
description: "Capture an operator request as a well-formed item in the project's canonical tracker (todo.json / GitHub / Asana) and mirror it as a ready task locally, so nothing is dropped during a barrage. Invokes the tasker specialist."
argument-hint: "[for <project>:] <request text>"
user-invocable: true
---

# /capture — request capture buffer

Runs the `tasker` specialist to turn a request into a durable, well-formed tracker
item plus a local mirror task, without the active session stopping its current
work. Front door of the capture buffer; `aa_auditor` is the back door that closes
the item once acceptance criteria are verified.

## Usage

- **`/capture <text>`** — capture the text against the **current project**, routed
  to whatever tracker that project declares in `.autonomous.json`.
- **`/capture for <project>: <text>`** — capture against a named project.

## auto-capture (default)

The session auto-invokes the `tasker` for any barraged request that implies a code
change — the operator does not need to type `/capture`. Pure questions are answered
inline and not filed. `/capture` is only needed to force-file something the
heuristic would otherwise skip.

## Invocation

Dispatch the `tasker` specialist (host-specific: Claude `Agent(subagent_type:
"tasker")`, Codex/Anvil subagent, etc.), passing `request`, `project` (default:
current), and optional `priority`/`lane`.

**Branch on `filed` before reading any other field** (matching the tasker's
`## Output` contract):

- **`{"filed": false, "reason": "..."}`** — the request was a pure question. Answer
  it inline; do NOT file anything and do NOT emit a TodoWrite item.
- **`{"filed": true, "tracker", "ref", "title", "url"}`** — surface a one-line
  confirmation to the operator and mirror a `#<ref> <title>` item into the live
  TodoWrite list. Note `url` is `null` when `tracker` is `todo_json` (no external
  item exists — the local task itself is canonical); render the ref instead.

This skill is the inline counterpart of the `tasker` specialist, matching the
`/reconcile` ↔ `reconciler` pattern.
