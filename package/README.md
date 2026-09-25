# package/

Reproducible Paperclip configuration. See `COMPANY.md`. `payloads/` holds the JSON to paste into the
Paperclip web page or send with `paperclipai agent create --company-id <id> --payload-json "$(cat payloads/agent-x.json)"`
(replace every `<placeholder>`; strip the `_note` keys first with `jq 'del(._note)'`).
The web page is the normal way to configure the company; these files exist so it can be rebuilt.

Field names such as `instructions`, `desiredSkills` and `title` follow the guide's tables, not a verified
schema (guide §5.4: instructions are set as Agent → Instructions → External; skills with
`paperclipai agent skills:sync <agent-id> --desired-skills a,b,c`). Check the create payload against
the running instance and set those two things through the UI/CLI if the create call rejects them.
