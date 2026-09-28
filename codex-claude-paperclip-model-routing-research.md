---
title: "Paperclip studio: evidence-based AI routing, capacity and measurement"
as_of: 2026-09-28
revision: 2
status: "Research and operating specification complete; studio benchmarks and enforcement implementation pending"
scope: "Claude Pro, ChatGPT Plus/Codex and existing local Qwen models"
objective: "Maximise accepted, durable client work within subscription caps, then minimise human intervention, then elapsed time"
---

# Paperclip studio: AI efficiency research and operating specification

## 1. Conclusion and evidence boundaries

The strongest defensible starting design is **deterministic automation for mechanical work; small models for bounded interpretation and execution; stronger models for consequential judgment; and a shared quota controller for every cloud invocation**. Which particular model wins each route must be established through task results, including failures, review and rework. A model's token price or benchmark rank cannot establish the studio's optimal routing by itself.

This revision incorporates Ben's interview, corrects model eligibility, and adds an actionable testing plan, clerk records, project checkpoints and conditional scaling rules. It is a specification, not a claim that these controls are already installed. No benchmarks were run on Ben's PC or subscriptions, no account dashboards were accessed, and no studio capacity figures were measured during this research.

Evidence labels used throughout:

- **Owner requirement:** confirmed in the interview; governs the design.
- **Documented:** supported by a linked primary source, checked on 28 September 2026; runtime/account applicability must still be confirmed.
- **Derived:** arithmetic or reasoning from stated assumptions, not a provider promise.
- **Proposed:** a starting policy or experiment; not a measured optimum.
- **Unverified locally:** requires an installed-runtime check or studio measurement.

“Peak efficiency” means the best validated policy for the current workload, quality threshold and constraints. It does not mean maximum tokens, maximum GPU utilisation, the most active agents, or exhausting all available allowance. No universal optimum or fixed number of supported clients is established by this research.

## 2. Confirmed operating requirements

| Topic | Owner requirement |
| --- | --- |
| Availability | Operate 24/7. Complete client website work in dependency order, parallelising where efficient. |
| Idle production | When the complete client project is finished, production stops. Only maintenance continues until another client requests a website. No invented improvement work merely to keep agents busy. |
| Claude studio cap | At most **12% of the provider's five-hour allowance per applicable window**, across all studio agents combined. |
| Codex studio cap | At most **15% of the provider's five-hour allowance per applicable window**, across all studio agents combined. |
| Weekly allocation | Studio may consume at most **80% of each plan's weekly allowance**. The other **20% is for Ben's personal use**. |
| Reserve clarification | Personal use may consume that 20%; it need not remain untouched at reset. The studio must not borrow it. Personal use exceeding its share can further reduce available studio capacity. |
| Paid resources | Claude Pro and ChatGPT Plus initially. No paid API or extra-credit fallback is authorised by this design. Upgrades may be recommended with evidence, not purchased automatically. |
| Local resources | Ryzen 5 3600, RX 5600 XT with 6 GB VRAM, 16 GB RAM; Ollama with Qwen 3.5 4B and 9B. Confirmed by Ben in this interview. |
| Shared PC | Pause local inference for gaming or other demanding personal use. Queue/checkpoint local work; eligible cloud work can continue within its limits. |
| Maintenance | Uptime/error monitoring and repairs; tested dependency/security updates; client email support and requested changes; periodic performance, accessibility, form and integration checks. |
| Response targets | Begin handling urgent outages immediately; routine requests within 24 hours. These are response targets, not guaranteed resolution times. |
| Client work | Brochure sites, portfolios/forms, bookings/calendars/integrations, shops/payments, and custom account/database/business applications. Analyse these as different workload classes. |
| Scale | Follow business growth. Recommend when upgrades merit consideration or become necessary only when supported by substantial evidence. |
| Validation | Produce a testing plan now. The clerk must measure efficiency continuously, at project intervals and at completion. Tests remain to be executed. |

Retained approval rules from the original document:

- **A:** autonomous task-to-merge within explicitly delegated scope and repository safeguards.
- **B1:** Ben accepts the plan; implementation conforms; merge after required checks.
- **B2:** implementation materially deviates from the accepted plan; Ben must accept that implementation before merge.

Approval class and model size are independent. A small model does not make a task low-risk, and a strong model does not remove approval requirements. Client requests can create bounded maintenance change tasks; a substantial new feature or redesign must be classified as new production scope rather than hidden in maintenance totals.

## 3. Five-hour limits and weekly allocation

### 3.1 What the percentages establish

**Documented:** Claude exposes session and weekly usage separately. Codex documents five-hour usage estimates and possible weekly limits; current account limits and reset times are authoritative. Neither reviewed source establishes a universal absolute five-hour-to-weekly allowance ratio for Ben's accounts. [S2, S3]

The 12% and 15% figures are owner-imposed studio ceilings. They are not verified conversions proving 80% weekly consumption. Preserve all four constraints independently: Claude session, Claude weekly, Codex session, Codex weekly.

**Derived:** a seven-day period contains 168 hours, or 33.6 five-hour durations. An even weekly consumption rate of 80% corresponds to:

```text
80 / 168 = 0.476190... weekly percentage points per hour
80 * 5 / 168 = 2.380952... weekly percentage points per five hours
```

Under a simplified constant-capacity, continuously paced model, let F be a provider's full five-hour allowance and W its full weekly allowance, expressed in the same metered units:

```text
Claude: 33.6 * 0.12 * F <= 0.80 * W  requires W/F >= 5.04
Codex:  33.6 * 0.15 * F <= 0.80 * W  requires W/F >= 6.30
```

These are **conditions**, not discovered provider ratios. Actual window boundaries, partial windows, model-specific buckets, changed limits and burst timing prevent treating 33.6 as a literal count of discrete reset windows. Use actual reset metadata. Even if a ratio is measured once, retest after plan/model/limit changes.

### 3.2 Proposed quota controller

Use a non-LLM controller shared by all studio processes using an account. Agent prompts saying “stay below 12%” are insufficient. The controller must cover Directors, workers, reviewers, scouts, clerk summaries, nested subagents, retries, compaction and scheduled model calls.

Maintain separate records for each provider/account/quota bucket/window:

```text
window identifier and actual reset timestamp
account usage observed, observation time, precision and source
studio usage attributed or conservatively bounded
personal usage attributed or unknown
unreconciled usage and outstanding job reservations
maintenance reserve and measurement/overshoot margin
plan, billing mode and allowance-policy version
```

