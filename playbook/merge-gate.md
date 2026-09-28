# Autonomous merge gate

Status (2026-09-28): **implemented in source, not activated, no project authorised.**
Code: `lib/merge_gate.py`, `bin/merge-gate`. Policy: `policy/autonomous-merge.json`
(human-only: Constitution, `CODEOWNERS`, Guard `NEVER_ALLOWED`). Tests:
`tests/test_merge_gate.py`, `tests/test_guard.py`.

Paperclip supplies authority and linkage, GitHub supplies engineering evidence,
and the Studio evaluates them deterministically. A model may *request* a merge
(`merge-gate merge …`); it never decides one. Every decision is appended to
`$STUDIO_DATA/log/merge-gate.jsonl` before any merge, and a failed write
prevents the merge.

## Conditions (all must be proven; anything missing or ambiguous refuses)

| Condition | Evidence |
|---|---|
| Project explicitly authorised | Studio policy entry for the issue's Paperclip `projectId`, `enabled: true`, well-formed; company ID matches |
| Exact repository | Request repo = policy repo = PR base and head repo (no forks) |
| Task authority | Exactly one `**Authority:**` line in the packet, `A` or `B`, and that class allowed by the project policy. A packet that says A while a `plan` document exists refuses |
| B approval | Accepted `request_confirmation`, `effectiveResolverPolicy=human_only`, resolved by a user and not an agent, targeting the **current** `plan` revision |
| No B2 deviation | Approved plan states `**Scope paths:**`; every changed file (and rename source) is inside it; no `b2`, `deviation`, `needs-human`, `needs-board` or `do-not-merge` label |
| No unresolved confirmation | No interaction on the issue is `pending` |
| Paperclip state | Issue `in_review`; all `blockedBy` done; any review policy `completed` with an `approved` last decision |
| Exact PR and branch | Exactly one live GitHub `pull_request` work product on the issue, with metadata and URL agreeing and naming this repo and PR; its `headRef` equals the PR branch; branch is `agent/<identifier>-<slug>` |
| Exact head SHA | Request SHA (40 hex) = PR head = a GitHub `commit` work product on the issue (same repo and branch) |
| Checks on that head | Every check run on the SHA completed and passing; every commit status `success`; each policy `required_checks` name passed on that SHA |
| Independent review | Latest decision per reviewer: no `CHANGES_REQUESTED`; enough `APPROVED` reviews **on the exact SHA** from `trusted_reviewers` who are not the PR author. At least one for B or for engineering risk other than `low` (a missing or unknown risk counts as high) |
| Protected paths | Always refused: `CONSTITUTION.md`, `CLAUDE.md`, `.claude/**`, `docs/PLAN.md`, `.studio/project.yaml`, `.studio-allowed-paths`, `.github/**`, `CODEOWNERS`, `policy/**`; plus the project's `protected_paths`; plus, if set, anything outside `mergeable_paths` |
| Complete file list | Paginated file count equals GitHub's `changed_files` |
| Mergeable | GitHub `mergeable=true`, `mergeable_state=clean`; open, not draft |
| Stale head / race | Evidence is read immediately before merging; `gh pr merge --match-head-commit <sha>` makes GitHub reject a head that moved. No `--admin`, no `--auto` |

Guard blocks `gh pr merge` and raw API merges (`…/pulls/N/merge`) by agents. That
is defence in depth. The gate becomes the *only* path only when agents' GitHub
credentials cannot merge (see below).

## Project policy entry (template; do not add without Benjamin's authorisation)

```json
"<paperclip project id>": {
  "enabled": true, "repo": "Owner/Name", "base_branch": "main", "merge_method": "squash",
  "authority_classes": ["A"], "required_checks": ["<check name>"], "required_approvals": 1,
  "trusted_reviewers": ["<github login>"], "protected_paths": [], "mergeable_paths": [],
  "authorised_by": "Benjamin", "authorised_on": "YYYY-MM-DD"
}
```

## What enabling a project requires

Common to both projects:

1. **Benjamin's explicit authorisation**, recorded by a human-merged PR that adds the entry above.
2. **`local_trusted` gap closed.** The Constitution makes this a precondition, because host access can currently act as the Board and accept human-only confirmations (Milestone 2).
3. **A server-side merge restriction.** GitHub branch rules must prevent agent tokens from merging, with a separate merge credential used only by the gate process. Until this exists the gate is procedural (Milestone 2 credential work).
4. **An independent reviewer identity.** This means a GitHub login distinct from the authoring agents, listed in `trusted_reviewers`. Whether agents currently share one GitHub identity is **unverified** (tokens are redacted). If they do, agent reviews cannot be evidenced on GitHub.
5. **Work products recorded in practice.** A `pull_request` and a head `commit` work product must be recorded per issue. Today no live issue has any.
6. **Runtime activation** of this source (a separate approval).

**Agentic Builds Studio** (`BenjaminMPritchard/Agentic-Builds-Studio`, project `ba0da149-a497-4a85-82c5-1d6e0729cdde`):

- A merge here changes Studio enforcement code once it is deployed. `STUDIO_AUTODEPLOY` must be verified off, or removed, first; otherwise an autonomous merge becomes an autonomous runtime activation.
- Use `mergeable_paths` as an allow-list (for example `docs/**`, `tests/**`, `templates/**`). Protect `bin/**`, `lib/**`, `claude/**`, `agents/**`, `skills/**` and `package/**`.
- The required check name is **unverified**. `gh` is not authenticated in the implementation session, so branch protection could not be read.

**Mothers Carpentry** (`Agentic-Builds-Studio/Mothers-Carpentry-Webpage`, project `c2b582f3-d52e-47fd-812c-e29d6b805d3f`):

- Unverified: CI check names, branch protection, and whether a merge to `main` deploys to production. If it does, autonomous merge is autonomous production deployment and needs its own decision.
- Money, stock, personal-data and migration paths should be `protected_paths`, or be kept to B work with Principal review.
- Nothing about Mothers was changed.

## Known limits

- **Authority classification.** The Director classifies A/B/HUMAN in the task packet. The gate checks the stated class and its evidence; it cannot judge whether the classification was right.
- **Linkage is recorded by agents.** Work products and branch names are recorded by agents. The gate requires them to agree with GitHub, but it does not scan other issues for a PR linked twice.
- **Semantic deviation.** Deviation inside the declared scope paths is left to independent review.
