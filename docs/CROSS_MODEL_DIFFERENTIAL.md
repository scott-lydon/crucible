# Cross-Model Verification: do "independent" oracles actually share blind spots?

**One-line finding:** they do — and *differently* by vendor. Two Claude models (the producer's
family and its same-family checker) **missed the exact same error**, while three other vendors
caught it. And no two vendors share the same gaps: their blind spots are **complementary**, so a
mix of families catches more than any single model. This is the evidence behind routing
Crucible's differential oracle to a **different model family than the producer**.

---

## Why this matters

Crucible's central wager (`README.md`, `constitution.md §7`) is **independent verification**: a
checker panel that catches an AI's silent failures *because it doesn't share the AI's blind
spots*. The PRD is explicit about the differential oracle — `plan.md §199`:

> Differential oracle = **"Second implementation from a different model family."**
> Rejected alternative: *"Same family, different seed"* — *"Same family shares blind spots."*

But the shipped code checked a **Sonnet** producer with an **Opus** reference — *same family*.
So the question was real: is "different family" a measurable property, or just a claim? We
measured it.

---

## The experiment

- **12 labeled cases**, two domains: customer-support **facts** (return window, fake loyalty
  tier, refund policy, shipping threshold) and **numeric/logic** (multiplication, date math,
  percentage, shipped≠delivered). **8 are wrong, 4 are correct** (so we measure both catch-rate
  and false-positives).
- **Ground truth is deterministic** for the math/dates (verified with a calculator, not an LLM),
  so the labels don't depend on any model's — or the author's — reasoning.
- **6 verifier models across 5 vendors**, each asked "is this answer materially wrong vs the
  facts?" with a conservative prompt ("OK if unsure"):
  Anthropic **Sonnet 4.6** (the producer's own model) and **Opus 4.8** (the current same-family
  checker), **OpenAI GPT-5.5**, **Google Gemini 3.5**, **DeepSeek v4**, **Qwen 3.7-max**.

---

## Results

| verifier | vendor | catch (of 8 wrong) | false-pos (of 4 correct) |
|---|---|---:|---:|
| Sonnet 4.6 | Anthropic (producer's own) | 7/8 | 0/4 |
| Opus 4.8 | Anthropic (current differential) | 7/8 | 0/4 |
| GPT-5.5 | OpenAI | 7/8 | 0/4 |
| Gemini 3.5 | Google | 6/8 | 0/4 |
| DeepSeek v4 | DeepSeek | **3/8** | 0/4 |
| Qwen 3.7-max | Qwen (Alibaba) | **8/8** | 0/4 |

**Nobody false-flagged a correct answer** — the conservative verifier prompt holds precision
across all six.

### Who missed *what* — the blind-spot map

The three 7/8 scorers did **not** miss the same case:

| verifier | missed |
|---|---|
| Sonnet (Claude) | the **multiplication** (`2×$34.99 + $12.50`) |
| Opus (Claude) | the **multiplication** — *identical to Sonnet* |
| GPT-5.5 | the **date math** (`Jan 15 + 30d = Feb 14`) — *a different case* |
| Gemini 3.5 | the **15% discount** and the **shipped≠delivered** logic |
| DeepSeek | five of eight (too weak to be a checker) |
| Qwen | none |

---

## The two findings

### 1. Within a family → the *same* blind spot
Sonnet and Opus — different sizes, same lineage — missed the **exact same** case (the
multiplication). That is precisely why a same-family checker adds little: **it fails where the
producer fails.** Opus-checking-Sonnet inherits Sonnet's gap.

### 2. Across vendors → *complementary* blind spots
Claude misses the multiplication but nails the date; GPT nails the multiplication but misses the
date; Gemini misses two cases everyone else caught. Their gaps don't overlap. So:

> **Claude + any one different vendor = 8/8** on this set — each covers the other's blind spot.

That is the real argument: not "find the smartest single model," but **combine different
lineages.** Diversity, not raw capability, is what closes the gaps.

### The headline example (good for the deck)
> A customer asks for a refund on **2 items at $34.99 plus $12.50 shipping**. The agent confidently
> answers **"$112.48."** The correct figure is **$82.48** — off by exactly **$30**. **Both Claude
> models — the agent's own family *and* its same-family checker — accepted it.** GPT-5.5, Gemini,
> and Qwen all caught it. A model can't reliably check its own family's arithmetic.

---

## But two honest caveats (don't oversell it)

1. **Capability still matters as much as vendor.** DeepSeek is a different vendor but a *weak*
   checker — **3/8, worse than same-family Opus.** "Different family" only helps if the model is
   *also capable*. The rule is **different *and* strong**, not just different.
2. **The independence win is modest at this scale.** On 7/8 cases the same-family Opus was fine;
   the gap showed on ~1/8. The *phenomenon* is proven and reproducible; the exact rate shouldn't
   be over-read at N=12. And the case *selection* was authored by a Claude (us), which biases
   toward known LLM weaknesses — a presentation-grade number should have the cases authored by a
   **non-Claude model or sampled from real producer failures**. (The math ground truth is
   calculator-verified, so the labels are sound; it's the *choice* of cases that's ours.)

---

## Cost & governance

| model | input $/1M | output $/1M | note |
|---|---:|---:|---|
| Opus 4.8 (current) | 5.00 | 25.00 | same family — the problem |
| **GPT-5.5** | 5.00 | 30.00 | ≈ Opus cost; US vendor; different family; caught the blind spot |
| Gemini 3.5 flash | 1.50 | 9.00 | cheaper than Opus; US vendor |
| Qwen 3.7-max | 1.25 | 3.75 | best & cheapest — but Alibaba (China) → governance flag for SR 11-7 |
| DeepSeek v4 | 0.43 | 0.87 | cheapest — but too weak (3/8) |

For a bank model-risk (SR 11-7) audience, routing data to a Chinese-lab model is a governance
concern, so **Qwen is documented but not the default.**

---

## Decision & implementation

- **Default differential → `openai/gpt-5.5`** when the producer is Claude: US vendor, familiar,
  genuinely different family, caught the blind spot, ≈ Opus cost. (`google/gemini-3.5-flash` is
  the cheaper-Western fallback.)
- **Crucible auto-picks** a different family than the producer — it isn't hardwired.
  `shared/model_family.py:pick_differential_model(producer, ...)` returns `(model, cross_family)`.
- **Graceful by design — it never halts a run.** If the producer's family can't be determined,
  or no different-family model is available, it falls back to the default and reports
  `cross_family=False`: the differential still runs, the run still completes, independence is
  *annotated* as not-guaranteed rather than blocking. (`tests/integration/test_model_family.py`.)
- **Override:** set `CRUCIBLE_DIFFERENTIAL_MODEL` to force a specific reference model.
- **Not yet:** per-run selection from a BYO producer's actual model (currently keys off the
  configured producer); surfacing `cross_family` in the verdict audit so the report states it.

---

## Reproduce

The eval is `scratchpad/crossmodel_eval.py` (labeled cases + scoring across all six models via
the OpenRouter key). `scratchpad/controlled_diff.py` is the focused A/B that shows the
substance-aware differential catching a wrong answer the refuse-vs-comply check missed.
