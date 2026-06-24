# Specification

What Crucible is, who uses it, and how anyone can tell whether it is doing its job. User stories carry explicit Given / When / Then acceptance criteria. The transparency requirements in `constitution.md` section 4 manifest here as user stories with measurable acceptance, not as a vague nonfunctional goal.

If a behavior is not in this file, it is not in the product, and the answer to "but should it" is "open a pull request against this file first."

## 1. Problem statement (one paragraph)

AI models are graded against a proxy metric, and the optimizer that fit the model finds the cheapest path to that score. When the proxy diverges from the real goal, the optimizer lives in the gap: the model scores high on the metric and silently fails at the job. Crucible's user is whoever paid for or is responsible for that AI system continuing to do what it claims to do. Success is the user being able to point at a single number ("we caught X percent of cheats against an attacker who knew the verification scheme") and trust it. Success is also the user being able to drill into any individual catch-or-miss and see, end to end, exactly what each subcomponent did. Crucible is the evaluation harness; the target (the model or agent under evaluation) is the external system being evaluated, brought by the customer or provided as an example in `examples/targets/` — it is not part of the harness.

## 2. Customers

Listed in priority order. The first three are who we design the two-week demo around.

1. **A bank's model risk officer** consuming an AI fraud-detection model from a vendor. Subject to United States Federal Reserve Supervisory Letter 11-7 (SR 11-7). Pays for independent verification with a report in SR 11-7 format. The fraud target adapter and the SR 11-7 report exist for this customer.
2. **A code-generation agent vendor** (a Cursor, Cognition, or GitHub Copilot Business engineering lead) whose enterprise customers ask "does this agent reward-hack our test suite." The code-agent target adapter exists for this customer.
3. **A public-sector artificial intelligence (AI) procurement officer** (US AI Safety Institute, UK AI Safety Institute, European Union AI Office). The exported seeded-hack corpus and the leaderboard exist for this customer.
4. AI auditors and red-teaming firms; AI insurance underwriters; frontier labs (for fine-tunes and bug bounties). Out of scope for the two-week build; in scope for the productization roadmap.

## 3. User stories

Each story is owned by one of the four pillar owners (Targets-and-Oracles, Red, Blue, Measure). The owner is responsible for the acceptance test passing in `vouch`.

### US-1. Submit a target for evaluation

**As an** operator running Crucible, **I want** to register a target (a model endpoint or a code-agent harness) together with a sealed specification, **so that** Crucible can run a measured red-and-blue pass against it.

- **Given** the operator pastes a Yet Another Markup Language (YAML) spec describing the task plus a model artifact reference,
- **When** the operator clicks Start on the Run Launcher (`/`),
- **Then** the dashboard navigates to `/runs/:runId` and shows the spec accepted, the producer sandbox launched, and the first attack round in progress within ten seconds.

**Owner:** Targets-and-Oracles.

### US-2. Watch one round of the loop unfold in real time

**As an** operator, **I want** to see attack-success-rate (ASR) climbing, detection-rate falling, and the red agent's reasoning trace scrolling, **so that** I can tell at a glance whether the platform is doing its job on this run.

- **Given** a run is in progress,
- **When** I open `/runs/:runId`,
- **Then** I see an ASR chart updating once per attack, a detection-rate chart updating once per verdict, and a reasoning-trace pane streaming new tokens from the red agent's chain of thought via Server-Sent Events (SSE).
- **And** every trace line carries an "Inspect" button that opens the underlying LLM call's prompt, raw response, parsed output, token count, and dollar cost.

**Owner:** Measure.

### US-3. Drill into any single verdict

**As an** operator, **I want** to click any verdict and see exactly which oracle fired, which spec obligation was violated, what the producer's output was, and what the held-out test would have expected, **so that** I trust the catch.

- **Given** a verdict exists at `/runs/:runId/verdicts/:verdictId`,
- **When** I open that page,
- **Then** I see (a) the producer's output, (b) the spec obligation cited verbatim, (c) one card per oracle showing pass-or-fail plus the oracle's own reasoning, (d) the aggregator's vote tally, (e) a "Replay" button that re-runs the verdict deterministically.
- **And** the page renders within one second on cached audit data.

**Owner:** Measure. Replay determinism owned by Targets-and-Oracles (seed capture).

### US-4. See every oracle's vote and reasoning

**As an** operator or auditor, **I want** the verdict view to show each of the four oracles plus the large language model (LLM) judge as separate cards, **so that** "the LLM judge alone" can never be mistaken for "the verdict."

- **Given** the verdict view,
- **When** I scroll the oracle vote section,
- **Then** five cards appear in order (held-out tests, metamorphic relations, differential cross-family, property-based fuzz, LLM judge), each carrying the obligation it checked, the result, and a one-paragraph reason.
- **And** the LLM judge card is visually marked "one vote" with a tooltip explaining why.

**Owner:** Measure.

### US-5. Replay any past action

