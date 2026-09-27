# Builder run checklist
1. Read the packet and work products. Proceed on authorised A work. For B, verify human-only approval of the current `plan` revision; otherwise request it and wait. Queue HUMAN actions.
2. Build in the worktree. Small commits. Trailer `Studio-Agent: <your name>` (keep Paperclip's co-author trailer).
3. `make check` green, then `/code-review medium` in a fresh session; fix blocking findings.
4. Open the PR with the template; link the GitHub issue. Never merge.
5. Hand off: evidence, what to look at, 2–3 process notes. Set `in_review`.
