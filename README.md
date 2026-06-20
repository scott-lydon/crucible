# Crucible

Crucible verifies that an AI model is actually doing its job, not just scoring
high on the test it was graded on.

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

The attacker is not a network intruder. The attacker is an **optimizer**:
the model's training process, an agentic system iterating on its own outputs,
or a human producer chasing a benchmark. Any of them can find outputs that
score high on a proxy reward while failing the actual goal. The AI safety
field calls this *reward hacking*, *specification gaming*, or *hallucination*
depending on the shape it takes.

A fraud detector that misses 69 percent of real fraud is, operationally,
identical to a database whose values were silently tampered with. The data
flowing downstream is wrong, the code consuming it trusts it, the same
class of harm follows. Same Integrity failure, different attacker.

Traditional security tooling does not look here, because the failure does
not live in a code path. It lives in the model's output distribution.

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
| Held-out tests | New instances generated *after* submission, never exposed to the producer |
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