**As an** operator or auditor reviewing past behavior, **I want** every persisted action (a verdict, an attack, a blue patch, an oracle vote, an LLM call) to carry a "Replay" button that re-runs it deterministically and surfaces any difference, **so that** Crucible's behavior is reproducible end to end.

- **Given** any persisted row with a captured seed,
- **When** I click Replay,
- **Then** the action re-runs in a side-by-side pane and the dashboard highlights any diff between the original output and the replay.
- **And** if the replay differs from the original, a red banner appears with the row identifier and the diff is logged as a non-determinism incident.

**Owner:** Measure. Determinism owned by Targets-and-Oracles.

### US-6. Browse the strategy catalog

**As a** red-team owner, **I want** every successful evasion to appear in `/catalog`, **so that** the platform's institutional memory is visible and the demo shows the catalog growing in real time.

- **Given** at least one successful evasion exists,
- **When** I open `/catalog`,
- **Then** I see a sortable table of (tactic name, target-type filter, first-discovered run, reuse count, average dollars-to-succeed),
- **And** clicking a row reveals the prompt fragment, the discovery audit trace, and a "Run This Tactic Against a Different Target" button.

**Owner:** Red.

### US-7. Trigger the blue loop and review the patch

**As an** operator, **I want** Crucible to propose a blue patch automatically when undetected evasions accumulate, **so that** I can review a diff before retraining is applied.

- **Given** the strategy catalog contains at least three undetected attacks of the same target type,
- **When** the orchestrator schedules a blue pass,
- **Then** `/blue/:patchId` shows (a) the proposed feature additions, (b) the proposed adversarial training samples with provenance to the catalog entries, (c) a "Validate on Held-Out Attacks" button.
- **And** the held-out validation never touches the attacks the patch was built from; if it does, the orchestrator refuses to apply the patch and surfaces a typed error.

> **Implementation note (Option B, 2026-06-24).** The blue maker does NOT pick feature additions off a menu. It is given ONLY the raw data columns and the attack pattern, REASONS to a hypothesis, and WRITES a feature-engineering transform (Python source). The harness runs that untrusted code in the Docker producer sandbox over a bounded sample, retrains on the base features plus the one engineered column, validates recovery on the held-out evasions, and iterates with feedback. It is bounded and **allowed to fail** — there is no guaranteed-recovery fallback, and recovery from a single engineered feature is honestly partial (amt still dominates the model). Per constitution §1 deviation, the maker runs on **Opus 4.8** (code generation held to the higher tier), not the §1-default Sonnet.

**Owner:** Blue.

### US-8. See platform health for every subcomponent

**As an** operator, **I want** a `/health` page that lists every module, every sub-module, every external dependency (Postgres, the sandbox adapter, Anthropic), and shows live pass-fail status with last-self-test timestamp, **so that** when something breaks I see what and where in under five seconds.

- **Given** the platform is running,
- **When** I open `/health`,
- **Then** I see a hierarchical view (pillar, then module, then subcomponent) with each leaf showing one of {green and timestamp, amber with last-known-good and current error, red and current error}.
- **And** each leaf carries a "Run Self-Test Now" button that re-runs the subcomponent's smoke test and updates the status in place.

**Owner:** Measure. Self-test endpoints owned by each pillar.

### US-9. Confirm the producer sandbox is actually sealed

**As an** auditor reviewing Crucible's claims, **I want** the dashboard to surface evidence that the producer container cannot reach the verification artifacts, **so that** the core bet is not just asserted but demonstrated.

- **Given** a run is in progress,
- **When** I open `/health` and expand the producer sandbox card,
- **Then** I see (a) the sandbox job identifier, (b) the network egress allow-list applied (empty), (c) the environment variable list (no Postgres host, no sandbox/provider credentials, no Anthropic key), (d) a "Run Seal Probe" button that runs an inside-the-sandbox probe trying to reach Postgres, the sandbox's control plane / host, and the verification bucket; each must time out.

**Owner:** Targets-and-Oracles.

### US-10. Honest dashboard metrics

**As an** operator or auditor, **I want** the headline numbers at `/metrics` to be measured from real runs, never sampled, never zero-defaulted, **so that** the SR 11-7 model risk report carries weight.

- **Given** at least one run has completed,
- **When** I open `/metrics`,
- **Then** I see five tiles: undetected-hack rate, validation-vs-held-out gap, recall on the seeded corpus, dollars per caught hack, human-minutes per thousand outputs.
- **And** each tile shows the count of runs it aggregates over and the timestamp of the latest contributing run.
- **And** any tile with zero contributing runs renders the literal text "Not yet measured" with a link to the Run Launcher, never a "0.0" sample value.

**Owner:** Measure.

### US-11. Export the seeded-hack corpus

**As a** researcher or downstream auditor, **I want** to download the corpus of attacks that succeeded against the target, with full audit traces, **so that** the benchmark outlives the demo.

- **Given** the corpus contains at least one entry,
- **When** I open `/corpus` and click Download,
- **Then** I receive a JavaScript Object Notation Lines (JSONL) file where each line is `{attack_id, target_type, tactic, prompt, audit_trace, dollars, captured_at}`.
- **And** the file's row count matches the table's row count exactly.

