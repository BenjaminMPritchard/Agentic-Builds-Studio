---
name: Studio
goal: Build and launch client websites safely, at the lowest cost per finished site.
---
# Studio

An AI company that builds client websites. Agents are model tiers with authority, not job titles:
Director, Principal, Builder-1/2, Liaison, Worker (local Qwen), Clerk (scripts), Recorder, Architect.
Rules: `CONSTITUTION.md`. Agent instructions: `agents/<name>/`. Skills: `skills/`.

This folder is the reproducible Paperclip configuration. `payloads/*.json` are the agent settings
from guide §5.2 with `<placeholders>` for ids and secrets. After the first real setup, replace or
extend this folder with `paperclipai company export` (guide §5.6); exports contain no secret values.
