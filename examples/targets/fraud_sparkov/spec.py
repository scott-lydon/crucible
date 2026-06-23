"""Load the Sparkov SealedSpec from its co-located YAML declaration."""

from pathlib import Path

from shared.types import SealedSpec, sealed_spec_from_yaml

SPEC_PATH: Path = Path(__file__).resolve().parent / "spec.yaml"


def load_spec() -> SealedSpec:
    """Parse and validate the Sparkov SealedSpec via the shared loader."""
    return sealed_spec_from_yaml(SPEC_PATH.read_text())