Before admitting a cloud job, atomically reserve its estimated total chain cost: setup, worker, likely retries, reviewer and final handoff. Check its five-hour and weekly reservations separately, because their percentages have different denominators. Do not multiply one by an assumed conversion factor.

Using percentage points, the studio checks are:

```text
studio_5h_used + studio_5h_reserved + next_job_5h + margin_5h <= 12 (Claude) or 15 (Codex)
studio_week_used + studio_week_reserved + next_job_week + margin_week <= 80
```

Also check actual account headroom. For weekly personal protection, if personal usage P is known, preserve `max(0, 20-P)` additional weekly points for Ben. Account usage plus outstanding reservations, the next job, margin and that remaining personal allocation must fit within 100%. Do not subtract already-consumed personal usage twice. Model-specific limits must also pass. If personal attribution is unknown, use a conservative bound and flag reduced studio capacity rather than pretending to know it.

On completion, reconcile reservation against recorded consumption, then release only the reconciled remainder. After cancellation, keep a reservation until delayed usage is accounted for. A process crash must not erase commitments. A restart should recover outstanding reservations and prevent duplicate side effects.

**Hard-limit caveat:** delayed/rounded usage reporting and in-flight model requests mean a predictive reservation is not a mathematical upper bound. A runtime dollar budget is not an exact subscription-percentage limit. Until per-request bounds, telemetry and cancellation behaviour are validated, report these as operating caps with conservative enforcement, not a proven zero-overshoot guarantee. Stop admitting new cloud work when readings are stale or bounds are inadequate; retain deterministic monitoring. Do not silently weaken the owner's cap.

### 3.3 Pacing, incidents and resets

- Spend by useful demand, not a mandatory quota-burning schedule. Unused allowance is acceptable.
- Use the remaining weekly studio budget divided by time to its actual reset as a planning rate. This is a forecast, not a second fixed five-hour conversion.
- Reserve maintenance capacity inside each cap before admitting production. Size it from incident consumption and arrival measurements; no defensible numerical reserve is available yet.
- Before measurements exist, finish production checkpoints early enough to leave a conservative, explicitly provisional buffer. Do not advertise an outage SLA based on an untested buffer.
- Prioritise urgent outages, then time-sensitive maintenance, then production, then optional experiments. Experiments never consume the personal allocation.
- If one provider is unavailable, switch only to a validated alternative with headroom. Otherwise queue and alert. Never substitute a weaker unqualified model solely to avoid waiting.
- A reset is identified from provider data, not a local Monday-midnight assumption. Claude and Codex can reset at different times. Refresh after a reset, plan change or provider limit change; do not treat missing readings as a fresh 100% allowance.
- Scope the five-hour cap to the provider-reported window. If its semantics are rolling, use a matching rolling ledger; do not impose arbitrary local blocks that allow bursts across boundaries.

Immediate outage handling, strict caps and an unavailable local PC cannot jointly guarantee immediate AI investigation in every situation. Deterministic detection, an owner alert and a preapproved rollback may still operate without inference. If these are insufficient, the service promise, capacity or infrastructure must change explicitly.

## 4. Verified model catalogue and initial comparison set

### 4.1 Codex through ChatGPT authentication

**Documented:** OpenAI positions Astra for difficult judgment, Sol for complex coding/agent work and Luna for focused repeatable work. Availability depends on account, client and rollout. GPT-5.6 models remain during rollout. GPT-5.4 and GPT-5.4 mini retired from ChatGPT-authenticated Codex on **31 August 2026**; GPT-5.5 retires on **14 October 2026**. The original document incorrectly left 5.4 variants eligible. A stale pricing row does not override explicit retirement documentation. [S1]

Published credit rates below are **credits per million tokens**, not API dollars or verified Plus quota units. [S2]

| Exact model ID | Input / cached input / output | Proposed role to test |
| --- | ---: | --- |
| `gpt-6-luna` | 2.5 / 0.25 / 12.5 | Bounded extraction, evidence collection, routine changes and clerical synthesis |
| `gpt-6-sol` | 50 / 5 / 250 | General implementation, debugging and review baseline |
| `gpt-6-astra` | 250 / 25 / 1,250 | Ambiguous architecture, difficult failures and consequential decisions |
| `gpt-5.6-luna` | 5 / 0.5 / 30 | Conditional fallback; compare only if a current route needs it |
| `gpt-5.6-terra` | 50 / 5 / 300 | Conditional intermediate comparator |
| `gpt-5.6-sol` | 100 / 10 / 500 | Conditional legacy comparator |
| `gpt-5.5` | 125 / 12.5 / 750 | Short-lived fallback only; retire its routes before 14 October |

Derived from those rates, equal token mixes cost Sol 20 times Luna and Astra 100 times Luna in published credits. Equal mixes and equal success rates are not established for real tasks. These ratios therefore support prioritising experiments, not declaring a winning route or converting to plan percentages.

Use standard speed initially. Documented fast-mode multipliers can consume included usage faster. Do not enable automatic broad delegation merely by selecting a maximum-power preset; record all child work and evaluate its total yield. [S1, S2]

### 4.2 Claude through Claude Code

The official supported-model catalogue lists the following candidates; documented CLI support alone is not proof of Ben's current included entitlement. Resolve each through the actual signed-in runtime before use. [S4]

| Model ID | Proposed comparison role | Eligibility treatment |
| --- | --- | --- |
| `claude-haiku-4-5-20251001` | Bounded doing/scouting and extraction | Verify included account access and actual usage |
| `claude-sonnet-5` | General implementation/review comparator | Verify account access |
| `claude-opus-5-5` | Strong reasoning and difficult implementation comparator | Verify account access and compatible CLI |
| `claude-opus-5` | Previous-generation comparator | Use only if available and a measured advantage warrants it |
| `claude-opus-4-8`, `claude-opus-4-7`, `claude-opus-4-6` | Legacy alternatives | No default allocation; verify access first |
| `claude-sonnet-4-6` | Legacy workhorse | Same |
| `claude-opus-4-5-20251101`, `claude-sonnet-4-5-20250929` | Older documented choices | Same |
| `claude-fable-5`, `claude-fable-5-1` | Outside initial included-Pro set | Pro requires usage credits; excluded under the no-extra-spend policy [S5] |

