"""LLMHybridFraudRed — the AI attacker for the fraud target (plan.md section 3 Pillar 2,
the "Hybrid" decision in section 5).

Fraud features are anonymized PCA components with no human meaning, so a pure-LLM
attacker can't craft them directly. Instead the LLM **reasons about strategy** — given
the model's feature importances and what got caught last round, it picks which features
to perturb and why — and ``scipy.optimize`` **executes** it: it finds the smallest
perturbation of a REAL fraud that flips the classifier to "legitimate." The result is a
novel adversarial fraud (true label still fraud, carried in metadata for the held-out
oracle), and the open question is whether the other oracles catch the evasion.

One real LLM call per round (cheap). A ScriptedLLM makes it deterministic for tests."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

import numpy as np
from scipy.optimize import minimize

from shared.datasets.fraud import load_splits
from shared.llm.client import LLMClient
from shared.types.core import Attack, Verdict
from shared.types.ids import AttackId, RunId, new_id
from shared.types.results import HealthStatus
from shared.types.sealed_spec import SealedSpec

_SYSTEM = (
    "You are an adversarial red-team agent attacking a credit-card fraud classifier. "
    "You are given a REAL fraudulent transaction the classifier currently catches, the "
    "model's most important features, and feedback from the last attempt. Choose which "
    "features to perturb so the classifier MISSES this fraud (scores it legitimate), "
    "changing as few features as possible. Reply ONLY with a JSON object: "
    '{"tactic": "<short-name>", "features": ["V14", "V12", ...], "rationale": "<one sentence>"}.'
)

_WHITE_BOX = (
    " The verification ensemble also runs: a second IsolationForest model (differential), "
    "metamorphic stability checks under small perturbations, property-fuzzing, and an LLM "
    "judge. Prefer perturbations that also look normal to an anomaly detector and that do "
    "not make the label unstable."
)


class LLMHybridFraudRed:
    def __init__(
        self,
        llm: LLMClient,
        predict: Any,                      # Callable[[Mapping[str,Any]], dict[str,Any]]
        margin: Any,                       # Callable[[Mapping[str,Any]], float] (raw log-odds)
        feature_names: list[str],
        importances: dict[str, float],
        *,
        max_perturb_features: int = 12,
    ) -> None:
        self._llm = llm
        self._predict = predict
        self._margin_fn = margin
        self._features = feature_names
        self._importances = importances
        self._max = max_perturb_features
        splits = load_splits()
        self._frauds = [
            {k: float(v) for k, v in splits.x_holdout.loc[i].to_dict().items()}
            for i in splits.y_holdout[splits.y_holdout == 1].index
        ]

    # ---- producer probability over a raw feature vector ----
    def _prob(self, vec: np.ndarray) -> float:
        payload = {name: float(vec[i]) for i, name in enumerate(self._features)}
        return float(self._predict(payload)["fraud_probability"])

    def _vec(self, payload: Mapping[str, Any]) -> np.ndarray:
        return np.asarray([float(payload.get(n, 0.0)) for n in self._features], dtype=float)

    def _margin(self, vec: np.ndarray) -> float:
        payload = {name: float(vec[i]) for i, name in enumerate(self._features)}
        return float(self._margin_fn(payload))

    # ---- LLM: pick a strategy ----
    async def _strategy(
        self, base: Mapping[str, Any], last_verdict: Verdict | None, white_box: bool
    ) -> tuple[str, list[str], str, float]:
        top = sorted(self._importances.items(), key=lambda kv: kv[1], reverse=True)[:10]
        feedback = "First attempt."
        if last_verdict is not None:
            fired = [v.oracle for v in last_verdict.votes if v.fired]
            feedback = (
                f"Last attempt verdict={last_verdict.outcome}; oracles that fired={fired}. "
                "Adjust strategy to evade them."
            )
        prompt = (
            f"Top model features (name: importance): {dict(top)}\n"
            f"Base fraud current score: {self._prob(self._vec(base)):.3f}\n"
            f"{feedback}\nChoose features to perturb."
        )
        result = await self._llm.complete(
            _SYSTEM + (_WHITE_BOX if white_box else ""), prompt, max_tokens=200
        )
        tactic, features, rationale = self._parse(result.text, [k for k, _ in top])
        return tactic, features, rationale, result.dollars

    def _parse(self, text: str, fallback: list[str]) -> tuple[str, list[str], str]:
        s, e = text.find("{"), text.rfind("}")
        if s != -1 and e > s:
            try:
                obj = cast("dict[str, Any]", json.loads(text[s : e + 1]))
                feats = [f for f in obj.get("features", []) if f in self._features][: self._max]
                if feats:
                    return (str(obj.get("tactic", "llm-perturb")), feats,
                            str(obj.get("rationale", "")))
            except (ValueError, TypeError):
                pass
        return "llm-perturb-fallback", fallback[: self._max], "fallback: perturb top features"

    # ---- scipy: execute the strategy ----
    def _optimize(self, base: np.ndarray, feat_idx: list[int]) -> tuple[np.ndarray, float]:
        def objective(delta: np.ndarray) -> float:
            x = base.copy()
            x[feat_idx] = base[feat_idx] + delta
            # Minimize the raw margin (push toward "legit") with a small perturbation
            # penalty so the adversarial fraud stays close to the real one.
            return self._margin(x) + 0.001 * float(np.dot(delta, delta))

        res = minimize(objective, np.zeros(len(feat_idx)), method="Powell",
                       options={"maxfev": 250, "xtol": 1e-2, "ftol": 1e-2})
        adv = base.copy()
        adv[feat_idx] = base[feat_idx] + np.asarray(res.x, dtype=float).ravel()
        return adv, self._prob(adv)

    async def propose(
        self, spec: SealedSpec, run_id: RunId, round_index: int,
        last_verdict: Verdict | None, white_box: bool,
    ) -> Attack:
        base = self._frauds[round_index % len(self._frauds)]
        base_vec = self._vec(base)
        base_score = self._prob(base_vec)
        tactic, feats, rationale, dollars = await self._strategy(base, last_verdict, white_box)
        feat_idx = [self._features.index(f) for f in feats]
        adv_vec, adv_score = self._optimize(base_vec, feat_idx)
        payload = {name: float(adv_vec[i]) for i, name in enumerate(self._features)}
        trace = (
            f"AI strategy '{tactic}': {rationale} → perturbed {feats}; producer fraud score "
            f"{base_score:.3f} → {adv_score:.3f} "
            f"({'EVADED' if adv_score < 0.5 else 'still flagged'})."
        )
        return Attack(
            attack_id=AttackId(new_id("atk")), run_id=run_id, round_index=round_index,
            tactic=tactic, payload=payload, rationale=trace,
            seed=f"llmhybrid-{round_index}", white_box=white_box, hybrid=True,
            metadata={"true_label": 1, "base_is_real_fraud": True,
                      "base_score": base_score, "adv_score": adv_score,
                      "perturbed_features": feats, "llm_dollars": dollars},
        )

    async def health(self) -> HealthStatus:
        return HealthStatus(status="green", detail={
            "red": "llm-hybrid-fraud", "llm": self._llm.model, "n_frauds": len(self._frauds)})
