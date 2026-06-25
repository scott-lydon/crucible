# Crucible Reality-Check — 4 questions worth answering honestly

Four plain questions to tell *what we built* from *what we think we built*. For each: what an honest answer sounds like, and a fast way to check. The point isn't to pass — it's to know where the substance is and where the scaffolding is.

---

### 1. If we point Crucible at a target we've never seen, how much do we hand-build before it works — and is the *agent* attacking it, or are *we*?

**Honest answer today:** the harness (the `Target`/`Oracle`/`Adversary` ports + the loop) is shared, but behind each port we hand-build the adapter, the oracle set, and the attack surface — including handing the red a per-target list of what it's allowed to move (`movable_features`). So "target-agnostic" currently means *agnostic plumbing, bespoke attacks*. A genuinely agnostic agent would **discover** the surface by probing the target, not be handed it.

**Check:** `grep -rn "movable_features\|_OP_BUILDERS" modules/ orchestrator/` — if the red is handed the surface per target, that's us attacking, not it.

---

### 2. When the red lands an attack, did the *LLM* actually think of it — or did a deterministic script do the real work while the LLM took the credit?

**Honest answer today:** mostly the script. In a fully-live, LLM-only run the red landed **1** evasion; with the deterministic numeric search it landed **13–19**. The LLM is a strong *strategist* (which feature, why) but a weak one-shot *numeric solver*, and the solver was doing the landing. The fix we're aiming at: LLM picks the vector (visible, credited), a generic solver lands the number (a tool, not a silent stand-in).

**Check:** run the red LLM-only vs deterministic-only and compare `attacks WHERE evaded AND true_label_preserved`. If the LLM alone barely lands, it isn't the engine yet.

---

### 3. Are we catching flaws we genuinely didn't know about — or did we plant the flaw and act surprised when we found it?

**Honest answer today:** in the demo, we plant it — the fraud victim is deliberately built blind to certain signals so the machinery has something to find on a clock. That's a legitimate *demo*, but it is not a *discovery*. The tool's real value is the production case, where nobody knows the blind spots in advance. Say which one you're showing.

**Check:** read `examples/targets/fraud_sparkov/train.py` — if we choose the victim's blind set, the demo flaw is planted by us.

---

### 4. When something "passes," does that mean the AI is actually right — or just that it gamed the checks we let it see / agreed with our own proxy for the truth?

**Honest answer today:** "passes" is only as honest as the **sealed spec** (the answer key we hide from the AI) and how real that spec is. It holds when the producer genuinely can't see the held-back checks (sandbox, no network, Seal Probe proves it) and the ground truth is a real signal — not when the AI can see the checks, or when "correct" is a toy proxy. Knowing the rule is not the same as knowing where this AI is wrong; finding *that* is the whole job.

**Check:** confirm the producer is `--network none` and the Seal Probe shows unreachable (Health page); confirm the ground truth (`reference_model.py`) is trained on real labels with no train/test leakage — not a hand rule like "night = fraud."
