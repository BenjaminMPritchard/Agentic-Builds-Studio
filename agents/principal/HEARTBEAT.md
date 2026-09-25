# Principal run checklist
1. Read the task packet, the GitHub issue and the `plan` document. No approved plan: write it, raise `request_confirmation`, stop.
2. Build in your worktree with a commit per step and targeted tests. e2e only through `studio-e2e`, only when the packet says so.
3. `make check`, then `/security-review` and `/code-review high`. Open the PR (never merge).
4. Hand off with evidence and 2–3 process notes. Set `in_review`.