Do not add announced but unreleased Sonnet/Haiku variants as usable models. Anthropic's Opus 5.5 announcement says Sonnet 5.5 and Haiku 5.5 are forthcoming. It also describes increased five-hour subscription limits—another reason not to assume an old weekly/session ratio remains valid. [S6]

Claude's API dollar prices are not a validated conversion to Pro percentage usage. In particular, no evidence here proves that a Haiku workflow always consumes less included allowance than an Opus workflow after retries and review.

### 4.3 Effort and actual model identity

**Documented:** Opus 5.5 requires Claude Code v2.1.280 or later; its default effort is medium. Effort scales are model-specific; max may overthink. Claude's `ultracode` also changes orchestration, not just reasoning intensity. Noninteractive Fable requests can bill usage credits without a consent prompt. [S7]

**Proposed:** compare default effort first, then one lower or higher supported level where the task gives a reason. On mechanically bounded tasks, test low/default; on ambiguous tasks test medium/high/default before escalating further. Do not carry a numerical “intelligence score” across providers or assume all models support all effort settings.

Pin and log requested AND resolved model, effort, speed, auth mode, CLI version and adapter version. Claude subagents can inherit or substitute models; record the actual child model instead of trusting the configured label. [S8] Reject unapproved paid routes and unexpected substitutions before consequential work wherever the runtime permits it.

The initial experimental shortlist is Qwen 4B, Qwen 9B, GPT-6 Luna, Haiku 4.5, GPT-6 Sol, Sonnet 5, GPT-6 Astra and Opus 5.5. Do not run every model on every task. Screen cheaply, then compare plausible finalists. Legacy models remain discoverable fallbacks rather than multiplying the benchmark matrix without a reason.

## 5. Paperclip integration and telemetry

### 5.1 What the platform provides

Paperclip documents subscription credentials for matching Claude and Codex runtimes as well as separately billed API credentials. These are distinct routes; use supported subscription sign-in, not a generic API proxy supplied with subscription tokens. [S9, S10]

The `claude_local` and `codex_local` adapter documents are current upstream references, not confirmation of Ben's installed version. The Codex adapter also documents managed credential handling and concurrency considerations. Check effective configuration and sign-in mode before any calibration. Do not copy private authentication contents into logs. [S11, S12]

Paperclip's cost API supports token records, project/issue/run identifiers, billing categories and an explicit unpriced state. Its ordinary company/agent budget period is a calendar month in UTC. **Those monthly money budgets do not implement the studio's five-hour and weekly subscription-percentage caps.** A separate quota control layer is required unless the installed version demonstrably provides equivalent controls. [S13]

### 5.2 What to instrument

| Source | Documented information | Integration limit / required check |
| --- | --- | --- |
| Codex App Server | `account/rateLimits/read`, update notifications, bucket IDs, used percentages, window durations and reset timestamps [S14] | Confirm availability through the deployed adapter. Do not assume `primary` always means five hours or `secondary` always means seven days. Inspect every applicable bucket. |
| Claude Code status line | `rate_limits.five_hour` and `rate_limits.seven_day`, including usage percentages/reset times; fields can be absent and appear after an API response [S15] | This is a documented status-line interface, not proof of a headless Paperclip quota API. Validate collection on the installed execution path; absent is unknown. |
| Claude Code usage/monitoring | Session token/cost estimates, cache data and OpenTelemetry usage metrics [S16, S17] | Cost estimates and local-history breakdowns are not full-account quota readings. De-duplicate parent/child records. |
| Paperclip run records | Run/task/project attribution, token and billing metadata [S13] | Reconcile with runtime evidence. Do not label unknown money or quota as zero. |
| Ollama response | Load/prompt/evaluation timing and token counts; durations in nanoseconds [S18] | Log actual local model digest, quantisation, context, backend and residency alongside timing. |

Provider interfaces may be ahead of installed clients. Establish a small capability matrix before implementation: supported, absent, partially exposed, or untested. If headless Claude quota collection cannot be validated, use supervised calibration/manual quota snapshots and conservative admission; do not claim the 24/7 hard-cap controller is production-ready.

### 5.3 Attribution under shared personal use and parallel work

An account meter can include studio work, personal work and other surfaces. A before/after difference around one job is not automatically that job's cost.

For calibration, isolate runs per provider and avoid simultaneous personal activity; observe the meter until delayed reporting settles. For production, retain a single account-level reconciliation ledger, per-run token evidence and parent-child IDs. Mark per-job quota attribution as `measured_isolated`, `estimated_shared`, `bounded`, or `unknown`.

Never assign the full overlapping account delta to every concurrent job. Do not infer zero consumption from an unchanged rounded percentage. Split events crossing a reset into the correct windows; if exact separation is unavailable, preserve uncertainty. Changes in quota denominator require a new measurement epoch, not silently adding incomparable percentages.

## 6. Local-model contribution on the existing PC

**Documented:** Ollama's current Qwen 3.5 tag list shows Q4_K_M artifacts of about 3.4 GB for 4B and 6.6 GB for 9B. These are artifact sizes, not full runtime VRAM requirements. [S19] The installed tag/digest may differ. The 9B artifact alone exceeds the card's nominal 6 GB capacity, so full GPU residency is not a safe planning assumption for that artifact; CPU offload and additional context memory must be measured.

Ollama documents memory growth with concurrent requests and context length. Hardware support depends on backend; Vulkan support is documented, but this research did not verify the installed RX 5600 XT path. [S20, S21, S22]

**Proposed starting policy:** one local inference job at a time, one resident model, Qwen 4B first. Keep OS, browser, Paperclip and test-runner headroom. Test small context budgets such as 4K and 8K, then increase only if complete task inputs and stable memory usage justify it. These are experimental settings, not a claim that an entire coding-agent prompt fits. If tool definitions alone fill the budget, use a narrow extraction service or cloud worker rather than silently truncate the task.

Test Qwen 9B only on a task where 4B fails and the likely quality improvement can offset offload delay and resource use. Do not replace the working runtime or install alternative models merely because a leaderboard looks attractive. Alternative small models can enter later through the same evaluation process.

Good local candidates: fixed-schema extraction from short documents; classification into known categories; summarising a bounded test failure; preparing a compact evidence index; drafting routine text for review. Prefer scripts over even a local model for exact counts, file enumeration, checksums, log filtering, JSON validation, test execution and metric aggregation.

