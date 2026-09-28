# Paperclip contract checked for Milestone 1

Evidence sources: running `/api/health` reports `2026.916.1`; read-only live
requests returned HTTP 200 on 2026-09-28; locally cached package version
matches. Package source inspected includes
`@paperclipai/server/dist/routes/issues.js`,
`services/issue-thread-interactions.js`, `services/issues.js`, and the package
CLI schemas. No private live response was copied into this public repository.

| Contract | Package evidence | Studio use |
|---|---|---|
| Company issue list | Live bare array, 11 issues on first page; `limit=2` returned two. Two issues have nonempty `blockedBy` arrays of issue summaries. | `Paperclip.list_issues` walks offset pages and rejects changed shapes |
| Issue detail | Live object includes `blockedBy`, `blocks` and `workProducts` | Do not assume list rows contain `blockedByIssueIds` |
| Dependencies | Paperclip services manage blockers and readiness | Clerk no longer changes blocked issues to todo |
| Issue documents | `latestRevisionId` on document read; update supports `baseRevisionId` | A B approval targets the exact latest `plan` revision |
| Interactions | Live bare array. One existing plan confirmation was accepted by an agent under `anyone`; its target revision matched the current plan. This proves old acceptance cannot be treated as B human approval. | Plan handback requires accepted `human_only`, human resolver and matching revision |
| Run list | Bare array; `limit` applies | Client rejects changed shapes |
| Provider failure/recovery | Server exposes structured provider quota and native recovery | To be integrated in Milestone 3; no Studio retry owner added here |

The live company has nine existing agents and two projects; the Mothers project
records the expected GitHub repository. The package routes show offset limits
and separate list/detail shapes.
Tests in `tests/fakes.py` mirror these package-derived shapes and include a
205-issue pagination case, stale approval and agent-resolved approval cases.
They are contract regression tests, not live-service proof.

Before runtime deployment, verify the run-list response, native recovery
configuration and any contract requiring a write probe. Use a disposable test
issue for write probes. Sanitise fixtures before adding them here.
