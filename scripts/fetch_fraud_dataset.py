#!/usr/bin/env python3
"""Download the real Kaggle credit-card fraud dataset into data/.

Authenticates with the Kaggle API using KAGGLE_USERNAME plus KAGGLE_KEY (or
KAGGLE_API_TOKEN as the key), read from the environment or the gitignored
.env. Downloads mlg-ulb/creditcardfraud and unzips creditcard.csv. No
synthetic fallback: if credentials are missing or the download fails, it
raises a typed, explanatory error.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DATA_DIR = _REPO_ROOT / "data"
_CSV_PATH = _DATA_DIR / "creditcard.csv"
_DATASET = "mlg-ulb/creditcardfraud"


def _ensure_credentials() -> None:
    """Populate KAGGLE_USERNAME and KAGGLE_KEY, accepting KAGGLE_API_TOKEN as the key."""
    load_dotenv(_REPO_ROOT / ".env")
    if not os.environ.get("KAGGLE_KEY"):
        token = os.environ.get("KAGGLE_API_TOKEN")
        if token:
            os.environ["KAGGLE_KEY"] = token
    if not os.environ.get("KAGGLE_USERNAME") or not os.environ.get("KAGGLE_KEY"):
        raise RuntimeError(
            "Kaggle credentials missing. The Kaggle library needs both a username "
            "and a key. Set KAGGLE_USERNAME and KAGGLE_KEY (or KAGGLE_API_TOKEN) "
            "in .env, then retry."
        )


def fetch() -> Path:
    """Download and unzip creditcard.csv into data/, returning its path."""
    _ensure_credentials()
    # Imported here so the module loads without the kaggle dependency present.
    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    api.authenticate()
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    api.dataset_download_files(_DATASET, path=str(_DATA_DIR), unzip=True)
    if not _CSV_PATH.exists():
        raise RuntimeError(
            f"Kaggle download finished but {_CSV_PATH} is missing. Check the "
            f"dataset slug {_DATASET!r} and that the account accepted its terms."
        )
    return _CSV_PATH


def main() -> None:
    path = fetch()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f"downloaded {path} ({path.stat().st_size} bytes) sha256={digest}")


if __name__ == "__main__":
    main()