Do not use unvalidated local inference as the sole authority for payments, authorisation, database migrations, security conclusions, client commitments, autonomous broad refactors or unfamiliar root-cause diagnosis.

Pause policy: checkpoint at a safe task boundary, stop admitting local jobs, cancel bounded inference when necessary, and unload its resident model before demanding personal use. Record paused minutes and wasted partial work. Resume from a durable packet; recheck the repository commit to avoid applying stale output. This is reduced local availability, not a cloud quota exception.

Measure electricity at the wall where possible. Keep separate (a) incremental inference energy above matched idle and (b) the extra baseline energy of keeping the machine on when it would otherwise be off. Current electricity prices are not assumed. Use Ben's actual tariff and timestamps. A shared PC cannot be credited with 168 local inference hours each week when gaming, outages and other work remove availability.

## 7. Routing policy: doing, thinking and verification

### 7.1 Choose by uncertainty and consequence

A task's length is not its reasoning requirement. A long extraction job can be mechanically bounded; a three-line authorisation fix can require substantial judgment. However, “understand the entire repository” and “deep research” are not inherently low-reasoning tasks: deciding relevance, resolving contradictions and recognising missing evidence can be difficult.

Preserve Ben's intended division of labour as a **testable pipeline**:

1. A reasoner defines scope, questions, sources, required output, exclusions, stop conditions and escalation conditions. Reuse a previously validated task template when this would otherwise be repetitive planning.
2. Scripts enumerate/search/validate. A bounded worker interprets only the pieces that require language understanding. Use Qwen, Haiku or Luna according to validated context and quality needs.
3. The worker returns an evidence packet with coverage and provenance. Unchecked assumptions remain explicit unknowns.
4. The reasoner synthesises the evidence and makes consequential decisions. It directly inspects high-risk source material and uncertain findings instead of treating a summary as infallible.
5. Implementation and acceptance checks follow the approved task contract. Escalate when new facts break the contract.

Haiku and Luna are therefore candidates for **long, exhaustive doing tasks**, not just short responses. Long jobs should be chunked with a coverage manifest and shared schema. This avoids both duplicated scans and a false claim of total coverage. The strongest models should spend much of their scarce allowance on judgment when this pipeline demonstrably saves total allowance; a strong model remains appropriate for execution that itself requires continuous judgment.

Evidence packet contract:

```yaml
task_id: required
repo_commit_or_source_snapshot: required
scope_requested: required
scope_checked: required
items_checked: []
findings: [] # each: claim, source/path, line or section, observed date, evidence type
negative_searches: [] # search term, scope and limitations; absence is not proof
commands_and_results: []
unknowns_and_contradictions: []
coverage_gaps: []
next_required_action: required
```

The cost test is end-to-end: worker + planner + handoff + checking + repeats + downstream fixes must beat the alternative at acceptable quality. A cheap scout that forces the reasoner to repeat the investigation has not saved work.

### 7.2 Starting routing hypotheses

Every route below is **proposed**, not a benchmark result. Provider choice remains conditional on validated performance and current headroom.

| Task | First route to test | Escalation or acceptance rule |
| --- | --- | --- |
| Monitoring, arithmetic, inventories, clerical totals | Deterministic scripts | Invoke a model only for a new anomaly needing interpretation |
| Bounded extraction / inbox classification | Qwen 4B; compare Luna and Haiku | Schema and source checks; escalate ambiguous requirements |
| Exhaustive scoped research / repo inventory | Script collection plus Luna/Haiku or chunked local work | Coverage manifest; stronger model resolves gaps and synthesis |
| Requirements clarification / architecture | Sol or Sonnet; compare Astra/Opus on hard cases | Approval gate, explicit trade-offs and acceptance criteria |
| Routine change to an established pattern | Luna/Haiku versus Sol/Sonnet baseline | Tests and relevant review; no unapproved scope expansion |
| Multi-file feature / integration | Sol or Sonnet | Stronger reasoning for uncertain contracts, state or failure handling |
| Difficult debugging / migration / incident diagnosis | Sol/Sonnet or directly Astra/Opus when consequence/ambiguity warrants | Evidence-driven diagnosis; no mandatory cheap-model failure first |
| UI implementation / visual polish | Compare coding routes using rendered-browser evidence | Screenshot and interaction review, responsive behaviour and rubric; build success alone is insufficient |
| Auth, payments, permissions, data loss risks | Strong reasoner and independent review | Risk-specific tests, approval class, rollback/recovery evidence |
| Routine client reply | Template or small-model draft | Verified facts and delegated communication scope; escalate commitments/ambiguity |
| Final completion claim | Deterministic evidence plus qualified reviewer | Independent acceptance criteria; task remains incomplete when checks are missing |
| Clerk periodic interpretation | Scripted report first; small model if useful | Reasoner only for anomalies or a consequential routing/upgrade decision |

Avoid assigning an expensive model permanently to a job title. “Director” describes authority; many routing/scheduling decisions are deterministic. Conversely, an inexpensive “builder” must escalate when the code change stops being routine.

### 7.3 Retry and parallelism rules

Proposed initial retry rule: allow one bounded correction for a clear, local error; repeated failure with the same cause triggers diagnosis or escalation. Transport failures use bounded retry/backoff and are logged separately from reasoning failures. Do not let model self-repair loops run until the budget is exhausted.

Parallelise independent work with stable interfaces: separate components, independent evidence collection, or tests that do not race on shared state. Keep dependent schema/API/implementation work ordered. Use isolated worktrees or equivalent protection where concurrent edits can collide; count integration and conflict-resolution cost.

Begin cloud calibration serially per provider. Test concurrency later with central reservations. Do not multiply agent count to increase an account's quota. Parallelism is justified only if it improves accepted throughput or target response time after coordination, cache duplication and rework are counted.

Independent review can reveal correlated mistakes but is not automatically cheaper or more accurate when it uses another provider. Test reviewer defect recall and false alarms using seeded defects. A second model merely agreeing is not acceptance evidence.

## 8. Context, cache, skills and tools

**Documented:** Codex skills use progressive disclosure. Claude Code documents prompt-prefix caching, expiry, changes that invalidate it, and extra work when resuming/compacting cold histories. [S23, S24] API cache pricing or lifetime must not be assumed to match every subscription/client configuration.

