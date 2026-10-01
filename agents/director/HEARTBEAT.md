# Director run checklist
1. Read the `digest` on the Director inbox issue. Read only the tasks it names.
2. For each item needing you: decide, or write a packet, or raise one batched Board question.
3. Classify authority and engineering risk separately. Request exact-revision human-only approval for B; queue HUMAN actions.
4. Accept or bounce finished work against "Done when". After 2 review rounds, settle it yourself.
4b. Make sure the issue records its PR and exact head SHA as work products (the assignee runs `studio-record-pr <issue id> <PR URL>`; the Clerk lists PRs matched only by branch name). If `policy/autonomous-merge.json` authorises the project, run `/srv/studio/bin/merge-gate merge --issue <id> --repo <owner/name> --pr <n> --head <sha>`; if it refuses, or the project is not authorised (Mothers is; the Studio is not), the PR waits for human merge. Never work around a refusal. A merge alone does not satisfy every acceptance criterion.
5. Comment with the decision and reason. End with 2–3 process notes. Stop.
