# Agentic Studio

Agentic Studio uses Paperclip for organisational work and GitHub for engineering
history, review and merge evidence. This repository contains the Studio's agent
instructions, policy, deterministic integrations, tests and operating procedures.

The intended path is human objective → Paperclip task → suitable worker in an
isolated workspace → verification → risk-appropriate review → GitHub PR →
authorised delivery → curated learning. Paperclip owns task status, dependencies,
confirmations and workspaces. Studio code must not create parallel owners for them.

## Authority

`CONSTITUTION.md` is the highest local rule and can only be amended by Benjamin.
The implementation policy in `skills/task-packet/SKILL.md` separates authority
(A, B, HUMAN) from engineering risk (low, medium, high). Routine authorised A
work proceeds without human confirmation. B requires human-only acceptance of
the exact `plan` document revision. Consequential HUMAN actions wait for direct
human authority. PRs require human merge unless `policy/autonomous-merge.json`
authorises the project, in which case only the deterministic `bin/merge-gate` may
merge. No project is authorised; Studio and Mothers PRs require human merge. See
`playbook/merge-gate.md` for the gate's conditions and what enabling a project needs.

## Source and runtime

GitHub `BenjaminMPritchard/Agentic-Builds-Studio` and this checkout's `main`
are the engineering source of truth. `/srv/studio/company` is a deployment
checkout, not a source branch. See `playbook/source-runtime.md` for the recorded
2026-09-27 inspection, protected runtime state, and deployment gate. Source
edits are not active until a deliberate, authorised deployment verifies the
running commit.

The running Paperclip health endpoint reports `2026.916.1`. Read-only live
calls verified the company, projects, agents and issue/confirmation shapes.
`playbook/paperclip-contract.md` records the sanitised contract evidence and
the remaining checks.

## Repository map

| Path | Purpose |
|---|---|
| `agents/`, `skills/` | Role instructions and reusable practices |
| `package/` | Paperclip configuration reference, with placeholders |
| `lib/paperclip.py` | Small Paperclip API client |
| `lib/clerk.py`, `lib/pacer.py` | Existing deterministic integration and capacity code |
| `lib/worker.py`, `qwen/` | Bounded local Worker harness |
| `bin/guard` | Claude hook defence in depth, not a security boundary |
| `playbook/`, `projects/`, `upgrades/` | Procedures, curated memory and proposals |
| `deploy/` | Service template; changes require deliberate activation |

## Tests

```bash
python -W ignore -m unittest discover -s tests -t .
```

The test suite uses local fake Paperclip and Ollama HTTP servers, so it needs
loopback socket access. A passing fake suite does not verify the running
Paperclip instance. Keep the risky Qwen jobs disabled until their semantic
checks and end-to-end handback are proven.
