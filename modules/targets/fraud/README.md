# Fraud target

A Shape 1 `Target`: a LightGBM classifier trained on the real Kaggle
credit-card fraud dataset (`mlg-ulb/creditcardfraud`, the ULB data).

## Build the model (real data, no synthetic fallback)

```bash
python scripts/fetch_fraud_dataset.py        # downloads data/creditcard.csv (Kaggle creds in .env)
python -m modules.targets.fraud.train        # trains artifacts/fraud-v1.lgb + .meta.json, prints AUC
```

The raw `data/creditcard.csv` is gitignored (large, license-bound). The trained
`artifacts/fraud-v1.lgb` and its metadata ARE committed, so the app and the test
suite use the real model without re-downloading 150 MB.

## Interface contract

Implements `orchestrator.interfaces.Target`:

- `submit(spec, attack_input) -> TargetOutput`: returns the model's fraud
  probability for a transaction (`{"fraud_probability": p}`, score `p`).
- `query_target(attack_input) -> float`: the probability in `[0, 1]`, the
  first-class probe the red agent calls while searching for an evasion.
- `self_test() -> ProbeResult`: green with the held-out AUC, training time, and
  model checksum; red (not a crash) when the artifact is missing.

A transaction is a dict of the dataset features (`V1`..`V28`, `Time`,
`Amount`); a feature absent from the dict defaults to 0.0, and column order
matches training exactly.

## Done-criterion

The model trains on real Kaggle data with held-out ROC-AUC at or above 0.85
(`tests/integration/test_fraud_target.py`), and `/health/targets/fraud`
returns 200.
