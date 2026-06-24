"""US-1 input side: the operator selects a target + pastes/edits the sealed spec,
and the backend accepts, seals, and runs the oracles against THAT spec.

All offline: synth target over in-memory SQLite, ZERO real LLM calls.
  * ``GET /targets`` lists the real bundled adapters (not a hardcoded frontend list).
  * ``GET /targets/{name}/spec`` returns the default YAML; 404 on an unknown target.
  * ``POST /runs`` with a CUSTOM valid spec -> 201 AND the run's oracles enforce the
    custom obligation (a custom must-flag invariant changes verdicts vs the default).
  * ``POST /runs`` with an INVALID spec -> 422 typed error naming the problem.
  * blank/absent spec -> falls back to the target's default.
"""

from collections.abc import AsyncGenerator, Mapping, Sequence
from typing import cast

import pytest
import yaml
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from orchestrator.api import app, init_db
from orchestrator.db import session_factory
from orchestrator.targets_registry import default_spec_yaml
from shared.persistence.models import SpecRow


def _invariant_names(spec_json: Mapping[str, object]) -> set[str]:
    """The invariant names declared in a stored spec_json (typed-narrowing helper)."""
    invs = cast(Sequence[Mapping[str, object]], spec_json["invariants"])
    return {cast(str, inv["name"]) for inv in invs}


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    await init_db("sqlite+aiosqlite:///:memory:")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


async def test_targets_lists_real_bundled_adapters(client: AsyncClient) -> None:
    r = await client.get("/targets")
    assert r.status_code == 200
    targets = r.json()["targets"]
    by_name = {t["name"]: t for t in targets}
    # The real registry: sparkov (serialized LightGBM victim) + synth (in-process).
    assert {"sparkov", "synth"} <= set(by_name)
    assert by_name["sparkov"]["kind"] == "fraud"
    assert by_name["sparkov"]["model_artifact_ref"].endswith(".pkl")
    assert by_name["sparkov"]["has_default_spec"] is True
    # Synth honestly reports its in-process detector, not a faked artifact file.
    assert "in-process" in by_name["synth"]["model_artifact_ref"]


async def test_target_spec_returns_default_yaml(client: AsyncClient) -> None:
    r = await client.get("/targets/synth/spec")
    assert r.status_code == 200
    # Byte-identical to the registry default + parses to a valid spec mapping.
    assert r.text == default_spec_yaml("synth")
    loaded = yaml.safe_load(r.text)
    assert loaded["target_kind"] == "fraud"
    assert isinstance(loaded["invariants"], list)


async def test_target_spec_unknown_target_404(client: AsyncClient) -> None:
    r = await client.get("/targets/nope/spec")
    assert r.status_code == 404


async def _fail_weight_total(client: AsyncClient, run_id: str) -> float:
    """Sum of fail_weight across a completed run's verdicts (more obligations
    violated => strictly larger total)."""
    body = (await client.get(f"/runs/{run_id}/verdicts")).json()
    return float(sum(v["fail_weight"] for v in body["verdicts"]))


async def test_post_run_custom_spec_changes_verdicts(client: AsyncClient) -> None:
    """A pasted spec genuinely changes the obligations the oracles enforce.

    The custom spec adds a ``must_flag_when amount >= 0`` invariant — true for
    EVERY synth transaction — so the InvariantOracle FAILS every cleared sample,
    strictly increasing the run's total fail_weight vs the default spec (whose
    invariant only fires on country_mismatch + high velocity). Same target, seed,
    and batch: the ONLY difference is the operator-supplied spec.
    """
    base = {"target": "synth", "rounds": 3, "batch_size": 60,
            "seed": "us1-spec", "run_blue": False}

    # Default-spec run (blank spec => target default).
    r_default = await client.post("/runs", json=base)
    assert r_default.status_code == 201
    default_run = r_default.json()["run_id"]
    default_fw = await _fail_weight_total(client, default_run)

    # Custom-spec run: an always-true must-flag invariant the synth detector
    # cannot satisfy on cleared samples.
    custom_spec = yaml.safe_dump(
        {
            "target_kind": "fraud",
            "obligations": ["flag everything (test obligation)"],
            "invariants": [
                {
                    "name": "always_must_flag",
                    "description": "every transaction must be flagged",
                    "kind": "must_flag_when",
                    "params": {"all_of": [{"feature": "amount", "ge": 0}]},
                }
            ],
            "metamorphic_relations": [],
            "holdout_generator_kind": "deterministic_rule",
        }
    )
    r_custom = await client.post("/runs", json={**base, "spec": custom_spec})
    assert r_custom.status_code == 201
    custom_run = r_custom.json()["run_id"]
    custom_fw = await _fail_weight_total(client, custom_run)

    # The custom obligation reached the oracle: with an always-firing invariant,
    # the InvariantOracle adds FAIL votes the default spec never produced.
    assert custom_fw > default_fw, (
        f"custom spec must change verdicts: custom fail_weight {custom_fw} "
        f"should exceed default {default_fw}"
    )

    # And the SEALED custom spec — not the target default — was stored + resolved
    # for the custom run (the seal loop drove the run off the operator's spec).
    sf = session_factory()
    async with sf() as s:
        row = (await s.execute(
            select(SpecRow).where(SpecRow.run_id == custom_run)
        )).scalars().first()
    assert row is not None, "the custom run must have a sealed spec row"
    assert "always_must_flag" in _invariant_names(row.spec_json)


async def test_post_run_invalid_spec_returns_422(client: AsyncClient) -> None:
    """A malformed sealed spec is a typed 422 (the message names the problem),
    never a silently-ignored bad spec — and no run is launched."""
    # Missing the required ``obligations`` key => from_dict raises ValueError.
    bad_spec = yaml.safe_dump(
        {
            "target_kind": "fraud",
            "invariants": [],
            "metamorphic_relations": [],
            "holdout_generator_kind": "deterministic_rule",
        }
    )
    r = await client.post(
        "/runs",
        json={"target": "synth", "rounds": 2, "batch_size": 20,
              "seed": "bad", "run_blue": False, "spec": bad_spec},
    )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "invalid_sealed_spec"
    assert "obligations" in detail["message"]


async def test_post_run_not_yaml_mapping_returns_422(client: AsyncClient) -> None:
    """A spec that does not parse to a mapping is also a typed 422, not a 500."""
    r = await client.post(
        "/runs",
        json={"target": "synth", "rounds": 2, "batch_size": 20,
              "seed": "bad2", "run_blue": False, "spec": "- just\n- a\n- list"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "invalid_sealed_spec"


async def test_blank_spec_falls_back_to_default(client: AsyncClient) -> None:
    """A blank spec string is treated as 'use the target default' (201), and the
    stored spec equals the target's default spec — no override."""
    r = await client.post(
        "/runs",
        json={"target": "synth", "rounds": 2, "batch_size": 20,
              "seed": "blank", "run_blue": False, "spec": "   "},
    )
    assert r.status_code == 201
    run_id = r.json()["run_id"]
    default_inv_names = _invariant_names(yaml.safe_load(default_spec_yaml("synth")))
    sf = session_factory()
    async with sf() as s:
        row = (await s.execute(
            select(SpecRow).where(SpecRow.run_id == run_id)
        )).scalars().first()
    assert row is not None
    assert _invariant_names(row.spec_json) == default_inv_names
