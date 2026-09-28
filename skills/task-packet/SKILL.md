---
name: task-packet
description: Use when creating, splitting or routing a task, or reading a project's .studio/project.yaml. Don't use when just doing an assigned task.
---
# Task packets

Write every task as a packet (template: `templates/task-packet.md`): goal, explicit work-product
links, authority, engineering risk, allowed and protected paths, dependencies, done-when,
evidence required, e2e yes/no, budget hint.

**Authority and engineering risk are separate.**
- **A:** already authorised low-consequence work. State the objective and acceptance criteria;
  execute with proportionate verification. No human confirmation for routine A work.
- **B:** implementation within an exact human-approved plan revision. Create a Paperclip
  `request_confirmation` targeting that `plan` document revision, with
  `resolverPolicy: human_only`. Agents cannot accept it. A material change in scope,
  spending, supplier, production target, data handling, security, review or customer policy
  requires a new revision and approval.
- **HUMAN:** consequential action requiring direct human authority, including significant
  financial or legal commitments, DNS, production secrets, destructive business-data work,
  material security changes and irreversible external actions. Queue until authorised.

Rate engineering risk low, medium or high independently. High risk calls for a qualified
worker, stronger checks and independent review; it does not itself require human approval.

**Routing**
| Work | To |
|---|---|
| polling, gates, CI, tests, lint, diff scope, cost | scripts (Clerk) |
| summaries, exact-quote extraction, sorting, failure classification, dedupe | Worker (`qwen-job`) |
| client drafts, question register | Liaison |
| features, design builds, SEO, docs, tests | Builder |
| high-risk engineering, qualified reviews, second-line debugging | Principal |
| site type, plan, acceptance, disputes | Director |

Use Paperclip's review policy with an independent qualified reviewer when engineering risk
requires it. The author must not independently accept consequential implementation. Read
`.studio/project.yaml` for project-specific check and isolation rules. Merge authority comes only
from `policy/autonomous-merge.json` in the Studio repo, through `bin/merge-gate`; Studio and Mothers
are not authorised, so their PRs require human merge. A B plan must state `**Scope paths:**`
(comma-separated globs); files outside it make the work B2.

## Paperclip gotchas (verified on a live instance)

- **Set blockers after creating an issue, never in the create call.** Paperclip silently ignores
  `blockedByIssueIds` (and `executionPolicy`) when an issue is created; they only take effect on an update
  (`PATCH /api/issues/{id}`). Create all the issues first, then PATCH each one's blockers and review
  policy, then read one back to check `blockedByIssueIds` is not empty. The Clerk can only unblock what is
  really blocked.
- Record the GitHub repository, issue, branch, PR and exact head SHA as explicit work products.
  A branch prefix is not a proof of linkage.
- Paperclip owns dependency and issue status transitions. Do not mirror its state machine in Clerk.
