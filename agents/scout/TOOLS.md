# Scout tools
- Paperclip API and the `paperclip` skill (added automatically): read the task, write the `evidence` document, comment, reassign.
- `bin/guard` runs on every Bash call; if it blocks you, do not work around it: say so in the task.
- Working directory: the task's project worktree, or `/srv/studio/work/scout`. For the studio repo run `studio-checkout BenjaminMPritchard/Agentic-Builds-Studio` there; for a client site repo add `--read`.
- `GH_TOKEN_SITE_READ` is a read-only token for client site repositories: `GH_TOKEN=$GH_TOKEN_SITE_READ gh ...` for reading issues and PRs.
- No Edit/Write tools, no commits or pushes, no GitHub writes (settings file `claude/scout.json`).
