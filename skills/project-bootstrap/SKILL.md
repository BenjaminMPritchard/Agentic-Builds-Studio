---
name: project-bootstrap
description: Use only when starting a new website project in the Studio. Don't use for work on an existing project.
---
# Bootstrapping a project

1. Choose the site type (A brochure, B content/CMS, C commerce, D web app). Cheapest stack that meets the requirements wins.
2. Copy `templates/project.yaml` to the site repo as `.studio/project.yaml` (a small PR; the file is protected, so list it in allowed-paths). Fill only values you can read from the repo.
3. Create `projects/<slug>/` in the studio repo (journal, metrics, lessons).
4. Set up the kit: CLAUDE.md template, Makefile targets (`setup`, `dev`, `check`, `e2e`), CI, per-worktree database name, e2e lock, PR template, branch protection (a human does the last one).
5. Open the question register issue; send the questionnaire through the Liaison.
6. Create phase issues from `templates/phases.md` for the site type; propose a budget to the Board.
7. Add a Paperclip project with workspace `git_repo`, `setupCommand: /srv/studio/bin/worktree-setup`, `cleanupCommand: /srv/studio/bin/worktree-cleanup`, test/sandbox secrets only.
