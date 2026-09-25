---
name: qwen-job
description: Use before delegating checkable text work (summaries, exact-quote extraction, sorting, classification) to the Worker. Don't use for code, security, customer or legal wording, decisions, reviews, or inputs over about 8k tokens.
---
# Delegating to the Worker (Qwen)

Create a Paperclip task assigned to the Worker with a `job` document:
`{"job": "<name>", "version": 1, "input": {...}, "requester": "<your agent id>"}`.
The Worker writes a `result` document and sets the task `done`, or hands it back with errors.

**Jobs enabled** are listed in `qwen/enabled.json` (a job needs an 80% golden pass rate):
summarise-comment, extract-followups, classify-failure, triage-message, extract-questionnaire,
todo-owner-questions, dedupe-note, extract-lessons, normalise-piece, thread-digest, doc-distill.
`changelog-digest` after launch. `mechanical-edit` is off.

**Rules**
- Output is JSON only, schema-checked; quotes and numbers must appear in the input.
- No check, no Qwen. Anything failing a check becomes `needs_human`: do it yourself, don't re-send the same input.
- One retry is built in. Trust `status: ok` results for routing and summaries, not for decisions.
- Inputs over about 8k tokens are refused; split them.