Current Claude Code documentation distinguishes the main conversation from subagents: included subscription main-conversation requests normally receive a one-hour cache lifetime, while most other requests receive five minutes, with documented exceptions and overrides. A new subagent has a different prompt prefix and does not initially reuse its parent's cache. [S24] This makes cold worker startup and handoff costs part of the delegation experiment; spawning many tiny workers is not automatically efficient. Validate the installed version and observed cache fields before tuning batch intervals.

**Proposed operating policy:**

- Keep durable state outside a transcript: task contract, accepted plan, source commit, modified paths, tests, decisions, unresolved risks and next action.
- Resume a coherent task when its state is still useful. Start a fresh task session when the objective or assumptions change. A compact handoff should preserve exact constraints and source pointers.
- Retrieve targeted code and source excerpts. For exhaustive work, keep the full evidence manifest in an artifact and pass a compact index plus important excerpts to the reasoner.
- Compact when needed for a continuing task; first persist constraints and unresolved issues. Evaluate lost facts and follow-up rereads as costs of compaction.
- Keep common instructions short and stable. Load task-specific skills/tools when needed, rather than appending the entire studio manual to every run.
- Use explicit model assignments for cheap workers; record the resolved model. A “cheap scout” inheriting an expensive parent defeats the policy.
- Batch related work when it reduces repeated setup without delaying urgent service or increasing error risk. Do not merge unrelated clients into one sensitive context for cache savings.
- Do not send dummy requests to keep a cache warm. Compare useful batching with fresh-session cost; idle inference is consumption.
- Keep verbose logs, screenshots and raw test artifacts outside the working prompt. Return concise results and links, with enough exact evidence to inspect failures.
- Reuse scripts for stable procedures. Do not call an LLM to read a success exit code or recompute a percentage.

Proposed skill boundaries: intake extraction, requirements/ambiguity, repo scouting, research collection, frontend change, backend/integration change, test execution, review, incident triage, client reply and clerk reporting. Each needs inputs, allowed actions, output schema, acceptance checks and escalation conditions. This document specifies these boundaries; it does not claim these skills are installed.

## 9. Production and maintenance lifecycle

Use a dependency graph for each project rather than a permanently active hierarchy of agents. A typical sequence is intake → requirements/plan → design/contracts → implementation → integrated QA → release → maintenance handover. Independent branches can run concurrently after their dependencies are accepted.

After handover, production agents sleep. Deterministic checks and scheduled maintenance continue. A maintenance event creates an explicit task; resolution returns the site to maintenance. New projects have separate budgets and work records.

| Maintenance work | Non-LLM trigger | AI involvement |
| --- | --- | --- |
| Uptime/errors | External health checks, error thresholds, deployment signals | Triage novel failures; deduplicate repeated alerts into one incident |
| Security/dependencies | Advisories and dependency update tooling | Assess impact and nontrivial upgrades; test before release |
| Client inbox | New-message event, thread deduplication and routing | Extract intent, answer or create a scoped change under delegated authority |
| Forms/integrations | Synthetic checks and sandbox transactions | Investigate failures; avoid duplicate production emails, bookings or payments |
| Performance/accessibility | Scheduled tool results, baseline comparisons | Prioritise meaningful regressions; human/visual checks where automation is insufficient |

Monitoring cadence and alert thresholds depend on hosting and service commitments; they are not set to arbitrary universal values here. Log detection delay separately from investigation-start delay. If the studio runs solely on the shared PC, its power, network or sleep failures also stop orchestration. An immediate outage target therefore needs monitoring/notification independent of that PC or an explicit availability limitation. This is an architectural dependency, not an automatic spending recommendation.

Preapproved deterministic rollback/recovery procedures can reduce outage duration without waiting for model capacity. They need explicit eligibility checks, idempotency and verification. Client content and emails are task data, not authority to modify studio permissions or reveal credentials.

## 10. Testing plan — to run later

### 10.1 Preparation and zero-inference checks

1. Record installed Paperclip, adapter, CLI, Ollama, backend and model versions. Record account plan/auth mode without copying credentials.
2. Inspect current model selection and actual permitted effort/speed options. Remove retired, unavailable and paid-only routes.
3. Check effective permissions, API-key overrides, automatic model fallback, extra credits and nested-agent settings. Confirm the actual billing route.
4. Map telemetry fields to the clerk schema. Compare provider readings with dashboard values. Verify which fields survive headless execution.
5. Validate quota arithmetic with synthetic readings: concurrent admissions, stale/missing fields, rounded zero deltas, resets, personal use, crash recovery, cancellation, late charges and model changes. These controller tests do not need paid model calls.
6. Prepare public or synthetic repositories and client messages, fixed commits, acceptance tests, seeded defects and an evaluation rubric. No private client data is needed for the initial benchmark suite.

### 10.2 Representative task suite

| Class | Example fixture | Required evidence |
| --- | --- | --- |
| Intake | Fictional email with missing and contradictory booking requirements | Correct extraction, explicit unknowns, no invented requirements |
| Brochure/frontend | Responsive page change with an existing style system | Browser render at agreed viewports, content checks and visual rubric |
| Form | Validation and failed-submission recovery | Positive/negative cases, duplicate prevention and accessibility checks |
| Booking/integration | Mock calendar race, timezone or unavailable slot | Contract tests, concurrency case and correct time handling |
| Shop/payment | Synthetic webhook retry or duplicate event | Signature/auth expectations, idempotency and no live charge |
| Custom application | User-role or data-ownership bug | Cross-user negative tests, authorised path and regression coverage |
| Debugging | Known defect with misleading adjacent logs | Correct cause, minimal justified fix and reproducer |
| Repo/research scout | Fixed repository or official-source set with a known manifest | Evidence accuracy, coverage and explicit gaps |
| Review | Clean diff and diffs with seeded serious/subtle defects | True findings, missed defects and false alarms |
| Maintenance | Dependency update and synthetic outage | Relevant regression checks, recovery verification and timeline |
| Clerk | Synthetic run ledger containing duplicates, resets and missing data | Correct totals, no double counting and explicit uncertainty |

Freeze task scope and acceptance before comparing models. Do not let a model write the only tests that judge its own patch. Add held-out cases. For visual and client-facing quality, use a recorded rubric and independent human spot checks; a model grader alone is not ground truth.

### 10.3 Staged experiments

**Stage A — instrumentation smoke test:** a few bounded runs on the likely routes. Confirm correct identity, complete logs, quota updates and accept/reject evidence. If telemetry is unusable, fix that before benchmarking efficiency.

