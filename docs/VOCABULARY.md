# Vocabulary

This file pins down the terms that recur across `coding-practices.md`, `acceptance-tests.md`, `ARCHITECTURE.md`, `tasks.md`, `QA_ADVERSARY.md`, `README.md`, and the design brief. The same English word can mean different things depending on which target Crucible is running against, which is the single biggest source of misreading on first contact with the docs.

If you read a sentence in a foundational artifact and the meaning of "model" or "retrain" is not obvious from the surrounding paragraph, that sentence is a bug. Open a pull request and pin the term to one of the entries below.

## Crucible is not what it verifies

**Crucible does not detect fraud.** Crucible verifies that AI systems are doing what they claim to do. The fraud-detection example is one of three target adapters; it was picked because the Kaggle credit-card dataset is public, banks have explicit Supervisory Letter 11-7 (SR 11-7) governance, and the failure mode "scores high on the proxy metric and misses real fraud" is concrete enough to demo. In a production deployment of the fraud target, the LightGBM classifier catches fraudulent transactions on a card swipe (its job). Crucible catches that classifier being silently wrong about a transaction (Crucible's job). Crucible never sits on the production decisioning path; the operator runs Crucible against the classifier in a lab pass and reads the report.

The same shape holds for the code-agent target. The code agent generates code (its job). Crucible catches the code agent reward-hacking the test suite, hallucinating an import, or skipping a required obligation in the sealed specification (Crucible's job).

## "Target" and "producer"

**Target** and **producer** are the same thing in this codebase: the system under verification. Both terms are used because they each carry a different connotation that is useful in the right context. Use "target" when emphasizing that this is the AI system Crucible attacks. Use "producer" when emphasizing that this is the AI system that produces output for the oracles to check.

A target / producer is NEVER: Crucible itself, the oracles, the red agent, the blue agent, the orchestrator, or any of Crucible's own internal LLM calls.

## Target shapes — Shape 1 and Shape 2

Crucible verifies two architectural shapes of AI system. The same Target Protocol covers both, and the same red, blue, and measure pillars run against both, but several behaviors (what "model" refers to, what "retrain" does, what hardening can touch) differ by shape. Naming the shape explicitly removes the ambiguity.

### Shape 1 — Smaller custom machine-learning model the customer owns

A supervised or unsupervised ML model the customer trained themselves on data they own, with weights they can hold in their hand. The fraud LightGBM classifier in `modules/targets/fraud/` is the example shipping in the two-week build. Other systems that fit this shape: credit scorers, churn predictors, anomaly detectors, content moderation classifiers, medical triage scorers, insurance underwriting models, demand forecasters. None are large language models. Persistence is a versioned weight file at `artifacts/fraud-vN.lgb` (or the equivalent for other Shape 1 systems).

For Shape 1, "model" means this trained classifier. "Retrain" means running a fresh `LGBMClassifier.fit(...)` pass and emitting a new versioned weight file. The customer owns everything end to end (data, features, training pipeline, weights).

### Shape 2 — Agent product built on a vendor language model

An agent loop the customer built, wrapping a vendor large language model the customer rents (Anthropic Sonnet 4.6, OpenAI GPT-equivalent, Google Gemini-equivalent). The code-generation agent in `modules/targets/code_agent/` is the example shipping in the two-week build. Other systems that fit this shape: code-review bots, customer-service chatbots, research assistants, retrieval-augmented Q&A systems, internal-knowledge agents, document-extraction agents. Persistence is the agent's prompts, guardrails, configuration, and any orchestration logic — never the vendor language model's weights.

For Shape 2, "model" almost always means the agent's prompts and configuration, NOT the vendor language model. "Retrain" is a misnomer for this shape; the operation is a reviewable patch against the prompts and configuration emitted to a new `agent_configs` row. The vendor language model is never modified by Crucible because the customer does not own it.

### Why the distinction matters in the docs

A sentence about "the model" is ambiguous unless the reader knows which shape is in play. Throughout `README.md`, `coding-practices.md`, `acceptance-tests.md`, `ARCHITECTURE.md`, `tasks.md`, and `QA_ADVERSARY.md`, sentences that apply to only one shape should name it (e.g., "the Shape 1 fraud LightGBM classifier" or "the Shape 2 code agent's prompts and configuration"). Sentences that genuinely apply to both shapes can use "the target" or "the AI system." Sentences that use "the model" without a shape qualifier are bugs and should be tightened.

## "Model" — three different referents

The word "model" alone is ambiguous. Use one of these specific terms:

### The fraud LightGBM classifier

The supervised classifier Crucible attacks in the fraud target adapter. A tree-based gradient-boosting model trained on the Kaggle credit-card fraud dataset, serialized as `artifacts/fraud-vN.lgb` where N is the version integer. Classical machine learning, not a large language model. Defined in `modules/targets/fraud/` per `ARCHITECTURE.md` section 3.

### The code agent (prompts, guardrails, config)

The code-agent target adapter. It is an agent loop wrapping a vendor language model (Anthropic Sonnet 4.6 via the Anthropic Software Development Kit). The "model" for blue-loop purposes is the agent's prompts, guardrails, and configuration, NOT the vendor language model's weights. Crucible never touches the vendor language model. Defined in `modules/targets/code_agent/` per `ARCHITECTURE.md` section 3.

### Crucible's internal LLMs

The Anthropic Claude models that Crucible calls for its own reasoning: Sonnet 4.6 for the red and blue inner loops, Opus 4.8 for the judge oracle and the white-box self-test pass. These are infrastructure. They are never targets. Crucible never retrains them. Per `coding-practices.md` section 1.

When you write "the model" in a doc, the reader will most likely assume one of these three. If you do not know which one your sentence means, name it explicitly.

## "Retrain" — two different operations

The word "retrain" alone is ambiguous. The Blue pillar's `retrainer.py` does one of two things depending on the target adapter.

### Retrain the fraud LightGBM classifier

For the fraud target, "retrain" means a single-machine training pass: load the original Kaggle dataset plus the new adversarial training samples the proposer wrote, run `lightgbm.LGBMClassifier.fit(...)` with the new feature set, serialize the result as `artifacts/fraud-vN.lgb` at the next version integer, and write a row to the `model_versions` table. This is a bounded operation that takes minutes on a single CPU.

This is NOT pretraining a large language model. This is NOT fine-tuning a foundation model. This is the same retrain operation a bank's model risk team runs when they refresh their fraud scorer with last quarter's labeled data.

### Patch the code agent

For the code-agent target, "retrain" is a misnomer; the operation is a patch against the agent's prompts, guardrails, and configuration. The proposer writes a reviewable diff; `retrainer.py` applies the diff and emits a new versioned agent config row, never new weights. The vendor language model the agent talks to (Sonnet 4.6) is never touched.

In the `/blue/:patchId` dashboard route, the diff view shows prompt deltas for the code-agent target and feature-and-sample deltas for the fraud target. Same route, different rendering, both honest about what they changed.

## "Catch" and "catch rate"

These terms are about Crucible's own correctness, NOT the target's production correctness.

When Crucible "catches" something, it catches the producer being wrong about its job. The fraud LightGBM classifier missed a fraudulent transaction in a held-out test; the oracles surface it; Crucible "caught" the producer's miss.

When the dashboard reports "catch rate," it means: of the producer outputs the oracles examined in this run, what fraction did the verification ensemble correctly identify as violating the sealed specification.

When the README says "the platform measures its own catch rate against an adversary that already knows the verification scheme," it means: when the red agent is given the oracles' protocol descriptions as input (the white-box pass), what fraction of producer wrongness do the oracles still surface. This is the headline number on `/metrics`.

"Catch rate" never means: the fraud classifier's production catch rate on real card swipes; the agent vendor's customer-side success rate; any metric of the target's production behavior. The target's own performance against its own metric is not something Crucible reports.

## "Producer wrongness"

A producer is "wrong" when its output violates an obligation in the sealed specification. For the fraud target, a missed fraudulent transaction is producer wrongness. For the code-agent target, code that passes the visible tests but violates a stated invariant or hardcodes a branch for exactly the visible inputs is producer wrongness. The oracles independently check the producer's output against the spec's obligations; an oracle that fires is asserting producer wrongness.

## "Undetected-hack rate" and "undetected-evasion rate"

The complement of catch rate. The fraction of producer wrongness Crucible's oracles missed. This is what an external auditor will multiply by the volume of real-world inputs to estimate harm exposure.

## "Verifier recall"

Recall of the oracle ensemble as a verifier. Measured on a seeded-hack corpus where the ground truth (which outputs are producer-wrong) is known. The halt-certification rule reads `metrics.recall_white_box` and refuses new clean verdicts when the value drops below the configured red line. Per `acceptance-tests.md` US-13.

## "Sealed specification" or "sealed spec"

The YAML document the operator pastes into the Run Launcher that defines the target's obligations and invariants. Stored in Postgres `specs` table after submission. "Sealed" means the producer container has no access to it: oracles read the spec through a server-side resolver the producer cannot reach. Per `ARCHITECTURE.md` section 11 (the core bet) and section 3.

A sealed spec is NOT: the user's prompt to the producer at runtime, the producer's training data, or any artifact the producer can introspect.

## "White-box self-test"

A red-and-blue pass run with the red agent's prompt augmented to include the oracles' protocol descriptions (which checks fire, what relations they check, how the held-out generator is structured). The catch rate the oracles achieve on this pass is the report-card number. A high white-box catch rate means the oracles work because of their design, not because the red agent was uninformed. Per `ARCHITECTURE.md` section 11 and `acceptance-tests.md` US-14.

This term is NOT a synonym for "open-source" or "transparent oracles in general." It is a specific run mode with a specific augmented red prompt.

## "Held-out attacks"

An attack set defined before the blue pass starts and never seen by the proposer or the retrainer. The held-out validator (`modules/blue/holdout_validator.py`) evaluates the post-retrain producer against this set so the recovered detection rate is not a memorization artifact. Per `ARCHITECTURE.md` section 3 Pillar 3.

If the proposer or retrainer ever sees the held-out attacks, the orchestrator refuses to apply the patch and returns a typed error. Per `acceptance-tests.md` US-7.

## "Adapter"

A thin wrapper that maps Crucible's `interfaces.Target` Protocol onto one specific kind of target system. Three adapters live in `modules/targets/`: `fraud/`, `code_agent/`, and `research_agent/` (stubbed for the two-week build). Adapters are how "target-agnostic by design" is realized in code. Per `coding-practices.md` section 2 and `ARCHITECTURE.md` section 2.

An adapter is NOT a target type itself. The fraud target is a LightGBM classifier; the adapter is the Python shim that exposes that classifier through the Target Protocol.

## How to extend this file

When a new term causes confusion in a pull request, code review, or interview, add it here in the same shape: a definition, an "is NOT" clause that names the most common misreading, and a citation to the foundational artifact that owns the term. Do not let umbrella nouns ("system", "platform", "framework", "loop") accumulate without a referent.
