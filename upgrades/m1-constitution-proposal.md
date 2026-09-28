# Proposed Constitution amendment for Benjamin

Status: **superseded and applied 2026-09-28** with Benjamin's authorisation. The adopted text
replaces the proposal below: autonomous merge only through `bin/merge-gate` for a project
authorised in `policy/autonomous-merge.json` (none yet), and an explicit `local_trusted` gap
statement instead of the claim that host access cannot obtain Board authority. The original
proposal is kept for history.

Original status: proposal only. `CONSTITUTION.md` was not edited. Its opening sentence
says only Benjamin can change it. This amendment is required to remove the
current conditional Director merge exception and align it with the approved
initial policy.

Replace the first bullet under **Only a human may** with:

> - merge a pull request for the Studio operating-system repository or the
>   Mothers project. For other projects, autonomous merge requires separate
>   explicit human authorisation and a server-side gate that verifies the
>   repository, exact head SHA, required checks and reviews, protected paths,
>   and task authority. `--admin` merges remain human-only;

Replace **Enforcement** with:

> `bin/guard` and the Claude deny rules are defence in depth. Paperclip
> authentication and authority rules, credential and filesystem boundaries,
> and GitHub branch protection provide the consequential controls. Agents
> cannot accept human-only confirmations or acquire Board authority merely
> through local host access.

The first replacement removes an existing grant, so leaving it unresolved
would make the rulebook contradict the approved initial merge policy. The
second removes the claim that Guard is the complete security boundary. Neither
replacement is active until Benjamin edits or explicitly authorises the
Constitution change, and runtime activation remains a separate approval.
