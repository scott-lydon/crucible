# Crucible Reality-Check — "what we think we built" vs "what we actually built"

A pointed self-audit so the team can separate the *claims* (target-agnostic, LLM-driven, finds the unknown) from the *implementation* (ports + bespoke adapters, LLM + deterministic solvers, planted demo flaws). Every question has a **How to check**, an **Honest green**, and a **Red flag**. Run them against `feat/critical-path`. None of these are "gotchas" — they're the questions that keep us honest.

> Origin: these came out of a session of hard operator questions. The uncomfortable answers we already found are noted inline as **[found]**.

---

## 1. Target-agnosticism: a shared *port*, or a real *driver*?

1. **When we add a brand-new target, what must we hand-write?**
   - *Check:* list everything bespoke for one target under `examples/targets/<t>/` + its oracle wiring in `orchestrator/wiring.py` (`build_components_<t>`). Count files/lines.
   - *Green:* a thin adapter + a spec; oracles + attack surface are reused generically.
   - *Red flag:* you hand-build the feature set, the attack surface, the oracle set, and the measurement per target. **[found: today it's "agnostic ports + bespoke per-target everything." The agnosticism is the `Target`/`Oracle`/`Adversary` Protocols; behind each port is hand-built.]**

2. **Does the red get *handed* its attack surface, or *discover* it?**
   - *Check:* `grep -rn "movable_features\|levers\|_OP_BUILDERS" modules/ orchestrator/ examples/`.
   - *Green:* the agent probes the target to learn what to move.
   - *Red flag:* we pass a per-target `movable_features`/lever list. **[found: yes, we hand it `movable_features` per target.]**

3. **Are the "generic" oracles actually generic?**
   - *Check:* `grep -rniE "sparkov|fraud|amt|hour|code_|is_palindrome" modules/oracles/` — a generic oracle should return nothing.
   - *Green:* oracle modules contain zero target words; everything flows in via the `SealedSpec` as data.
   - *Red flag:* a "generic" oracle hardcodes a target's fields.

4. **Could the harness attack a target we did NOT pre-wire an attack surface for?**
   - *Check:* run `modules/red/meta/test_adversary.py` (the meta-attacker) against a second target.
   - *Green:* yes — the meta-attacker introspects fields + writes its own attack.
   - *Red flag:* it only works where we declared the surface. **[found: the meta-attacker is a prototype; it writes its own code but doesn't reliably *land* yet — see §2.]**

---

## 2. LLM-driven, or deterministic scripts wearing an LLM coat?

5. **In a LIVE run, what share of *landed* attacks did the LLM actually author vs a deterministic script?**
   - *Check:* run with the LLM only, then deterministic only; compare evasion counts (`attacks WHERE evaded AND true_label_preserved`).
   - *Green:* the LLM lands a meaningful share on its own.
   - *Red flag:* the deterministic solver does ~all the landing. **[found: pure-LLM landed **1**; the hybrid (LLM + deterministic ladder) landed **13–19**. The deterministic numeric search was doing the heavy lifting.]**

6. **Is there a *silent* fallback from LLM → deterministic?**
   - *Check:* `grep -rn "fallback\|HybridAdversary" modules/red/ orchestrator/wiring.py`; read the conditions.
   - *Green:* no silent swap; if a deterministic tool is used, each attack records *which* engine produced it (provenance).
   - *Red flag:* on budget exhaustion the loop silently finishes on scripted mutations passed off as the model's. **[found + fixed: removed the silent budget-fallback; live is LLM-only. But that exposed §5 — pure-LLM is weak.]**

7. **What does the LLM uniquely add over the deterministic baseline?**
   - *Check:* diff the *tactics* each produces (the strategy catalog) and whether the LLM finds non-obvious multi-feature vectors a ladder can't.
   - *Green:* the LLM finds novel, semantically-valid vectors; the solver only handles numeric precision.
   - *Red flag:* the LLM proposes a direction the ladder would've found anyway, then the ladder lands it — the LLM is decoration.

8. **Per-attack provenance: can you tell who produced each attack?**
   - *Check:* inspect `attacks.mutation_json` — is there a rationale (LLM) vs none (script), and an explicit engine label?
   - *Green:* every attack is attributable.
   - *Red flag:* you cannot tell LLM attacks from scripted ones after the fact.

---

## 3. Is the "intelligence" discovered, or staged?

9. **Did the platform *discover* the victim's flaw, or did we *plant* it?**
   - *Check:* read `examples/targets/fraud_sparkov/train.py` — is the victim deliberately blind to a known signal set?
   - *Green (for a demo):* planted, and we *say so*.
   - *Red flag:* we present a planted flaw as a discovery. **[found: we deliberately build the victim blind to {velocity, hour, day_of_week, geo}. That's a demo necessity — be explicit that production is the unknown-flaw case.]**

10. **Does blue *discover* the missing signal, or get nudged to it?**
    - *Check:* read the blue engineer prompt — does it name the answer?
    - *Green:* blue reasons from raw columns to the signal.
    - *Red flag:* the prompt hands it "engineer the hour feature."

11. **Does the red find *novel* attacks or replay one known move?**
    - *Check:* the strategy catalog tactics across a run.
    - *Green:* varied, multi-feature, surprising vectors.
    - *Red flag:* every "attack" is `amt:down`.

---

## 4. Are the numbers honest?

12. **Every dashboard number from real persisted rows?**
    - *Check:* trace each metric to a SQL row; look for computed/defaulted values.
    - *Green:* honest empty-states ("Not yet measured"), never a fabricated 0.

13. **Is the ground truth a real signal or a toy proxy — and is it leak-free?**
    - *Check:* `reference_model.py` — trained on real labels? `merchant_risk`/aggregates fit on TRAIN split only? AUC reproducible? **[found: reviewed leak-free; AUC 0.987 reproduced.]**
    - *Red flag:* a hand rule like "night = fraud" (~2% precise) standing in for truth, or test labels leaking into a feature.

14. **What does the headline metric's denominator actually measure?**
    - *Check:* `modules/measure/` — is "catch rate" vs real failures, or recall against a proxy spec?
    - *Red flag:* a big number that measures agreement with our own proxy, not real-world correctness.

15. **Does "complete" mean the whole arc ran?**
    - *Check:* did blue actually run + persist a row, or did a phase silently skip while status read `complete`?
    - *Green:* terminal status set only after red→verify→measure→blue all finish. **[found + fixed: blue used to silently skip (OOM) while status said complete.]**

---

## 5. Sealed-spec integrity

16. **Is the spec genuinely hidden from the producer?**
    - *Check:* the producer runs in `--network none`; the Seal Probe proves it can't reach the spec store (ENETUNREACH, not DNS).
    - *Green:* proven unreachable on the Health page.

17. **Could the held-back answers leak anywhere the producer can read?**
    - *Check:* are sealed held-out tests/answers ever written into a row/file the producer could see?
    - *Red flag:* held-out answers persisted into the same `transactions.features_json` the producer's lineage touches. **[found: noted — held-out cases land in `features_json`; harmless today (producer has no DB access) but airtighten before any producer gains DB visibility.]**

---

## 6. The north-star gap (be honest about ambition)

18. **Is the genuinely-agnostic engine (red writes/discovers its own attacks for any target) real, or aspirational?**
    - *Green:* a meta-attacker that probes a new target, strategizes, and lands — proven live.
    - *Red flag:* "target-agnostic" means "we wrote an adapter per target." **[found: the write-its-own-code meta-attacker is a prototype that doesn't reliably land; the achievable synthesis is *discover (probe) → strategize (LLM) → solve (numeric)*, not yet built as default.]**

---

### How to use this
Pick a claim we make in the README/demo ("target-agnostic", "LLM-driven adversarial search", "finds silent failures"), run the matching checks, and write the honest answer next to it. The goal isn't to pass — it's to know exactly where the substance is and where the scaffolding is, so we build the substance on purpose.
