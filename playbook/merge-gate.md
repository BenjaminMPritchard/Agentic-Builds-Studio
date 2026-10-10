# Autonomous merge gate

Status (2026-09-30): **Mothers Carpentry authorised by Benjamin** (A and B work; money, stock, personal-data,
settings and migration files stay protected, so PRs touching them wait for a human). The Studio repository is not
authorised; its PRs are merged by Benjamin or, after green CI, by Claude Code with `--admin` (Constitution, 2026-10-01).
Code: `lib/merge_gate.py`, `bin/merge-gate`. Policy: `policy/autonomous-merge.json`
(human-only by the Constitution and Guard `NEVER_ALLOWED`; listed in `CODEOWNERS`, which GitHub does
not currently enforce: see the rulesets below). Tests:
`tests/test_merge_gate.py`, `tests/test_guard.py`.

Paperclip supplies authority and linkage, GitHub supplies engineering evidence,
and the Studio evaluates them deterministically. A model may *request* a merge
(`merge-gate merge …`); it never decides one. Every decision is appended to
`$STUDIO_DATA/log/merge-gate.jsonl` before any merge, and a failed write
prevents the merge.

**Who asks (Benjamin, 2026-10-10).** The Clerk asks the gate on every tick, with no model and no quota: for each
`done` task in an authorised project whose Paperclip review stage approved in the last 14 days, and for each of its
linked PRs that is open with every check green, it calls the gate once per head commit. A merged PR is noted in the
digest; a refusal only for protected paths is labelled `ready-for-benjamin` as before; any other refusal goes to the
Director. Unreadable evidence (`could not …`) is asked again on the next tick. A model may still request a merge
by hand.

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
| Independent review | Latest GitHub decision per reviewer: no `CHANGES_REQUESTED`. Count trusted-reviewer `APPROVED` reviews **on the exact SHA** (not by the PR author), plus Paperclip review decisions from the issue activity that approve, were made by someone other than the author (`executionState.returnAssignee`) and came **after** the head commit work product was first recorded. A Paperclip changes-requested decision after that point, or an unreadable activity log, refuses. At least one approval for B work or for engineering risk other than `low` (missing or unknown risk counts as high) |
| Protected paths | Always refused: `CONSTITUTION.md`, `CLAUDE.md`, `.claude/**`, `docs/PLAN.md`, `.studio/project.yaml`, `.studio-allowed-paths`, `.github/**`, `CODEOWNERS`, `policy/**`; plus the project's `protected_paths`; plus, if set, anything outside `mergeable_paths` |
| Complete file list | Paginated file count equals GitHub's `changed_files` |
| Mergeable | GitHub `mergeable=true`, `mergeable_state=clean`; open, not draft |
| Stale head / race | Evidence is read immediately before merging; `gh pr merge --match-head-commit <sha>` makes GitHub reject a head that moved. No `--admin`, no `--auto` |

Guard blocks `gh pr merge` and raw API merges (`…/pulls/N/merge`) by agents. That
is defence in depth. The gate becomes the *only* path only when agents' GitHub
credentials cannot merge (see below).

## Ready for a human merge

When the only reasons to refuse are protected paths, every other condition has been proven: the issue is
in review, the review approves the exact head, and the required checks are green. The gate then labels the PR
`ready-for-benjamin`. Benjamin merges labelled PRs only. A PR without the label is still in review, even when
it is open and green (2026-10-02: he had merged #47 and #48 before their review, and #48 went into another
agent's branch). Dependabot is set to security fixes only and has no Paperclip issue, so its PRs are merged by hand.

## Merge credential

If the policy has `"github_app": {"app_id": 5109343, "key_path": "/etc/studio/merge-gate-app.pem"}`, the gate
gets a token for that one repository from the App and uses it, and only it, for every GitHub read and for the
merge (inherited `GITHUB_TOKEN`/`GH_TOKEN` are replaced). No token, no decision. A confined agent
(`studio-agent`) running `merge-gate` is re-run as `paperclip` through one sudo rule, so it never holds the key.

## Project policy entry (template; do not add without Benjamin's authorisation)

```json
"<paperclip project id>": {
  "enabled": true, "repo": "Owner/Name", "base_branch": "main", "merge_method": "merge",
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
- Ruleset `Protect Main` (read 2026-09-28 with authenticated `gh`): PR required with **0 approvals**, no
  code-owner review, merge method `merge` only, required check `check` with up-to-date branches,
  no deletion or force-push, no bypass actors. Classic branch protection is not used (earlier note
  from the public API saying no checks were required was wrong). CI: `.github/workflows/check.yml`,
  one job `check` (full suite, about 28 s).

**Mothers Carpentry** (`Agentic-Builds-Studio-Client-Pages/Mothers-Carpentry-Webpage`; moved from `Agentic-Builds-Studio/`, which now redirects. The policy `repo` must use the new name, since GitHub reports it and the gate compares names exactly. Paperclip still records the old URL, project `c2b582f3-d52e-47fd-812c-e29d6b805d3f`):

- Ruleset `Protect main (Customer Projects)`: PR required with **0 approvals**, no code-owner review,
  merge method `merge` only, required check `check` (branch need not be up to date), no deletion or
  force-push, no bypass actors. CI is `check.yml` (`make check`). No deploy workflow and no GitHub
  deployments exist, so a merge does not deploy through GitHub; host-side deployment is unverified.
- Money, stock, personal-data and migration paths should be `protected_paths`, or be kept to B work with Principal review.
- Nothing about Mothers was changed.

## Known limits

- **Server-side review is not required.** Both rulesets require 0 approvals and no code-owner review,
  so the gate's review requirement and `CODEOWNERS` are not enforced by GitHub.

- **Authority classification.** The Director classifies A/B/HUMAN in the task packet. The gate checks the stated class and its evidence; it cannot judge whether the classification was right.
- **Linkage is recorded by agents.** Work products and branch names are recorded by agents. The gate requires them to agree with GitHub, but it does not scan other issues for a PR linked twice.
- **Semantic deviation.** Deviation inside the declared scope paths is left to independent review.
