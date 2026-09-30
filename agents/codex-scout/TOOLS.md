# Codex-Scout tools
- Paperclip API and the `paperclip` skill: read the task, write the `evidence` document, comment, reassign.
- `bin/guard` runs on every shell command and patch (a managed Codex hook); if it blocks you, do not work around it: say so in the task.
- Working directory: the task's project worktree, or `/srv/studio/work/codex-scout`. For the studio repo run `studio-checkout BenjaminMPritchard/Agentic-Builds-Studio` there; for a client site repo add `--read`.
- `GH_TOKEN_SITE_READ` is a read-only token for client site repositories: `GH_TOKEN=$GH_TOKEN_SITE_READ gh ...` for reading.
- You report; you do not change files, commit, push, or write to GitHub.
- Paperclip task actions: `studio-task comment|status|handback|doc <issue id> ...` (uses this run's key; run `studio-task` for usage). Finish every task with `studio-task handback <issue id> "<one-line summary>"`.
