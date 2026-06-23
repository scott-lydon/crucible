# Sparkov fraud victim

A REAL fraud-detection victim wired into Crucible's red loop. The detector is a
LightGBM classifier trained on the public Sparkov `fraudTrain.csv`, deliberately
restricted to the proxies `amt` + `cat_risk` (no hour, no distance) so it stays
accurate on the natural distribution (held-out AUC ~0.97) yet is blind to
amount-lowering on night-driven frauds — the exploitable gap the red loop
attacks.

## The declared rule is a deliberately simplified PROXY for ground truth

The declared ground-truth rule (`rule.py` `is_fraud`) is:

```
is_fraud = (hour in {22,23,0,1,2,3})        # night-hour, ANY amount
           OR (cat_risk == 1 AND amt > 250) # high amount in a risky category
```

This rule is **a deliberately simplified ground-truth PROXY, not the real fraud
labels**:

- **High recall (~95%) vs the real labels** — it catches 95.3% of the rows the
  real dataset marks `is_fraud`.
- **Low precision (~2%)** — it over-flags night-hour transactions, so its
  positive set is only ~30% real fraud at best. The night window genuinely
  carries a 17x-elevated fraud rate, but the *base* rate is still low, so a
  flag-all-night rule sweeps in many legitimate transactions.

### What the co-evolution numbers therefore mean

The co-evolution **gap** this harness reports measures **recall loss against the
DECLARED spec** — how many transactions the declared rule calls fraud that the
attacked detector lets through. It is **NOT** a measure of catch rate against
real fraud. The headline numbers (detection falls, evasion climbs, gap > 0) are
honest *about the declared spec*; do not read them as "the detector misses N%
of real fraud."

### Why this is intentional, not a bug

This proxy-imperfection is itself an instance of Crucible's core thesis: **the
spec is a proxy for intent, and the residual between proxy and intent must be
surfaced, not hidden.** A clean interpretable rule can be far higher-recall than
the noisy real labels while being far lower-precision; the gap between "what the
spec says fraud is" and "what fraud actually is" is exactly the residual the
harness exists to make visible. Surfacing it here — in committed, visible files
rather than a buried report — is the point.

## Files

- `rule.py` — the declared ground-truth rule / red-loop `label_fn`.
- `spec.yaml` / `spec.py` — the SealedSpec (invariant + metamorphic relation).
- `train.py` — rebuilds the flawed detector artifact from the REAL CSVs.
- `loader.py` — verified CSV load + derived interpretable features.
- `generator.py` — deterministic class-balanced batch over the real test data.
- `constants.py` — thresholds and paths, all derived from the Step-1 analysis.

## Rebuilding the artifact

The CSVs (`data/*.csv`) and the model artifact (`artifacts/*.pkl`) are
gitignored external inputs. Place the verified CSVs under `data/`, then:

```bash
python -m examples.targets.fraud_sparkov.train
```

`train.py` serializes the bare LightGBM `Booster` (not the sklearn
`LGBMClassifier` wrapper) so the generic `LocalModelTarget` can score plain
feature vectors without sklearn's cosmetic "X does not have valid feature names"
warning.