**Stage B — screen plausible candidates:** start with one fixture per relevant class. Compare a local/small route with a qualified generalist baseline. A single run only identifies obvious failures and promising candidates; it cannot establish a reliable success rate.

**Stage C — paired finalist trials:** use the same task commits, tool permissions and acceptance criteria for finalists. Randomise/interleave order to reduce time-of-day and service-condition bias. Repeat at least three times across several independent fixtures as an initial screening design, then extend only when uncertainty affects a decision. Three runs are not statistical proof. Separate cold/warm cache conditions and short/long context tasks.

**Stage D — pipeline ablations:** compare (1) generalist end-to-end, (2) small scout plus reasoner, (3) deterministic collection plus reasoner, (4) low/default versus higher effort, and (5) same-provider versus cross-provider review. Change one factor at a time. Count both agents, handoff rereads and failed attempts.

**Stage E — scheduling and failure drills:** test approved parallelism; local pause/resume; exhausted Claude/Codex caps; both providers blocked; personal use during a run; outages during production; duplicate inbox events; runtime restart and stale source commits. Confirm monitoring continues without repeated paid heartbeats and no unexpected API fallback occurs.

**Stage F — limited production observation:** promote a route provisionally to low-consequence work only after its acceptance evidence passes. Observe real outcomes and reopenings. High-consequence routes need the relevant seeded failure tests and review gates even when average pass rates look good.

All cloud tests count inside the studio's 12%/15% and 80% allocations. Allocate an experiment budget only from remaining production-safe headroom, with maintenance protected. No fixed benchmark-spend allowance is invented. Schedule across resets if needed; stop an experiment once its remaining uncertainty cannot change the decision or its budget is exhausted.

### 10.4 Decision rules and limitations

- Reject any route that violates permission, billing, quota or critical acceptance rules.
- Compare accepted results after all review and rework, not just the first generated answer.
- Promote only when quality is adequate and the evidence supports a useful allowance/time/intervention trade-off. If results overlap, retain the established route and collect more evidence during normal work.
- Log sample size, independent task count and uncertainty. Repeats on one fixture are correlated and do not replace coverage across distinct tasks.
- With zero failures in n independent trials, the approximate “rule of three” gives an upper 95% failure-rate bound of about 3/n; even 30 clean trials do not demonstrate negligible risk. Treat this as a statistical heuristic with its assumptions, not a safety certificate.
- Revalidate after model, prompt, skill, tool, adapter, context-policy or substantial workload changes. Historical results remain attached to their version, not silently transferred.

## 11. Clerk specification: records and cadence

The clerk is an accounting and evidence function. Most collection and arithmetic should be deterministic. Model-written commentary is optional and its consumption must be included. The clerk never invents missing records, approves its own work, changes budgets or upgrades plans.

### 11.1 Per-event and per-task records

| Record group | Required fields |
| --- | --- |
| Identity | Event ID, task/work-package ID, parent task/run IDs, project/client ID, stage, UTC timestamp, attempt number |
| Scope and risk | Workload class, complexity/ambiguity tags, approval class, fixed acceptance criteria version, priority, due/response target |
| Runtime | Requested/resolved provider and model, effort, speed, auth/billing mode, CLI/adapter/tool/skill versions, prompt-template hash |
| Reproducibility | Source commit, fixture ID, context policy, local model digest/quantisation/backend, input/output artifact pointers |
| Tokens | Provider-reported uncached input, cached input/cache-write if available, output, reasoning tokens if separately exposed; definition of each field |
| Quotas | Raw before/after observations, actual window IDs/reset times, precision, delay, studio/personal attribution class, reservations, margins, applicable buckets |
| Timing | Queued, admitted, first action, model execution, tool execution, review, blocked, personal-PC pause, accepted and released timestamps |
| Outcome | Accepted/rejected/blocked/abandoned, acceptance evidence, failed checks, escalation/retry reason, human intervention minutes |
| Quality | Review findings by severity, seeded-defect detection where relevant, false alarms, later reopenings, regressions and rollback links |
| Money/resources | Actual incremental charges, estimated API-equivalent cost separately, subscription allocation method, kWh, local available/busy hours, RAM/VRAM/offload observations |
| Context/coordination | Cache observations, compactions, restarts, duplicated reads, handoff size, source coverage, parallel conflicts and integration effort |

Never log credentials or unnecessary customer contents. Store enough redacted evidence to reproduce a finding. Retain immutable raw events plus versioned derived reports. A repaired extraction changes the derived record with provenance; it does not erase the original event.

### 11.2 Project intervals and completion

| When | Clerk output | Decision supported |
| --- | --- | --- |
| Every run/attempt ends | Usage, identity, outcome, evidence and unresolved reservation | Can the next task be admitted? |
| Every accepted work package | Total chain cost including retries/review; acceptance; remaining dependency work | Is the route producing acceptable work efficiently? |
| Each five-hour reset / budget reconciliation | Per-provider studio use versus 12%/15%, personal/account use, overshoot/stale-reading incidents | Adjust pacing or halt faulty enforcement |
| Daily during active work | Queue age, due tasks, incident reserve, predicted remaining-week demand, local availability | Reprioritise before response targets are missed |
| Intake/requirements accepted | Requirements completeness, clarification loops, baseline scope and forecast range | Is implementation ready to begin? |
| Design/architecture accepted | Decisions, contracts, risk gate, expected implementation/review demand | Can independent branches start safely? |
| Each implementation milestone | Accepted features versus baseline, spend-to-date, scope changes, defects, forecast to finish | Continue, revise scope, escalate or rebudget |
| Integrated QA / release readiness | Failed/passed acceptance checks, unresolved risks, review cost, rollback readiness | Release or keep the project open |
| Project completion / maintenance handover | Whole-project resource totals, acceptance, outstanding support obligations, baseline maintenance demand | Close production and begin maintenance accounting |
| Post-release review | Linked regressions, client corrections, reopens and recovery costs | Correct the true delivered-work efficiency |
| Every provider weekly reset | Full studio/personal reconciliation and withheld-reserve compliance; route comparisons | Capacity and upgrade evidence |
| Monthly maintenance review | Per-site-class demand, incidents, routine request latency, dependency work and idle-monitoring overhead | Price/capacity review and client admission |

