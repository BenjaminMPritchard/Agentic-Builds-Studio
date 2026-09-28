# package/

Paperclip configuration reference. See `COMPANY.md`. `payloads/` contains
historical creation payloads with placeholders, not a current company export
or an instruction to recreate existing agents. Reconcile each payload with
the live agent before any approved configuration change.

Field names such as `instructions`, `desiredSkills` and `title` follow the guide's tables, not a verified
schema (guide §5.4: instructions are set as Agent → Instructions → External; skills with
`paperclipai agent skills:sync <agent-id> --desired-skills a,b,c`). Check the create payload against
the running instance and set those two things through the UI/CLI if the create call rejects them.

## Verified against a live instance (v2026.916.1, 2026-09-26)

- `POST /api/companies/{id}/agents` accepted these payloads with these corrections: valid roles are
  `ceo cto cmo cfo security engineer designer pm qa devops researcher general` (so Liaison and Clerk are `general`);
  `claude-opus-5-5` and `--effort xhigh` in `extraArgs` are accepted; budget is set on creation.
- Agents must be created WITHOUT `runtimeConfig.aiConnection`. The wizard's "My Claude subscription" connection
  makes Paperclip reject `extraArgs` and env overrides, and it cannot be removed by PATCH.
- Secrets are referenced by id (`{"type":"secret_ref","secretId":"<uuid>","version":"latest"}`); look ids up with
  `GET /api/companies/{id}/secrets` (names and ids only).
- The Clerk is a `process` agent with a 600 s heartbeat and `CLERK_DRY_RUN=0` (live).
