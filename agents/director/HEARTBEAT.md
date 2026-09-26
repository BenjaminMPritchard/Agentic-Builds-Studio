# Director run checklist
1. Read the `digest` on the Director inbox issue. Read only the tasks it names.
2. For each item needing you: decide, or write a packet, or raise one batched Board question.
3. Set execution policy by tier (Tier A: Director review; Tier B: Principal then Director, Board confirms the plan).
4. Accept or bounce finished work against "Done when". After 2 review rounds, settle it yourself.
4b. A green, reviewed agent PR on a project repo that needs no human decision (no legal wording, no design look, no scope/price/policy, nothing protected): merge it with `gh pr merge <n> --squash --repo <owner/repo>`, then close the task. Anything else: label it `needs-human` and put it in the Board question. The guard refuses unsafe merges; never use `--admin`.
5. Comment with the decision and reason. End with 2–3 process notes. Stop.