Proposed post-release checkpoints: 7 and 30 days, plus any serious incident. These are measurement intervals, not promises that defects stop appearing after 30 days. Report later defects against the original delivery cohort and current maintenance period without double-counting the resource event.

### 11.3 Efficiency metrics and accounting rules

For a predefined work-package class:

```text
first_pass_acceptance = accepted without substantive rework / completed first attempts
eventual_acceptance = accepted work packages / all attempted work packages
provider_allowance_per_acceptance = total attributed provider usage for the class / accepted work packages
human_minutes_per_acceptance = total intervention minutes / accepted work packages
rework_share = usage linked to correction and avoidable repeats / total usage
queue_latency = admitted_at - queued_at
response_latency = first meaningful handling_at - received_or_detected_at
end_to_end_latency = accepted_at - received_or_queued_at
local_decode_tokens_per_second = eval_count / (eval_duration / 1e9)
local_energy_cost = sum(kWh_in_tariff_interval * actual_price_per_kWh)
```

Show Claude and Codex consumption as separate columns/vectors. Do not add their percentages and call the result money or interchangeable capacity. A task using both providers must include both components. For scheduling comparisons, test which resource is binding; a route that saves Claude while spending spare Codex may increase feasible throughput without being cheaper in any universal currency.

Use median and tail latency, not only averages. Include failed and abandoned work in the numerator. If no work is accepted, report “no accepted results” and the consumption; do not hide it by dropping the route. Freeze work-package boundaries before evaluation so splitting one feature into ten tickets cannot create apparent productivity.

Deduplicate by stable event/run IDs. Provider token totals may already include cached or reasoning tokens; keep their definitions and avoid adding components twice. Shared overhead stays in a visible company bucket until allocated by a declared method. Allocated project totals must reconcile back to the company total. Quota spent across different allowance regimes remains in separate epochs.

Subscription fees are real fixed business costs. API-equivalent token estimates can help explain behaviour but are not cash spent on an included subscription. Local inference has no provider quota charge but still consumes electricity, time and shared-PC capacity. Keep all three cost views visible.

### 11.4 Completion report template

```text
Project / cohort / workload class / release commit:
Original scope; accepted scope changes; final acceptance evidence:
Dates: intake, approved plan, implementation milestones, release, handover:
Claude: weekly and session usage by actual window, attribution confidence:
Codex: weekly and session usage by actual window, attribution confidence:
Local: inference hours, availability, kWh, energy cost, pauses/offload:
Planning / doing / review / rework / coordination / clerk overhead:
Human interventions and minutes; approval waits shown separately:
First-pass acceptance; rejected/abandoned work; escaped defects:
Response and completion latency; deadline misses and their causes:
Forecast versus actual; explanation of variance:
Routes that improved or worsened outcomes, sample sizes and limitations:
Maintenance baseline and remaining obligations:
Capacity implication; upgrade status and evidence:
Next measurement action; owner decisions needed:
```

## 12. Scaling and evidence-based upgrades

There is no justified “upgrade at five clients” rule. A rarely changed brochure site and a payment application have different incident, testing and support demands. Client count is a business descriptor; measured workload is the capacity input.

Build separate demand profiles for each service class: new builds, change requests, routine maintenance and incidents. Forecast their combined demand against each provider's effective five-hour capacity, studio weekly allocation, local available hours and human approval capacity. Include tail demand and concurrent outages, not just average consumption.

Conceptually, for task class j and route r, measure a resource vector containing Claude quota, Codex quota, local time and human time per accepted package. Select routes and admitted workload such that their combined demand fits every relevant window and quality/response constraint. Five-hour admission and deadlines matter even if weekly totals fit. This is a proposed capacity model; its coefficients are currently unknown.

| Status | Evidence needed | Action |
| --- | --- | --- |
| Insufficient evidence | Missing telemetry, too few representative tasks, changed models or unclassified workload | Do not give a supported-client number. Collect the missing observations. |
| Upgrade worth considering | Sustained or forecast quota-related queues threaten commitments; measured routing improvements cannot provide sufficient headroom | Compare the smallest relevant plan increase with delaying new admissions, scope changes and measured efficiency improvements. |
| Capacity increase required to keep current commitments | Validated forecast or observed demand cannot meet accepted targets under current caps, even with reasonable routing/scheduling; quota is demonstrated to be the bottleneck | Add validated capacity before accepting more work, or explicitly change commitments. A paid plan is “required” only if it resolves the actual bottleneck and chosen alternatives are insufficient. |
| Upgrade not justified | Delays are caused by approvals, broken tooling, client ambiguity, quality failures or unavailable local resources rather than subscription capacity | Repair the binding cause; more quota alone does not solve it. |

As a proposed evidence floor, observe more than one complete weekly reset cycle and representative project stages before estimating steady demand. Several cycles improve evidence but are not automatically sufficient, especially for rare outages. Use forecast ranges and scenario tests; do not claim a well-estimated 95th-percentile incident load from a handful of incidents.

**Documented plan candidates:** OpenAI advertises Pro tiers with 5x or 20x more Codex usage than Plus. Anthropic lists Max 5x and Max 20x at US web prices of $100 and $200 monthly. [S2, S25] These are provider descriptions, not verified multiples of Ben's sustainable weekly studio output. Obtain current UK checkout prices/tax and exact account entitlements before an upgrade recommendation; this document does not invent GBP totals.

If upgraded, retain the owner's 12%/15% five-hour caps and 80% weekly studio allocation as percentages of the new plan unless Ben explicitly changes them. Recalibrate the two windows independently. A provider's advertised session multiplier does not prove the same weekly multiplier or improve model correctness. Fable eligibility can change on Max, but adding it remains a separately evaluated routing decision. [S5]

Upgrade memo required from the clerk:

1. Current bottleneck, affected targets, supporting run/window records and data quality.
2. Forecast workload and uncertainty, including accepted new work and incident scenarios.
3. Current-plan alternatives tried and their measured outcomes.
4. Candidate plan's current documented limits, price and any account-specific unknowns.
5. Expected additional accepted work or avoided delay, with assumptions explicit.
6. Whether the extra commercial margin justifies recurring cost; use actual business figures, not invented revenue.
7. Post-upgrade validation and a reconsideration point if expected gains do not occur.

## 13. External evidence and unresolved questions