**Owner:** Measure.

### US-12. Generate an SR 11-7 model risk report

**As a** bank model risk officer, **I want** a Markdown report at `/reports/:runId` that follows SR 11-7 section structure (purpose, model description, developmental evidence, ongoing monitoring, limitations, governance), populated from the run's actual numbers, **so that** I can submit the model for internal model risk committee review.

- **Given** a completed run,
- **When** I open `/reports/:runId`,
- **Then** I see the six SR 11-7 sections rendered, with every numeric field traceable to a Postgres row identifier (click the number, jump to the source).
- **And** a "Download PDF" button produces a portable document format file with the same content.

**Owner:** Measure.

### US-13. Halt certification at a residual red line

**As an** operator or auditor, **I want** Crucible to refuse to issue new clean verdicts when verifier recall on the white-box self-test drops below a configured red line, **so that** the platform does not certify what it cannot defend.

- **Given** verifier recall on the latest white-box pass is below the configured threshold (default 0.7),
- **When** any user opens any dashboard route,
- **Then** a red banner appears at the top reading "Certification halted: recall is X.XX, threshold is Y.YY," with a link to `/metrics`.
- **And** the orchestrator refuses new run-launch requests and returns Hypertext Transfer Protocol (HTTP) 409 Conflict with a typed error body.

**Owner:** Measure.

### US-14. The white-box self-test runs on every pass

**As a** principal scientist reviewing the platform, **I want** every run to include a white-box pass where the red agent is given the verification scheme as input, **so that** the headline catch-rate number is recall-against-an-informed-attacker, never against an ignorant one.

- **Given** a run completes its black-box red and blue rounds,
- **When** the orchestrator transitions to the white-box pass,
- **Then** the red agent's prompt explicitly includes the oracles' protocol descriptions (which checks fire, what relations they check, how the held-out generator is structured),
- **And** the dashboard renders both numbers (black-box catch rate and white-box catch rate) side by side at `/metrics`,
- **And** the gap is reported as a tile of its own.

**Owner:** Red. White-box prompt assembly owned by Targets-and-Oracles.

### US-15. Internal debug route

**As a** developer iterating on a single pillar, **I want** `/admin/debug` to let me jump to any past run's state, flip a mock-LLM mode for local development, and replay any past audit row, **so that** I do not have to re-run the full pipeline to test a fix.

- **Given** I open `/admin/debug`,
- **When** I select a past run and click "Resume at round N",
- **Then** the platform hydrates from the persisted state of that round and continues from there.
- **And** "Mock-LLM mode" toggles the Anthropic client to return canned responses from a fixture directory; the toggle is reflected in the run header banner so it cannot be confused with a real run.

**Owner:** Measure. Mock-LLM mode owned by Orchestrator.

## 4. Out of scope for the two-week build

- Submission portal: producer login, billing, producer-scoped permissions. Post-capstone.
- Research-agent target: shape exists, runtime skipped via `wiring.py`.
- Automated specification compiler (free-form task to obligations).
- Full verifier tournament: learned cheapest-verifier router, hierarchical decomposition, debate escalation, live human-review-budget meter.
- Mobile responsive dashboard. Desktop only for the demo.
- Multi-tenant isolation. Single operator account.

## 5. Rubric-pillar mapping

| Rubric pillar | User stories that advance it | Plan section |
|---|---|---|
| Architecture | US-1, US-7, US-9, US-14 | `plan.md` sections 2 and 3 |
| Scalability | US-2, US-5, US-8 | `plan.md` section 4 |
| Security | US-9, US-13, US-14 | `plan.md` section 5 |
| Testing | US-3, US-4, US-5, US-8, US-10 | `plan.md` section 6 |

`AI_INTERVIEW_PREP.md` cites this table when answering rubric-pillar questions in the AI video interview.

## 6. Demo script, 10 minutes, June 29 2026

Same shape as README section 9, refined.

- **0 to 2 min.** The problem. Two slides: silent wrongness in fraud detection, reward-hacking in code agents. Manual review does not scale.
- **2 to 6 min.** Point the red agent at the fraud detector live. ASR climbs, the reasoning trace scrolls, an evasion lands within the budget. Click the verdict, the Inspect button opens the LLM call trace card showing the exact prompt and the producer's response. Same red agent against the code task, the four oracles plus the judge catch it, US-4 evidence visible.
- **6 to 9 min.** Trigger the blue loop. The proposed patch shows the new features and the adversarial training samples with provenance. The validation runs on held-out attacks and detection recovers. The same attack now gets blocked, demonstrated by replaying it via the `/admin/debug` route.
- **9 to 10 min.** Open `/metrics`. Black-box catch rate, white-box catch rate, and the gap side by side. Open `/corpus` and download the JSONL. Open `/reports/:runId` and show the SR 11-7 report. Close on the halt-certification banner appearing when we deliberately drop the red line.
