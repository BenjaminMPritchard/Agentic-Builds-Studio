# Codex-Builder tools
- Paperclip API and the `paperclip` skill. Studio house rules override its "never ask a human" rule; see `CONSTITUTION.md`.
- `bin/guard` runs on every shell command and patch (a managed Codex hook); if it blocks you, do not work around it: comment on the task and ask.
- `gh` and `git push` use a one-hour token from the `abs-agents` GitHub App (push branches, open and comment on PRs and issues; it cannot merge). Never print it.
- Workspace: git worktree per task. Test/sandbox keys only; `SHIPPING_PROVIDER=mock`.
- `studio-checkout`, `studio-record-pr`; skills: house-rules, verify-handoff, qwen-job, routing-table.
- Paperclip task actions: `studio-task comment|status|handback|doc <issue id> ...` (uses this run's key; run `studio-task` for usage). Finish every task with `studio-task handback <issue id> "<one-line summary>"`.