SWE-bench Verified contains 500 human-filtered issue instances. Its documentation distinguishes arbitrary systems from the more controlled mini-SWE-agent comparison and warns that harness releases are not necessarily comparable. This supports using matched harnesses in studio trials; it does not estimate website deliveries per subscription week. [S26]

Terminal-Bench's retrieved current page identifies version 4.0 and resolution/cost/token reporting, but its numeric leaderboard rows were not available in the retrieved page. No scores have been reconstructed or imported from a different version. [S27]

Anthropic's Opus 5.5 cost/performance claims are vendor-reported and concern its test conditions. They justify evaluating the new model, not applying a claimed percentage saving directly to the studio's Pro quota. [S6]

No source reviewed establishes the complete same-harness comparison of all shortlisted models, on this studio's tasks, with measured subscription quota and local resource cost. That missing evidence is supplied by the testing and clerk programme, not by fabricated rankings.

Still unknown locally:

- Current effective account quotas, denominators, reset semantics and model-specific buckets.
- Which documented quota interfaces the installed Paperclip runtimes expose reliably before and during headless work.
- Per-route acceptance rates, incident demand, quota tails, attribution precision and safe margins.
- Installed model digests, context sizes, actual GPU residency, local speed and energy use.
- Shared-PC uptime and local availability; monitoring/hosting availability independent of it.
- Current UK upgrade checkout prices and measurable capacity gains.

These gaps do not prevent adopting the measurement design. They prevent claiming validated peak routing, exact supported-client counts, or guaranteed autonomous enforcement today.

## 14. Revision record and refresh policy

**28 September 2026, revision 2:** incorporated the full interview; broadened scope to existing local models; clarified that the 20% reserve is for personal use; separated session caps from weekly allocation; removed retired GPT-5.4 variants from eligibility; replaced broad capability assertions with testable routing hypotheses; added quota telemetry and attribution limitations, maintenance capacity, staged tests, clerk records, project checkpoints and evidence-based upgrades.

This revision supersedes the original operational recommendations. It retains the intent of cheap doing agents and strong reasoning agents while requiring end-to-end evidence. Original material is preserved in the file's prior version history; unverified numerical capability or capacity claims are not carried forward as facts.

Refresh model/plan eligibility before enabling a route and after provider/client changes. Recheck documented retirements before scheduled work. Rebaseline after material changes; retain old records for comparison with their original version labels. The clerk should flag changes for review, not autonomously raise caps or remove approval gates.

## 15. Primary-source register

All sources below were retrieved or checked on **2026-09-28**. Current documentation may change; record a dated source snapshot when implementing a dependency. Source pages establish the specific facts attributed to them, not every proposed studio policy in this document.

| ID | Source and use |
| --- | --- |
| S1 | [OpenAI — Models](https://learn.chatgpt.com/docs/models): model roles, availability conditions, retirement dates and reasoning/orchestration distinctions |
| S2 | [OpenAI — Pricing](https://learn.chatgpt.com/docs/pricing): published credits, usage caveats, sharing and plan tiers |
| S3 | [Anthropic — Usage limit best practices](https://support.claude.com/en/articles/9797557-usage-limit-best-practices): session and weekly account meters |
| S4 | [Anthropic — Claude Code model configuration](https://support.claude.com/en/articles/11940350-claude-code-model-configuration): supported model identifiers |
| S5 | [Anthropic — Fable models on your plan](https://support.claude.com/en/articles/15424964-claude-fable-models-on-your-plan): Pro paid-credit exclusion and differing Max treatment |
| S6 | [Anthropic — Opus 5.5 announcement](https://www.anthropic.com/claude-opus-5-5): vendor claims, forthcoming releases and changed session limits |
| S7 | [Claude Code — Model configuration](https://code.claude.com/docs/en/model-config): CLI requirements, effort defaults, model resolution and noninteractive billing behaviour |
| S8 | [Claude Code — Subagents](https://code.claude.com/docs/en/sub-agents): actual model selection and inheritance |
| S9 | [Paperclip — Anthropic connector](https://docs.paperclip.ing/connectors/anthropic/): supported credential routes |
| S10 | [Paperclip — OpenAI connector](https://docs.paperclip.ing/connectors/openai/): supported credential routes |
| S11 | [Paperclip — Claude local adapter](https://github.com/paperclipai/paperclip/blob/master/docs/adapters/claude-local.md): upstream runtime reference |
| S12 | [Paperclip — Codex local adapter](https://github.com/paperclipai/paperclip/blob/master/docs/adapters/codex-local.md): upstream runtime and credential/concurrency reference |
| S13 | [Paperclip — Costs API](https://docs.paperclip.ing/reference/api/costs/): billing categories, token attribution and monthly budgets |
| S14 | [OpenAI — Codex App Server](https://learn.chatgpt.com/docs/app-server): account quota read/update schema |
| S15 | [Claude Code — Status line](https://code.claude.com/docs/en/statusline): quota field definitions and absence conditions |
| S16 | [Claude Code — Manage costs](https://code.claude.com/docs/en/costs): local cost estimates, usage and cache diagnostics |
| S17 | [Claude Code — Monitoring](https://code.claude.com/docs/en/monitoring-usage): telemetry and its attribution limits |
| S18 | [Ollama — Generate response](https://docs.ollama.com/api/generate): token/timing fields, structured output and model-specific thinking controls |
| S19 | [Ollama — Qwen 3.5 tags](https://ollama.com/library/qwen3.5/tags): current artifact variants and sizes |
| S20 | [Ollama — FAQ](https://docs.ollama.com/faq): residency, concurrency and memory behaviour |
| S21 | [Ollama — Context length](https://docs.ollama.com/context-length): context configuration and memory implications |
| S22 | [Ollama — Hardware support](https://docs.ollama.com/gpu): backend-dependent GPU support |
| S23 | [OpenAI — Build skills](https://learn.chatgpt.com/docs/build-skills): progressive disclosure |
| S24 | [Claude Code — Prompt caching](https://code.claude.com/docs/en/prompt-caching): prefix reuse, expiry and compaction/resume behaviour |
| S25 | [Anthropic — Max plan](https://support.claude.com/en/articles/11049741-what-is-the-max-plan): advertised tiers and US web prices |
| S26 | [SWE-bench — Verified](https://www.swebench.com/verified.html): dataset and comparison methodology |
| S27 | [Terminal-Bench](https://www.tbench.ai/): current benchmark identity and reporting structure; numeric scores not retrieved |
