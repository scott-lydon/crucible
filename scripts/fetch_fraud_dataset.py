#!/usr/bin/env python3
"""Fetch and checksum the fraud dataset.

Source is the ULB Credit Card Fraud dataset via the OpenML mirror (data_id 1597) —
the same data as the Kaggle set, without requiring Kaggle credentials. Writes
``data/creditcard.csv`` (gitignored) and prints its shape and sha256.
"""

from __future__ import annotations

import hashlib

from modules.targets.fraud.data import CSV_PATH, load_dataframe


def main() -> int:
    frame = load_dataframe()
    digest = hashlib.sha256(CSV_PATH.read_bytes()).hexdigest()
    print(f"rows={frame.shape[0]} cols={frame.shape[1]} path={CSV_PATH}")
    print(f"sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
