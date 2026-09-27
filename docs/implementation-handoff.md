# Agentic Studio productionisation handoff

Updated: 2026-09-28. Status: **Milestone 1 source checkpoint; not activated or complete**.
This document is for the next implementation agent. Stop after Milestone 1 is
reviewable; do not begin Milestone 2 in this handoff session.

## Original objective and references

Productionise the existing AI-native Studio into a reliable small digital
company: human → Paperclip → specialised workforce → isolated engineering →
verification → risk-appropriate review → GitHub → authorised delivery →
institutional learning. Optimise for reliable authorised work, graceful
provider degradation and human control. Preserve the existing Paperclip
company, identities, history, worktree model, Guard, bounded Qwen Worker,
Recorder, Architect, Claude, native Codex capability, Tailscale previews,
backups, Mothers work and credentials.

The controlling detailed specification is Benjamin's **“Agentic Studio —
Productionisation Implementation”** message in the initiating 2026-09-27
session. The preceding **GPT-6 Astra read-only architecture audit** supplied
the baseline and defects reconciled into that specification. Neither full
transcript is checked into this repository; preserve access to both session
records and ask Benjamin for them if the next agent cannot see them. Do not
replace them with a large `CLAUDE.md`. The `pre-astra-studio-audit` tag points
to source baseline `7f462eb08d572924befb74a925de82a580daee27`, not to the
audit text. `playbook/source-runtime.md`, `playbook/paperclip-contract.md`,
and `upgrades/m1-constitution-proposal.md` hold this session's concise
evidence and proposed policy amendment.

## Five-milestone structure

1. **Make Studio truthful:** reconcile source/runtime, policy, Paperclip
   contracts and tests. **Current milestone; partial source implementation.**
2. **Enforce boundaries:** authenticated human/agent authority, confinement,
   credentials, Docker access, merge gate, safe cleanup, DRAIN/STOP.
3. **Repair deterministic infrastructure:** Clerk receipts/dry-run/cursors,
   provider capacity, workspace safety and real Qwen handback.
4. **Introduce multi-provider execution:** native Codex Principal with Astra,
   economical Codex Builder-1, preserve Claude roles, prove fallback and
   capacity admission.
5. **Organisational acceptance:** disposable client A/B/provider/review/
   concurrency/Worker/capacity/emergency/operations/deploy/memory trials,
   then Mothers takeover inventory only. Mothers implementation requires
   separate human authorisation.

## IMPLEMENTED in source, not activated

- `lib/paperclip.py`: reads bare-array issue, agent, run and interaction
  responses; issue list uses offset pages and asks for blocker projection;
  adds issue-detail read and rejects unexpected shapes.
- `lib/clerk.py`: stops duplicating Paperclip's dependency transition. B plan
  handback now requires the current `plan` revision, an accepted
  `human_only` confirmation and a human resolver. Historical agent-accepted
  confirmations no longer satisfy that gate.
- `bin/guard`: denies autonomous merges for now and checks that an email
  confirmation is human-only, human-resolved and bound to the current
  `email-draft` revision. Guard remains defence in depth.
- `skills/task-packet/SKILL.md`, `skills/studio-house-rules/SKILL.md`,
  `templates/task-packet.md`: separate A/B/HUMAN authority from engineering
  risk; B targets an exact plan revision; task packets name work products.
- `agents/director/{AGENTS,HEARTBEAT}.md`,
  `agents/builder-{1,2}/{AGENTS,HEARTBEAT}.md`,
  `agents/principal/{AGENTS,HEARTBEAT}.md`,
  `agents/liaison/AGENTS.md`, `skills/client-comms/SKILL.md`: remove universal
  plan confirmation and conditional Director merge instructions; require
  human-only exact-revision approval where applicable. These are source
  instructions only; live Paperclip agents still have their existing config.
- `package/payloads/company.json`, `package/README.md`: remove obsolete
  Tier A/Tier B universal review payload and label historical creation
  payloads as reference, not a live export.
- `README.md`: replaces stale onboarding and auto-deploy claims with the
  current source/runtime and authority picture.
- `tests/fakes.py`, `tests/test_clerk.py`, `tests/test_guard.py`: fake live
  bare-array and document-revision shapes, pagination, stale/agent approval
  regression checks, and human-merge guard expectations.
- `playbook/source-runtime.md`: source/runtime evidence and deliberate
  deployment gate. `playbook/paperclip-contract.md`: sanitised package and
  live API contract evidence. `upgrades/m1-constitution-proposal.md`: exact
  amendment proposal, **not** a Constitution edit.
- This file: durable continuation state.

## VERIFIED evidence

- Initial source: clean `main` at `7f462eb08d572924befb74a925de82a580daee27`,
  remote `git@github.com:BenjaminMPritchard/Agentic-Builds-Studio.git`.
- Runtime checkout: `/srv/studio/company` at
  `4a914cf5d4bdc319968312c115e91aa789125f7e`; its obsolete `origin`
  points to `/home/benjamin/studio/studio-company`. Runtime HEAD is an
  ancestor of source HEAD. Runtime has no tracked edits and has untracked,
  unread `.claude/settings.local.json`. Across tracked files, 29 shared
  files differ and source has two additional files.
- Paperclip service is active; `/api/health` returned status `ok`, version
  `2026.916.1`, `deploymentMode=local_trusted`. System unit still invokes
  unpinned `npx --yes paperclipai run` as `paperclip`.
- Read-only API: one company, **Agentic Builds Studio**, ID
  `bcf0f336-0c20-4194-9e21-fac517979ba0`; two projects: Studio
  infrastructure `ba0da149-a497-4a85-82c5-1d6e0729cdde` and Mothers
  `c2b582f3-d52e-47fd-812c-e29d6b805d3f`; Mothers project points to
  `https://github.com/Agentic-Builds-Studio/Mothers-Carpentry-Webpage.git`.
  Nine original agents exist. Principal and Liaison were paused at inspection;
  preserve human pause state.
