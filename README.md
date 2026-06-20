# Crucible

## The problem

A trained AI model is graded against a *proxy metric*: a validation set,
a benchmark, a unit-test suite, a user-feedback signal, or whatever
scorecard the producer's training process was pointed at. The producer's
training process is an *optimizer*. Optimizers find the cheapest way to
maximize the metric they were given.

When the metric matches the real-world goal perfectly, this is harmless.
When it does not, the optimizer finds the gap and lives in it. The
result is a model that scores high on the metric while silently failing
at the actual job.

Concrete instances of this failure mode:

- A fraud detector that learns "flag transactions in merchant category
  code 5816" because the validation set happened to be heavy in that
  category. It scores 99 percent on the producer's eval and misses
  two-thirds of real fraud in production.
- A code-generation agent that learns to hardcode the visible test
  inputs into a lookup table. It passes the test suite and produces
  broken code on anything new.
- A research agent that learns to fabricate citations because the
  reward signal rewarded "answer that looks sourced" rather than
  "answer that is actually sourced." It sounds authoritative and cites
  papers that do not exist.

The AI safety field has names for this class of failure:

- **Reward hacking** is when an optimizer maximizes the reward signal
  in a way that does not maximize the goal the reward signal was meant
  to capture.
- **Specification gaming** is when a system satisfies the literal
  written specification while violating its intent.
- **Hallucination** is when a generative system produces confident
  outputs that have no grounding in reality.

These failures do not live in a code path. Static analysis, fuzzers,
authentication testers, and secret scanners cannot see them. They live
in the model's output distribution, and they only become visible when
something checks the outputs for correctness on inputs the producer did
not get to choose.

That something is what Crucible is.

## What Crucible does

The producer (the team that trained and submitted the model) hands
Crucible two things: the model itself, and a description of the task it
is supposed to do (example: "given a transaction record, output fraud
or not-fraud"). The producer does **not** pick the test inputs.
Crucible generates fresh inputs on its own, the producer does not see
them, Crucible runs them through the model, and Crucible checks whether
the model's answers are correct.

If the producer were allowed to pick the test inputs, the cheapest
winning move would be to ship a lookup table of memorized answers. An
honest verifier has to control its own inputs.

## Scope: the Integrity pillar

The classical InfoSec triad has three pillars:

| Pillar | Concern |
|---|---|
| **C**onfidentiality | Did secrets leak? |
| **I**ntegrity | Is the output silently wrong? |
| **A**vailability | Is the system up? |

Crucible targets **Integrity**, and only Integrity.

Confidentiality and Availability are out of scope. If your concern is "did
anything leak" or "did the system go down," use the tools built for those
jobs (SAST, DAST, secret scanners, uptime monitors). Crucible will not help.

## Threat model

Three terms, used precisely:

| Term | What it is |
|---|---|
| **Threat** | Silent wrongness introduced by optimization pressure. See the Problem section above. |
| **Attack** | A specific input that surfaces the wrongness at runtime. A fraudulent transaction in an unseen merchant category. A code-generation prompt outside the visible test inputs. A research query whose answer cannot be fabricated. |
| **Red agent** | The component inside Crucible that searches for attacks. LLM-driven adversarial search with a persistent strategy catalog. |

The producer is not assumed to be malicious. The optimization process
itself is what found the cheat; the producer may not even know it is
there. Crucible's job is to surface the failure regardless of intent.

## What Crucible is not

- A SQL injection, XSS, CSRF, or SSRF scanner
- An authentication or authorization bypass tester
- A memory-safety fuzzer
- A secrets-exfiltration or prompt-injection scanner
- An uptime or denial-of-service monitor

For any of the above, use the right tool: Semgrep, CodeQL, Burp, ZAP,
AFL, ASan, OWASP LLM Top 10 tools, your observability stack.

## What Crucible is

A correctness-verification loop with four independent oracles that judge a
submitted AI artifact's output on inputs the producer could not have
memorized. The oracles are non-colluding: each fails differently, so a hack
that fools one is caught by another.

| Oracle | Method |
|---|---|
| Held-out tests | New inputs Crucible generates *after* the model is submitted; the producer has no way to see them in advance |
| Metamorphic relations | Transformations that should not change the verdict |
| Differential oracle | A second implementation from a different model family that must agree |
| Property-based fuzzing | Random inputs against declared invariants |

A small LLM judge contributes one vote in the ensemble. It is not the
authority.

Crucible applies to:

- ML classifiers (fraud detection, anomaly detection, scoring models)
- Code-producing agents (does the generated code actually work on
  unseen inputs?)
- Multi-step research agents (are the answers grounded, or fabricated?)

The interactive architecture website with diagrams, decision tables, and
trade-off panels lives at [`website/index.html`](website/index.html).

## The headline metric

The validation-minus-held-out gap: the proxy reward `R` minus the
ground-truth reward `R*`. This number is the slack a producer learns to
exploit. Crucible's job is to make it small and keep it small.

## In one sentence

Crucible is an Integrity verifier for AI systems, built around the
assumption that the model under test is being adversarially optimized to
look correct without being correct.
