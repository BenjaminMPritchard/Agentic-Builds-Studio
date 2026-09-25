---
name: verify-handoff
description: Use before opening a PR and when finishing a task. Don't use while still exploring.
---
# Verify and hand off

1. Targeted tests first, then `make check` in your worktree (lint, migrations check, types, tests). Paste the result summary.
2. e2e only if the packet says so or checkout paths changed, through `/srv/studio/bin/studio-e2e`. Never two at once (the lock enforces it).
3. UI changes: attach screenshots.
4. Open the PR from the site's template. Body: what and why, `Closes #<issue>`, evidence, risks, what the reviewer should look at.
5. Hand-off comment: what changed, evidence, open questions, and 2–3 **process notes**. Set the task `in_review`. Do not merge.
6. Red checks: fix and re-run. After 3 red runs on the same task, stop and hand to the Principal.