- Live issue list is a bare array (11 items on first page); nonempty
  `blockedBy` contains issue summary objects. Issue detail has `blockedBy`,
  `blocks` and `workProducts`. Live interactions/documents are bare arrays
  and document metadata includes `latestRevisionId`. One historical plan
  confirmation was accepted by an agent with effective policy `anyone` even
  though it targets the current revision; it must not count as B approval.
- Full suite before the final Guard/email and documentation edits:
  `python -W ignore -m unittest discover -s tests -t .` → **52 tests OK**.
  Later full-suite rerun was interrupted before a result and is **not** a pass.
- After final code edits: focused
  `python -W ignore -m unittest tests.test_guard tests.test_clerk -q` →
  **32 tests OK**; `python -m unittest tests.test_package -q` →
  **6 tests OK**; `python -m py_compile` for edited Python files and Guard →
  **exit 0**; `git diff --check` → **exit 0**. Focused fake-server tests need
  loopback access outside the restricted sandbox.

## NOT VERIFIED and unresolved work in Milestone 1

- New source code is **not deployed**. The exact Studio code loaded in running
  processes, live agent instruction/config revisions, live run-list response,
  native recovery settings and workspace state need a read-only reconciliation.
- `CONSTITUTION.md` still grants a conditional Director merge exception and
  describes Guard as enforcement. Benjamin-only amendment is prepared in
  `upgrades/m1-constitution-proposal.md`; do not edit it without approval.
- Runtime remote and untracked `.claude/` have not been reconciled. Do not
  reset or overwrite them. Deliberate deployment and service changes require
  approval; no deployment was attempted.
- `lib/clerk.py` still contains historical auto-deploy, weak action receipts,
  branch-prefix PR linkage, merged-PR-means-done behaviour and pacer flaws.
  These are known Milestone 3 repairs. In particular, do not enable source
  Clerk live reconciliation or `STUDIO_AUTODEPLOY=1` based on this checkpoint.
- `bin/guard` is a hook, not a host/Board security boundary. Paperclip's
  `local_trusted` mode remains a Milestone 2 authority risk. Do not expose
  Paperclip through Funnel or alter authentication without an owner recovery
  plan and approval.
- The new client rejects changed response shapes; verify against live run and
  agent list endpoints before deployment. The current tests use fakes, not an
  end-to-end Paperclip write probe.
- Package and agent payloads still contain historical Claude-only model
  strings; model migration belongs to Milestone 4. Do not change models now.
- Review Git diff for source-only policy contradictions not yet removed.
  Milestone 1 is complete only when Constitution, instructions, running
  config and Paperclip contracts agree, tests pass, and evidence is recorded.

## Architectural decisions and discoveries

Paperclip owns dependencies and status transitions. GitHub owns branches,
PRs, checks, review and merge history. Studio stores policy and deterministic
integrations. B authority requires `resolverPolicy=human_only` on the exact
document revision; engineering risk is separate from authority. Until a
future project has an explicitly authorised exact-head merge gate, Studio and
Mothers merge stays human. Provider/model changes were intentionally deferred.

Live Paperclip is available through a read-only localhost call when shell
execution has the required sandbox exception. Its version matches the cached
package used for contract inspection. The original runtime remote is wrong,
but runtime HEAD is an ancestor of source HEAD; drift can be planned without
discarding history. The accepted `anyone` plan confirmation is concrete
evidence of the old authority defect. Preserve this fact without copying raw
private task content into the public repository.

## Protected assets and approvals

Do not alter Mothers, its branches/PRs/database/preview, Paperclip company or
agent identities/history, runtime `.claude/`, credentials, logs, data,
human pauses, recovery state, backups or Tailscale mappings during this
checkpoint. Do not start Milestone 2. Do not change `CONSTITUTION.md`,
Paperclip auth, groups, system services, firewall/network policy, GitHub
rulesets, autonomous merge, credentials, Tailscale mappings or material
runtime behaviour without the explicit human approvals in the specification.
Benjamin's Constitution approval is still required. Runtime activation is a
separate approval after tested commit and rollback plan.

## Git state and baseline commands

Source began on clean `main` at `7f462eb08d572924befb74a925de82a580daee27`.
The tested implementation checkpoint is commit
`6e3e312` on branch `feat/studio-m1-truthful-source`. This handoff document
is the follow-up documentation commit at branch `HEAD`; use `git rev-parse
HEAD` for its exact SHA. No PR or push was made, and no pre-existing unrelated
source changes were present at session start. The intended final working tree
is clean; confirm with `git status --short --branch` before continuing.

```bash
cd '/home/benjamin/Agentic Builds Studio'
git status --short --branch
git rev-parse HEAD
git diff --check
python -m unittest tests.test_package -q
python -W ignore -m unittest tests.test_guard tests.test_clerk -q
git -c safe.directory=/srv/studio/company -C /srv/studio/company status --short --branch
git -c safe.directory=/srv/studio/company -C /srv/studio/company rev-parse HEAD
curl -sS http://127.0.0.1:3100/api/health
```

The focused Guard/Clerk command needs loopback socket permission in a
restricted sandbox. Avoid printing raw API responses in a public log; extract
only metadata needed to verify identity and shape.

**Recommended exact next action:** inspect the final Git diff and focused
test results, then obtain Benjamin's decision on the prepared Constitution
amendment. Complete the remaining read-only live contract/config checks and
Milestone 1 review before planning any approved runtime deployment. Do not
begin Milestone 2 until the Milestone 1 ledger has a defensible verified exit.
