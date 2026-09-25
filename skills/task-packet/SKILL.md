---
name: task-packet
description: Use when creating, splitting or routing a task, or reading a project's .studio/project.yaml. Don't use when just doing an assigned task.
---
# Task packets

Write every task as a packet (template: `templates/task-packet.md`): goal, GitHub issue link
(`GitHub: owner/repo#N`, the Clerk reads this line), tier, allowed and protected paths,
depends-on, done-when, evidence required, e2e yes/no, budget hint.

**Risk tiers**
- **Tier B:** money, stock, fulfilment, login, personal data, security, hardening, customer or
  legal wording, anything in the project's `risk_paths`, any migration on those. Principal builds
  or reviews; the Board confirms the plan; Board merges.
- **Tier A:** everything else. Director approves the plan; Builder's `/code-review` or Principal
  as fits.

**Routing**
| Work | To |
|---|---|
| polling, gates, CI, tests, lint, diff scope, cost | scripts (Clerk) |
| summaries, exact-quote extraction, sorting, failure classification, dedupe | Worker (`qwen-job`) |
| client drafts, question register | Liaison |
| features, design builds, SEO, docs, tests | Builder |
| Tier B, reviews, second-line debugging | Principal |
| site type, plan, acceptance, disputes | Director |

Execution policies: Tier B = review by Principal then Director, `maxReviewRounds: 2`; Tier A =
Director only. Read `.studio/project.yaml` in the site repo for check/e2e commands, risk paths,
isolation, registers and gates. Don't invent values that file already has.
