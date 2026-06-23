"""Orchestrator-level full-arc flow: red -> verify -> measure -> blue -> recover.

``run_with_blue`` composes the generic ``run_loop`` (red -> verify -> measure,
persisting rounds/attacks/verdicts) with the blue recovery round. ``run_loop``
itself stays target-agnostic and blue-free; the composition happens HERE, where
the orchestrator already owns the run lifecycle.

After the red loop, this harvests THIS run's successful evasions from
``AttackRow`` (``evaded AND true_label_preserved``), reconstructs the held-out
mutated samples from the persisted feature maps, calls ``run_blue_round`` with
the components' proposer / retrain_fn / feature sets, and persists a
``BlueRoundRow`` with the ``BlueResult``.

The samples are reconstructed as plain attribute-bearing objects
(``SimpleNamespace``) from the persisted ``to_features`` dict — the detector
(``LocalModelTarget``) and the victim ``label_fn`` both read features via
attribute access, so the harness never needs to import the victim record type
(import-discipline: only ``orchestrator/wiring.py`` may see ``examples/``).
"""

import uuid
from collections.abc import Callable, Sequence
from types import SimpleNamespace
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modules.blue.loop import run_blue_round
from modules.blue.proposer import BlueProposer
from orchestrator.interfaces import Adversary, Detector, Oracle
from orchestrator.loop import GenerateFn, LabelFn, run_loop
from shared.persistence import repo
from shared.persistence.models import AttackRow, BlueRoundRow
from shared.types import SealedSpec


def _harvest_holdout(rows: Sequence[AttackRow]) -> list[object]:
    """Reconstruct the mutated, still-fraud, old-detector-cleared evasions.

    One sample per distinct ``txn_index`` (the latest mutation persisted last
    wins by dedup on first-seen, mirroring the demo test). Returned as plain
    attribute objects so the harness stays victim-agnostic.
    """
    holdout: list[object] = []
    seen: set[object] = set()
    for row in rows:
        to_features = cast(dict[str, object], row.mutation_json["to_features"])
        key = to_features.get("txn_index")
        if key in seen:
            continue
        seen.add(key)
        holdout.append(SimpleNamespace(**to_features))
    return holdout


async def run_with_blue(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: str,
    seed: str,
    n_rounds: int,
    batch_size: int,
    threshold: float,
    detector: Detector,
    adversary: Adversary,
    oracles: Sequence[Oracle],
    label_fn: LabelFn,
    generate_fn: GenerateFn,
    spec: SealedSpec,
    catalog: object,
    proposer: BlueProposer,
    retrain_fn: Callable[[Sequence[str]], object],
    available_features: Sequence[str],
    current_features: Sequence[str],
) -> None:
    """Run the full red->verify->measure->blue->recover arc for one run.

    ``run_loop`` is invoked first (and persists rounds/attacks/verdicts as
    today). Then the successful evasions are harvested and the blue recovery
    round runs and is persisted as a ``BlueRoundRow``. ``run_loop`` raises (and
    marks the run failed) on its own errors; if it completes, the blue round
    runs against the persisted evasions.
    """
    await run_loop(
        session_factory,
        run_id=run_id,
        seed=seed,
        n_rounds=n_rounds,
        batch_size=batch_size,
        threshold=threshold,
        detector=detector,
        adversary=adversary,
        oracles=oracles,
        label_fn=label_fn,
        generate_fn=generate_fn,
        spec=spec,
    )

    async with session_factory() as s:
        attacks = await repo.attacks_for_run(s, run_id)
    successful = [
        a for a in attacks if a.evaded and a.true_label_preserved
    ]
    holdout = _harvest_holdout(successful)
    if not holdout:
        # No successful evasions to recover from — nothing to persist. The run
        # is already marked complete by run_loop; surface honestly via no row.
        return

    result = run_blue_round(
        catalog=catalog,
        current_features=current_features,
        available_features=available_features,
        retrain_fn=retrain_fn,
        holdout_samples=holdout,
        label_fn=label_fn,
        threshold=threshold,
        proposer=proposer,
        old_detector=detector,
    )

    v = result.validation
    async with session_factory() as s:
        await repo.add_blue_round(
            s,
            BlueRoundRow(
                id=str(uuid.uuid4()),
                run_id=run_id,
                features_added=list(result.patch.features_to_add),
                detection_before=v.detection_before,
                detection_after=v.detection_after,
                recovered=v.recovered,
                n_holdout=v.n,
                proposer_rationale=result.patch.rationale,
                new_model_ref=str(result.new_model_path)
                if result.new_model_path is not None
                else None,
            ),
        )
