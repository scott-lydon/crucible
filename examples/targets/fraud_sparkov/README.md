# Sparkov fraud victim

A REAL fraud-detection victim wired into Crucible's red/blue loop, built on the
public Sparkov dataset (`fraudTrain.csv` / `fraudTest.csv`).

## Multi-signal, not a 2-feature toy

Every transaction is enriched (`loader.py`) into a RICH, multi-signal record
(`record.py`):

- **Static / contextual**: `amt`, `cat_risk`, `merchant_risk` (per-merchant
  historical fraud rate, computed from the TRAIN split only), `age`, `city_pop`.
- **Behavioral / temporal / geo**: `velocity` (prior same-card transactions
  within a 1-hour window), `hour`, `day_of_week`, `geo_distance_km` (REAL
  haversine between cardholder and merchant).

Three models reason over these signals:

| Model | File | Features | Role |
|-------|------|----------|------|
| **Reference** | `reference_model.py` | full rich set | ground-truth PROXY |
| **Victim** (deployed) | `train.py` | static/contextual only | the flawed detector |
| **Second family** | `second_model.py` | full rich set (IsolationForest) | cross-family second opinion |

## Ground truth is the reference model, not a hand-written rule

The old night-hour heuristic (`hour in {22,23,0,1,2,3} or (cat_risk and amt>250)`)
is **retired**. Ground truth is now the strong multi-signal **reference model**
(`reference_is_fraud`, re-exported as `is_fraud`): a LightGBM trained on the full
rich feature set against the REAL `is_fraud` labels.

- **Reference held-out test AUC ≈ 0.99** — a credible, multi-signal judge of ANY
  transaction (including red-mutated ones), because it weighs many signals rather
  than tripping on one.
- It is a **best-available PROXY for ground truth, not infallible** — we report
  its AUC so its quality is auditable, and `reference_is_fraud` is an operating-
  point decision that can be wrong on individual transactions. This is itself an
  instance of Crucible's thesis: the spec is a proxy for intent; surface the
  residual rather than hide it.

## The exploitable gap

The deployed **victim** uses only the static/contextual signals and is
deliberately **blind** to the behavioral/temporal/geo signals
(`velocity`, `hour`, `day_of_week`, `geo_distance_km`) — a plausible "we never
engineered the behavioral features" gap, not a 2-feature toy. The victim is still
decent on the natural distribution (held-out AUC ≈ 0.98) yet flawed in WHICH
signals it weighs, so:

- The **red loop** lands amount-lowering evasions that preserve the
  reference-model label while the amount-sensitive victim clears them.
- The **differential oracle** catches behavioral anomalies (e.g. high velocity)
  the static-only victim clears but the cross-family IsolationForest flags.
- The **blue loop** recovers by ENGINEERING a blind signal back from the raw
  columns (e.g. extracting `hour` from `trans_date_trans_time`) and retraining.

## Files

- `reference_model.py` — strong multi-signal ground-truth proxy / red-loop `label_fn`.
- `rule.py` — `is_fraud`, delegating to the reference model (stable symbol name).
- `spec.yaml` / `spec.py` — the SealedSpec (invariant + metamorphic relation).
- `train.py` — rebuilds the deployed (behavior-blind) victim from the REAL CSVs.
- `second_model.py` — the cross-family IsolationForest over the full rich set.
- `loader.py` — verified CSV load + ALL derived rich features.
- `generator.py` — deterministic class-balanced batch over the real test data.
- `raw_surface.py` — the raw column surface + engineered-retrain hook for blue.
- `constants.py` — feature sets, thresholds, and paths.

## Rebuilding the artifacts

The CSVs (`data/*.csv`) and the model artifacts (`artifacts/*.pkl`) are gitignored
external inputs. Place the verified CSVs under `data/`, then:

```bash
python -m examples.targets.fraud_sparkov.reference_model   # ground-truth proxy
python -m examples.targets.fraud_sparkov.train             # deployed victim
python -m examples.targets.fraud_sparkov.second_model      # cross-family model
```

Each serializes the bare LightGBM `Booster` (not the sklearn `LGBMClassifier`
wrapper) so the generic `LocalModelTarget` scores plain feature vectors without
sklearn's cosmetic "X does not have valid feature names" warning.
