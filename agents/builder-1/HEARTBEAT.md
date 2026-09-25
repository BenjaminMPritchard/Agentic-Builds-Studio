# Builder run checklist
1. Read the packet, the GitHub issue and any `plan`. No approved plan: write it, raise `request_confirmation`, stop.
2. Build in the worktree. Small commits. Trailer `Studio-Agent: <your name>` (keep Paperclip's co-author trailer).
3. `make check` green, then `/code-review medium` in a fresh session; fix blocking findings.
4. Open the PR with the template; link the GitHub issue. Never merge.
5. Hand off: evidence, what to look at, 2–3 process notes. Set `in_review`.
