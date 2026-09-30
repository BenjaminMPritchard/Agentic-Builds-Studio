# Codex-Principal run checklist
1. Read the task packet and work products. Proceed on authorised A work. For B, verify human-only approval of the current `plan` revision; otherwise request it and wait. Queue HUMAN actions.
2. Build (or review) in your worktree with a commit per step and targeted tests. e2e only through `studio-e2e`, only when the packet says so.
3. `make check` and your security checklist. Open the PR, run `studio-record-pr` (never merge); a review goes on the PR and the task.
4. Hand off with evidence and 2–3 process notes. Set `in_review`.
