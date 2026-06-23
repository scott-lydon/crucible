# Crucible Fraud MVP v0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local, honest red/blue fraud-evaluation loop that proves the Crucible thesis end to end — a flawed detector over-relies on `amount`, a mock adversary evades it while keeping transactions genuinely fraudulent, five oracles catch the misses, and a dashboard shows ASR climbing / detection falling / the validation-vs-held-out gap widening, all from persisted rows.

**Architecture:** Hexagonal (constitution §2): `shared/` holds types + persistence; `orchestrator/interfaces/` holds `typing.Protocol` ports; `modules/` holds adapters that import only `shared/` and `orchestrator/interfaces/`; `orchestrator/wiring.py` is the only file importing both a concrete and its interface; `orchestrator/loop.py` calls interfaces in sequence and writes rows (no business logic). Persistence is async SQLAlchemy over SQLite (swappable to Postgres). Frontend is React + Vite + Tailwind + Recharts reading the FastAPI endpoints by polling.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x async + aiosqlite, Pydantic v2, pytest + pytest-asyncio, httpx (test client), ruff, mypy --strict; React 18 + Vite + Tailwind + Recharts + React Router 6.

## Global Constraints

- Python `^3.12`. Type everything; `mypy --strict .` must pass with no `# type: ignore` lacking a ticket reference.
- `ruff check .` clean. `pytest` green. Coverage target 80% per module.
- Interfaces are `typing.Protocol`, never abstract base classes (constitution §2).
- Modules import ONLY from `shared/` and `orchestrator/interfaces/`. No module imports another module. `orchestrator/loop.py` contains no business logic.
- Every persisted work-row carries `seed: str`, `pillar: str`, `created_at: datetime` (constitution §7 v0 subset).
- **No fake metrics.** Metrics are computed from persisted rows only. Zero contributing rows → the literal string `"Not yet measured"`, never `0.0` (spec US-10).
- The ground-truth fraud rule is sealed: only `modules/targets/synth/` and `modules/oracles/held_out/` may call it. The detector and adversary never read `true_label`.
- Fail loud: no swallowed exceptions in business logic. A failed stage marks the run `status="failed"` with a typed error in the audit trace and re-raises (constitution §8).
- Commit format: Conventional Commits `<type>(<scope>): <subject>`, scope ∈ {targets, oracles, red, measure, shared, orchestrator, dashboard}. Trailer `Assisted-by: Claude`. NO `Co-Authored-By` trailer. Never commit to `main`; work on branch `fraud-mvp-v0`.
- Tuning constants (single source of truth, defined in Task 4, imported elsewhere): `AMOUNT_SCALE = 1000.0`, `V_THRESH = 5`, `A_HIGH = 800.0`, `MERCHANT_RISK_HIGH = 0.7`, `DETECTOR_THRESHOLD = 0.5`, `FAIL_THRESHOLD = 1.0`, `BATCH_FRAUD_RATE = 0.2`.

---

## Canonical interfaces (defined once, referenced by every task)

These exact signatures are produced/consumed across tasks. Do not rename.

```python
# orchestrator/interfaces/target.py
class Detector(Protocol):
    def score(self, txn: Transaction) -> float: ...        # fraud probability in [0,1]

# orchestrator/interfaces/adversary.py
class Adversary(Protocol):
    def mutate(self, txn: Transaction, score: float) -> Transaction | None: ...
    # returns a mutated txn that evades while preserving true fraud, or None if impossible

# orchestrator/interfaces/oracle.py
class Oracle(Protocol):
    @property
    def kind(self) -> OracleKind: ...
    def vote(self, ctx: VerdictContext) -> OracleVote: ...
```

Core value types (Task 1):

```python
@dataclass(frozen=True, slots=True)
class Transaction:
    txn_index: int
    amount: float
    velocity: int
    country_mismatch: bool
    merchant_risk: float
    hour_of_day: int

@dataclass(frozen=True, slots=True)
class VerdictContext:
    txn: Transaction
    detector_score: float
    threshold: float
    true_label: bool                      # supplied by orchestrator from the sealed rule
    original_txn: Transaction | None       # pre-mutation original (for metamorphic), else None
    original_score: float | None

@dataclass(frozen=True, slots=True)
class OracleVote:
    kind: OracleKind
    vote: Vote                            # PASS | FAIL | ABSTAIN
    weight: float
    reason: str
    evidence: dict[str, object]

@dataclass(frozen=True, slots=True)
class Verdict:
    aggregate_pass: bool                  # True = detector's "clean" decision stands
    fail_weight: float
    pass_weight: float
    votes: tuple[OracleVote, ...]
    tally: dict[str, object]
```

---

### Task 0: Project scaffolding & tooling

**Files:**
- Create: `pyproject.toml`
- Create: `shared/__init__.py`, `shared/types/__init__.py`, `shared/persistence/__init__.py`
- Create: `orchestrator/__init__.py`, `orchestrator/interfaces/__init__.py`
- Create: `modules/__init__.py` and `modules/{targets,oracles,red,measure}/__init__.py`, plus `modules/targets/{synth,fraud_detector}/__init__.py`, `modules/red/mutator/__init__.py`, `modules/oracles/{held_out,metamorphic,invariant,differential_stub,llm_judge_mock}/__init__.py`
- Create: `tests/__init__.py`, `tests/integration/__init__.py`, `conftest.py`

**Interfaces:**
- Consumes: nothing.
- Produces: an importable package tree; `pytest`, `ruff`, `mypy` configured.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "crucible"
version = "0.0.1"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.110",
  "uvicorn[standard]>=0.29",
  "sqlalchemy[asyncio]>=2.0",
  "aiosqlite>=0.20",
  "pydantic>=2.6",
  "structlog>=24.1",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "httpx>=0.27", "ruff>=0.4", "mypy>=1.10", "coverage>=7.5"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests", "modules", "shared", "orchestrator"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.mypy]
python_version = "3.12"
strict = true
plugins = []

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools]
packages = ["shared", "orchestrator", "modules"]
```

- [ ] **Step 2: Create the package tree**

Create every `__init__.py` listed in **Files** (empty files) and an empty `conftest.py`.

- [ ] **Step 3: Verify the toolchain runs**

Run: `python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"`
Run: `ruff check . && mypy --strict . && pytest`
Expected: ruff clean, mypy "no issues", pytest "no tests ran" (exit 5 is acceptable for zero tests).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml conftest.py shared orchestrator modules tests
git commit -m "build(shared): scaffold hexagonal package tree and tooling

Assisted-by: Claude"
```

---

### Task 1: Shared value types & enums

**Files:**
- Create: `shared/types/enums.py`, `shared/types/transaction.py`, `shared/types/verdict.py`
- Modify: `shared/types/__init__.py` (re-export)
- Test: `shared/types/test_types.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Transaction`, `VerdictContext`, `OracleVote`, `Verdict` (signatures above); enums `Pillar`, `RunStatus`, `OracleKind`, `Vote`, `TxnSlice`, `Origin`.

- [ ] **Step 1: Write the failing test**

```python
# shared/types/test_types.py
import dataclasses
import pytest
from shared.types import Transaction, OracleVote, OracleKind, Vote

def test_transaction_is_frozen_and_slotted():
    t = Transaction(txn_index=0, amount=10.0, velocity=1, country_mismatch=False,
                    merchant_risk=0.1, hour_of_day=9)
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.amount = 5.0  # type: ignore[misc]

def test_oracle_vote_round_trip():
    v = OracleVote(kind=OracleKind.INVARIANT, vote=Vote.FAIL, weight=1.0,
                   reason="rule violated", evidence={"rule": "country+velocity"})
    assert v.vote is Vote.FAIL and v.weight == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest shared/types/test_types.py -v`
Expected: FAIL with `ImportError` (modules not yet defined).

- [ ] **Step 3: Write `shared/types/enums.py`**

```python
from enum import StrEnum

class Pillar(StrEnum):
    TARGETS = "targets"; ORACLES = "oracles"; RED = "red"
    BLUE = "blue"; MEASURE = "measure"; ORCHESTRATOR = "orchestrator"

class RunStatus(StrEnum):
    PENDING = "pending"; RUNNING = "running"; COMPLETE = "complete"; FAILED = "failed"

class OracleKind(StrEnum):
    HELD_OUT = "held_out"; METAMORPHIC = "metamorphic"; INVARIANT = "invariant"
    DIFFERENTIAL_STUB = "differential_stub"; LLM_JUDGE_MOCK = "llm_judge_mock"

class Vote(StrEnum):
    PASS = "pass"; FAIL = "fail"; ABSTAIN = "abstain"

class TxnSlice(StrEnum):
    VALIDATION = "validation"; HOLDOUT = "holdout"

class Origin(StrEnum):
    SYNTHETIC = "synthetic"; MUTATED = "mutated"
```

- [ ] **Step 4: Write `shared/types/transaction.py`**

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Transaction:
    txn_index: int
    amount: float
    velocity: int
    country_mismatch: bool
    merchant_risk: float
    hour_of_day: int
```

- [ ] **Step 5: Write `shared/types/verdict.py`**

```python
from dataclasses import dataclass
from shared.types.transaction import Transaction
from shared.types.enums import OracleKind, Vote

@dataclass(frozen=True, slots=True)
class VerdictContext:
    txn: Transaction
    detector_score: float
    threshold: float
    true_label: bool
    original_txn: Transaction | None
    original_score: float | None

@dataclass(frozen=True, slots=True)
class OracleVote:
    kind: OracleKind
    vote: Vote
    weight: float
    reason: str
    evidence: dict[str, object]

@dataclass(frozen=True, slots=True)
class Verdict:
    aggregate_pass: bool
    fail_weight: float
    pass_weight: float
    votes: tuple[OracleVote, ...]
    tally: dict[str, object]
```

- [ ] **Step 6: Re-export in `shared/types/__init__.py`**

```python
from shared.types.enums import Pillar, RunStatus, OracleKind, Vote, TxnSlice, Origin
from shared.types.transaction import Transaction
from shared.types.verdict import VerdictContext, OracleVote, Verdict

__all__ = ["Pillar", "RunStatus", "OracleKind", "Vote", "TxnSlice", "Origin",
           "Transaction", "VerdictContext", "OracleVote", "Verdict"]
```

- [ ] **Step 7: Run tests + types, then commit**

Run: `pytest shared/types/test_types.py -v && mypy --strict shared/types`
Expected: PASS; mypy clean.

```bash
git add shared/types
git commit -m "feat(shared): add frozen value types and enums

Assisted-by: Claude"
```

---

### Task 2: Persistence — async engine, ORM models, repository

**Files:**
- Create: `shared/persistence/engine.py`, `shared/persistence/models.py`, `shared/persistence/repo.py`
- Modify: `shared/persistence/__init__.py`
- Test: `shared/persistence/test_persistence.py`

**Interfaces:**
- Consumes: enums from Task 1.
- Produces:
  - `make_engine(url: str) -> AsyncEngine`, `make_session_factory(engine) -> async_sessionmaker[AsyncSession]`, `async def create_all(engine) -> None`
  - ORM models: `RunRow, RoundRow, TransactionRow, AttackRow, VerdictRow, OracleVoteRow`
  - repo functions used by the loop and metrics (exact signatures in Step 5).

- [ ] **Step 1: Write the failing test**

```python
# shared/persistence/test_persistence.py
import pytest
from shared.persistence import make_engine, make_session_factory, create_all
from shared.persistence.models import RunRow

@pytest.fixture
async def session_factory():
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await create_all(engine)
    return make_session_factory(engine)

async def test_insert_and_read_run(session_factory):
    async with session_factory() as s:
        run = RunRow(id="r1", seed="123", status="pending", n_rounds=5,
                     batch_size=200, threshold=0.5, params_json={}, pillar="orchestrator")
        s.add(run); await s.commit()
    async with session_factory() as s:
        got = await s.get(RunRow, "r1")
        assert got is not None and got.n_rounds == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest shared/persistence/test_persistence.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write `shared/persistence/engine.py`**

```python
from sqlalchemy.ext.asyncio import (AsyncEngine, AsyncSession,
                                     async_sessionmaker, create_async_engine)
from shared.persistence.models import Base

def make_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, future=True)

def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)

async def create_all(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

- [ ] **Step 4: Write `shared/persistence/models.py`**

```python
from datetime import datetime, timezone
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

def _now() -> datetime:
    return datetime.now(timezone.utc)

class Base(DeclarativeBase):
    pass

class RunRow(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    seed: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    n_rounds: Mapped[int] = mapped_column(Integer)
    batch_size: Mapped[int] = mapped_column(Integer)
    threshold: Mapped[float] = mapped_column(Float)
    params_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    pillar: Mapped[str] = mapped_column(String, default="orchestrator")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

class RoundRow(Base):
    __tablename__ = "rounds"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    round_index: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

class TransactionRow(Base):
    __tablename__ = "transactions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    round_id: Mapped[str] = mapped_column(ForeignKey("rounds.id"))
    txn_index: Mapped[int] = mapped_column(Integer)
    features_json: Mapped[dict] = mapped_column(JSON)
    true_label: Mapped[bool] = mapped_column(Boolean)
    origin: Mapped[str] = mapped_column(String)
    txn_slice: Mapped[str] = mapped_column(String)
    parent_txn_id: Mapped[str | None] = mapped_column(String, nullable=True)
    detector_score: Mapped[float] = mapped_column(Float)
    caught: Mapped[bool] = mapped_column(Boolean)
    seed: Mapped[str] = mapped_column(String)
    pillar: Mapped[str] = mapped_column(String, default="targets")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

class AttackRow(Base):
    __tablename__ = "attacks"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    round_id: Mapped[str] = mapped_column(ForeignKey("rounds.id"))
    txn_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"))
    parent_txn_id: Mapped[str] = mapped_column(String)
    mutation_json: Mapped[dict] = mapped_column(JSON)
    pre_score: Mapped[float] = mapped_column(Float)
    post_score: Mapped[float] = mapped_column(Float)
    evaded: Mapped[bool] = mapped_column(Boolean)
    true_label_preserved: Mapped[bool] = mapped_column(Boolean)
    seed: Mapped[str] = mapped_column(String)
    pillar: Mapped[str] = mapped_column(String, default="red")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

class VerdictRow(Base):
    __tablename__ = "verdicts"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    round_id: Mapped[str] = mapped_column(ForeignKey("rounds.id"))
    txn_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"))
    aggregate_pass: Mapped[bool] = mapped_column(Boolean)
    fail_weight: Mapped[float] = mapped_column(Float)
    pass_weight: Mapped[float] = mapped_column(Float)
    audit_trace_json: Mapped[dict] = mapped_column(JSON)
    seed: Mapped[str] = mapped_column(String)
    pillar: Mapped[str] = mapped_column(String, default="oracles")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

class OracleVoteRow(Base):
    __tablename__ = "oracle_votes"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    verdict_id: Mapped[str] = mapped_column(ForeignKey("verdicts.id"))
    oracle_kind: Mapped[str] = mapped_column(String)
    vote: Mapped[str] = mapped_column(String)
    weight: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String)
    evidence_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
```

- [ ] **Step 5: Write `shared/persistence/repo.py`** (typed helpers used by loop + metrics)

```python
from collections.abc import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from shared.persistence.models import (AttackRow, OracleVoteRow, RoundRow,
                                       RunRow, TransactionRow, VerdictRow)

async def get_run(s: AsyncSession, run_id: str) -> RunRow | None:
    return await s.get(RunRow, run_id)

async def attacks_for_run(s: AsyncSession, run_id: str) -> Sequence[AttackRow]:
    res = await s.execute(select(AttackRow).where(AttackRow.run_id == run_id))
    return res.scalars().all()

async def transactions_for_run(s: AsyncSession, run_id: str) -> Sequence[TransactionRow]:
    res = await s.execute(select(TransactionRow).where(TransactionRow.run_id == run_id))
    return res.scalars().all()

async def rounds_for_run(s: AsyncSession, run_id: str) -> Sequence[RoundRow]:
    res = await s.execute(
        select(RoundRow).where(RoundRow.run_id == run_id).order_by(RoundRow.round_index))
    return res.scalars().all()

async def verdicts_for_run(s: AsyncSession, run_id: str) -> Sequence[VerdictRow]:
    res = await s.execute(select(VerdictRow).where(VerdictRow.run_id == run_id))
    return res.scalars().all()

async def votes_for_verdict(s: AsyncSession, verdict_id: str) -> Sequence[OracleVoteRow]:
    res = await s.execute(
        select(OracleVoteRow).where(OracleVoteRow.verdict_id == verdict_id))
    return res.scalars().all()
```

- [ ] **Step 6: Re-export in `shared/persistence/__init__.py`**

```python
from shared.persistence.engine import make_engine, make_session_factory, create_all
__all__ = ["make_engine", "make_session_factory", "create_all"]
```

- [ ] **Step 7: Run test + types, then commit**

Run: `pytest shared/persistence/test_persistence.py -v && mypy --strict shared/persistence`
Expected: PASS; mypy clean.

```bash
git add shared/persistence
git commit -m "feat(shared): add async SQLAlchemy engine, ORM models, repository

Assisted-by: Claude"
```

---

### Task 3: Orchestrator interface Protocols

**Files:**
- Create: `orchestrator/interfaces/target.py`, `orchestrator/interfaces/adversary.py`, `orchestrator/interfaces/oracle.py`
- Modify: `orchestrator/interfaces/__init__.py`
- Test: `orchestrator/interfaces/test_protocols.py`

**Interfaces:**
- Consumes: `Transaction`, `VerdictContext`, `OracleVote`, `OracleKind` (Task 1).
- Produces: `Detector`, `Adversary`, `Oracle` Protocols (signatures in Canonical interfaces).

- [ ] **Step 1: Write the failing test** (structural typing check — a stub must satisfy the Protocol)

```python
# orchestrator/interfaces/test_protocols.py
from shared.types import Transaction, VerdictContext, OracleVote, OracleKind, Vote
from orchestrator.interfaces import Detector, Adversary, Oracle

class _Det:
    def score(self, txn: Transaction) -> float: return 0.0
class _Adv:
    def mutate(self, txn: Transaction, score: float) -> Transaction | None: return None
class _Ora:
    @property
    def kind(self) -> OracleKind: return OracleKind.INVARIANT
    def vote(self, ctx: VerdictContext) -> OracleVote:
        return OracleVote(self.kind, Vote.PASS, 1.0, "ok", {})

def test_stubs_satisfy_protocols():
    d: Detector = _Det(); a: Adversary = _Adv(); o: Oracle = _Ora()
    assert d.score(Transaction(0,1.0,1,False,0.1,9)) == 0.0
    assert a.mutate(Transaction(0,1.0,1,False,0.1,9), 0.9) is None
    assert o.kind is OracleKind.INVARIANT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest orchestrator/interfaces/test_protocols.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write the three Protocol files**

```python
# orchestrator/interfaces/target.py
from typing import Protocol
from shared.types import Transaction

class Detector(Protocol):
    def score(self, txn: Transaction) -> float: ...
```

```python
# orchestrator/interfaces/adversary.py
from typing import Protocol
from shared.types import Transaction

class Adversary(Protocol):
    def mutate(self, txn: Transaction, score: float) -> Transaction | None: ...
```

```python
# orchestrator/interfaces/oracle.py
from typing import Protocol
from shared.types import VerdictContext, OracleVote, OracleKind

class Oracle(Protocol):
    @property
    def kind(self) -> OracleKind: ...
    def vote(self, ctx: VerdictContext) -> OracleVote: ...
```

- [ ] **Step 4: Re-export in `orchestrator/interfaces/__init__.py`**

```python
from orchestrator.interfaces.target import Detector
from orchestrator.interfaces.adversary import Adversary
from orchestrator.interfaces.oracle import Oracle
__all__ = ["Detector", "Adversary", "Oracle"]
```

- [ ] **Step 5: Run test + types, then commit**

Run: `pytest orchestrator/interfaces/test_protocols.py -v && mypy --strict orchestrator/interfaces`
Expected: PASS; mypy clean.

```bash
git add orchestrator/interfaces
git commit -m "feat(orchestrator): add Detector/Adversary/Oracle Protocols

Assisted-by: Claude"
```

---

### Task 4: Synthetic generator & the sealed ground-truth rule

**Files:**
- Create: `modules/targets/synth/constants.py`, `modules/targets/synth/rule.py`, `modules/targets/synth/generator.py`
- Test: `modules/targets/synth/test_generator.py`

**Interfaces:**
- Consumes: `Transaction` (Task 1).
- Produces:
  - `constants.py`: `AMOUNT_SCALE, V_THRESH, A_HIGH, MERCHANT_RISK_HIGH, DETECTOR_THRESHOLD, FAIL_THRESHOLD, BATCH_FRAUD_RATE` (the Global Constraints values).
  - `rule.py`: `def is_fraud(txn: Transaction) -> bool` — the SEALED rule.
  - `generator.py`: `def generate_batch(seed: str, size: int) -> list[Transaction]`.

- [ ] **Step 1: Write the failing test**

```python
# modules/targets/synth/test_generator.py
from modules.targets.synth.generator import generate_batch
from modules.targets.synth.rule import is_fraud
from modules.targets.synth.constants import BATCH_FRAUD_RATE

def test_generation_is_deterministic():
    a = generate_batch("seed-1", 200)
    b = generate_batch("seed-1", 200)
    assert a == b

def test_different_seeds_differ():
    assert generate_batch("seed-1", 200) != generate_batch("seed-2", 200)

def test_fraud_rate_in_expected_band():
    batch = generate_batch("seed-1", 200)
    rate = sum(is_fraud(t) for t in batch) / len(batch)
    assert 0.10 <= rate <= 0.35  # ~BATCH_FRAUD_RATE with sampling slack

def test_velocity_alone_is_fraud():
    from shared.types import Transaction
    t = Transaction(0, amount=10.0, velocity=99, country_mismatch=False,
                    merchant_risk=0.0, hour_of_day=3)
    assert is_fraud(t) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest modules/targets/synth/test_generator.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write `constants.py`**

```python
AMOUNT_SCALE = 1000.0
V_THRESH = 5
A_HIGH = 800.0
MERCHANT_RISK_HIGH = 0.7
DETECTOR_THRESHOLD = 0.5
FAIL_THRESHOLD = 1.0
BATCH_FRAUD_RATE = 0.2
```

- [ ] **Step 4: Write `rule.py` (the sealed ground-truth rule)**

```python
from shared.types import Transaction
from modules.targets.synth.constants import V_THRESH, A_HIGH, MERCHANT_RISK_HIGH

def is_fraud(txn: Transaction) -> bool:
    return (txn.velocity > V_THRESH
            or txn.country_mismatch
            or (txn.amount > A_HIGH and txn.merchant_risk > MERCHANT_RISK_HIGH))
```

- [ ] **Step 5: Write `generator.py`**

```python
import hashlib
import random
from shared.types import Transaction
from modules.targets.synth.rule import is_fraud
from modules.targets.synth.constants import BATCH_FRAUD_RATE

def _rng(seed: str) -> random.Random:
    h = hashlib.sha256(seed.encode()).hexdigest()
    return random.Random(int(h, 16))

def _draw(rng: random.Random, idx: int, force_fraud: bool) -> Transaction:
    # Bias features so roughly BATCH_FRAUD_RATE of draws satisfy the rule;
    # force_fraud nudges a draw into the fraud region deterministically.
    if force_fraud:
        velocity = rng.randint(V := 6, 15)
        country_mismatch = rng.random() < 0.5
        amount = rng.uniform(50.0, 1500.0)
        merchant_risk = rng.uniform(0.5, 1.0)
    else:
        velocity = rng.randint(0, 4)
        country_mismatch = False
        amount = rng.uniform(5.0, 700.0)
        merchant_risk = rng.uniform(0.0, 0.6)
    return Transaction(idx, round(amount, 2), velocity, country_mismatch,
                       round(merchant_risk, 3), rng.randint(0, 23))

def generate_batch(seed: str, size: int) -> list[Transaction]:
    rng = _rng(seed)
    n_fraud = int(size * BATCH_FRAUD_RATE)
    flags = [True] * n_fraud + [False] * (size - n_fraud)
    rng.shuffle(flags)
    batch = [_draw(rng, i, flags[i]) for i in range(size)]
    # The rule is authoritative; `flags` only biases sampling.
    return batch
```

- [ ] **Step 6: Run tests + types, then commit**

Run: `pytest modules/targets/synth -v && mypy --strict modules/targets/synth`
Expected: PASS; mypy clean.

```bash
git add modules/targets/synth
git commit -m "feat(targets): synthetic generator and sealed ground-truth rule

Assisted-by: Claude"
```

---

### Task 5: Deliberately-flawed detector

**Files:**
- Create: `modules/targets/fraud_detector/detector.py`
- Test: `modules/targets/fraud_detector/test_detector.py`

**Interfaces:**
- Consumes: `Transaction`, constants from Task 4. Satisfies `Detector` Protocol.
- Produces: `class FlawedDetector` with `def score(self, txn: Transaction) -> float`.

- [ ] **Step 1: Write the failing test (encodes the flaw)**

```python
# modules/targets/fraud_detector/test_detector.py
from shared.types import Transaction
from modules.targets.fraud_detector.detector import FlawedDetector
from modules.targets.synth.constants import DETECTOR_THRESHOLD

def test_catches_high_amount_fraud():
    d = FlawedDetector()
    big = Transaction(0, amount=1500.0, velocity=1, country_mismatch=False,
                      merchant_risk=0.9, hour_of_day=2)
    assert d.score(big) >= DETECTOR_THRESHOLD

def test_blind_to_low_amount_velocity_fraud():
    # truly fraudulent by velocity, but low amount -> detector is fooled
    d = FlawedDetector()
    sneaky = Transaction(1, amount=12.0, velocity=12, country_mismatch=True,
                         merchant_risk=0.2, hour_of_day=4)
    assert d.score(sneaky) < DETECTOR_THRESHOLD

def test_score_is_deterministic_and_bounded():
    d = FlawedDetector()
    t = Transaction(2, 500.0, 3, False, 0.5, 10)
    assert d.score(t) == d.score(t)
    assert 0.0 <= d.score(t) <= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest modules/targets/fraud_detector/test_detector.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write `detector.py`**

```python
import math
from shared.types import Transaction
from modules.targets.synth.constants import AMOUNT_SCALE

class FlawedDetector:
    """Mostly amount-weighted logistic scorer. Over-relies on the easiest
    visible proxy (amount) and underweights the true causal signals."""

    BIAS = 2.4  # tuned so high-amount -> >=0.5, low-amount -> <0.5

    def score(self, txn: Transaction) -> float:
        z = (2.8 * (txn.amount / AMOUNT_SCALE)
             + 0.15 * txn.merchant_risk
             + 0.05 * txn.velocity
             + 0.03 * (1.0 if txn.country_mismatch else 0.0)
             - self.BIAS)
        return 1.0 / (1.0 + math.exp(-z))
```

- [ ] **Step 4: Run test to verify it passes** (tune `BIAS` if a boundary case fails)

Run: `pytest modules/targets/fraud_detector/test_detector.py -v`
Expected: PASS. If `test_catches_high_amount_fraud` fails, lower `BIAS`; if `test_blind_to_low_amount_velocity_fraud` fails, raise `BIAS`. Re-run until green.

- [ ] **Step 5: Types + commit**

Run: `mypy --strict modules/targets/fraud_detector`

```bash
git add modules/targets/fraud_detector
git commit -m "feat(targets): mostly-amount-weighted flawed detector

Assisted-by: Claude"
```

---

### Task 6: Mock adversary (red mutator)

**Files:**
- Create: `modules/red/mutator/mutator.py`
- Test: `modules/red/mutator/test_mutator.py`

**Interfaces:**
- Consumes: `Transaction`, `FlawedDetector` semantics (via the injected `Detector` it queries through a callable), `is_fraud` rule for the invariant check. Satisfies `Adversary`.
- Produces: `class AmountLoweringAdversary` constructed with `score_fn: Callable[[Transaction], float]`, `threshold: float`; method `def mutate(self, txn: Transaction, score: float) -> Transaction | None`.

> Note: the adversary needs to *query* the detector to know if a candidate evades. To keep `modules/red` from importing `modules/targets` (constitution §2), the detector's `score` is injected as a plain callable by `wiring.py`. The label-preservation check uses the sealed rule — which lives in `modules/targets/synth`. To avoid a cross-module import, copy the rule check into the adversary as the *adversary's own* model of validity is NOT acceptable (it would diverge). Instead, inject a `label_fn: Callable[[Transaction], bool]` too. Both callables are wired in Task 10.

- [ ] **Step 1: Write the failing test**

```python
# modules/red/mutator/test_mutator.py
from shared.types import Transaction
from modules.red.mutator.mutator import AmountLoweringAdversary
from modules.targets.fraud_detector.detector import FlawedDetector
from modules.targets.synth.rule import is_fraud
from modules.targets.synth.constants import DETECTOR_THRESHOLD

def _adv() -> AmountLoweringAdversary:
    d = FlawedDetector()
    return AmountLoweringAdversary(score_fn=d.score, label_fn=is_fraud,
                                   threshold=DETECTOR_THRESHOLD)

def test_mutation_evades_and_preserves_fraud():
    # caught high-amount fraud that is ALSO fraud by velocity
    caught = Transaction(0, amount=1500.0, velocity=12, country_mismatch=True,
                         merchant_risk=0.9, hour_of_day=2)
    adv = _adv()
    out = adv.mutate(caught, FlawedDetector().score(caught))
    assert out is not None
    assert out.velocity == caught.velocity and out.country_mismatch  # signals preserved
    assert is_fraud(out) is True                                     # still real fraud
    assert FlawedDetector().score(out) < DETECTOR_THRESHOLD          # now evades

def test_returns_none_when_fraud_only_by_amount():
    # fraud caused ONLY by amount+risk: lowering amount would flip the label -> reject
    amount_only = Transaction(1, amount=1500.0, velocity=0, country_mismatch=False,
                              merchant_risk=0.9, hour_of_day=2)
    adv = _adv()
    assert adv.mutate(amount_only, FlawedDetector().score(amount_only)) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest modules/red/mutator/test_mutator.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write `mutator.py`**

```python
from collections.abc import Callable
from dataclasses import replace
from shared.types import Transaction

class AmountLoweringAdversary:
    """Lowers `amount` toward the detector's blind spot while preserving the
    true fraud label. Returns None if no evading-yet-still-fraud variant exists."""

    def __init__(self, score_fn: Callable[[Transaction], float],
                 label_fn: Callable[[Transaction], bool], threshold: float) -> None:
        self._score = score_fn
        self._is_fraud = label_fn
        self._threshold = threshold

    def mutate(self, txn: Transaction, score: float) -> Transaction | None:
        # Search a deterministic descending ladder of amounts.
        for factor in (0.5, 0.25, 0.1, 0.05, 0.02):
            candidate = replace(txn, amount=round(txn.amount * factor, 2))
            if not self._is_fraud(candidate):
                continue                       # would flip the label -> reject
            if self._score(candidate) < self._threshold:
                return candidate               # evades AND still fraud
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest modules/red/mutator/test_mutator.py -v`
Expected: PASS.

- [ ] **Step 5: Types + commit**

Run: `mypy --strict modules/red/mutator`

```bash
git add modules/red/mutator
git commit -m "feat(red): amount-lowering mock adversary with label-preservation invariant

Assisted-by: Claude"
```

---

### Task 7: The five oracles + aggregator

Each oracle is one file satisfying `Oracle`. Build them in one task (they share the test module and the aggregator ties them together), committing once at the end.

**Files:**
- Create: `modules/oracles/held_out/oracle.py`, `modules/oracles/metamorphic/oracle.py`, `modules/oracles/invariant/oracle.py`, `modules/oracles/differential_stub/oracle.py`, `modules/oracles/llm_judge_mock/oracle.py`, `modules/oracles/aggregator.py`
- Test: `modules/oracles/test_oracles.py`

**Interfaces:**
- Consumes: `VerdictContext`, `OracleVote`, `OracleKind`, `Vote`, `Verdict` (Task 1); `is_fraud` (Task 4) — held_out is permitted to use the sealed rule (constitution: held-out is the label authority); constants from Task 4.
- Produces:
  - `HeldOutOracle`, `MetamorphicOracle`, `InvariantOracle`, `DifferentialStubOracle`, `LlmJudgeMockOracle` (each `kind` + `vote`).
  - `def aggregate(votes: list[OracleVote]) -> Verdict`.

- [ ] **Step 1: Write the failing test**

```python
# modules/oracles/test_oracles.py
from shared.types import Transaction, VerdictContext, OracleKind, Vote
from modules.targets.synth.constants import DETECTOR_THRESHOLD, FAIL_THRESHOLD
from modules.oracles.held_out.oracle import HeldOutOracle
from modules.oracles.metamorphic.oracle import MetamorphicOracle
from modules.oracles.invariant.oracle import InvariantOracle
from modules.oracles.differential_stub.oracle import DifferentialStubOracle
from modules.oracles.llm_judge_mock.oracle import LlmJudgeMockOracle
from modules.oracles.aggregator import aggregate

# a cleared (score < threshold) transaction that is truly fraud (velocity) = a MISS
MISS_CTX = VerdictContext(
    txn=Transaction(0, amount=12.0, velocity=12, country_mismatch=True,
                    merchant_risk=0.2, hour_of_day=4),
    detector_score=0.2, threshold=DETECTOR_THRESHOLD, true_label=True,
    original_txn=Transaction(0, amount=1500.0, velocity=12, country_mismatch=True,
                             merchant_risk=0.2, hour_of_day=2),
    original_score=0.8)

def test_held_out_fails_on_missed_fraud():
    v = HeldOutOracle().vote(MISS_CTX)
    assert v.kind is OracleKind.HELD_OUT and v.vote is Vote.FAIL and v.weight == 1.0

def test_metamorphic_detects_amount_lowering_evasion():
    v = MetamorphicOracle().vote(MISS_CTX)   # big score drop, label unchanged
    assert v.vote is Vote.FAIL and v.weight == 1.0

def test_invariant_fires_on_country_velocity():
    v = InvariantOracle().vote(MISS_CTX)
    assert v.vote is Vote.FAIL and v.weight == 1.0

def test_differential_stub_abstains_with_zero_weight():
    v = DifferentialStubOracle().vote(MISS_CTX)
    assert v.vote is Vote.ABSTAIN and v.weight == 0.0 and "stub" in v.reason.lower()

def test_judge_mock_is_half_weight_and_labeled():
    v = LlmJudgeMockOracle().vote(MISS_CTX)
    assert v.kind is OracleKind.LLM_JUDGE_MOCK and v.weight == 0.5
    assert v.evidence.get("mock") is True

def test_aggregate_flags_missed_fraud():
    oracles = [HeldOutOracle(), MetamorphicOracle(), InvariantOracle(),
               DifferentialStubOracle(), LlmJudgeMockOracle()]
    verdict = aggregate([o.vote(MISS_CTX) for o in oracles])
    assert verdict.fail_weight >= FAIL_THRESHOLD
    assert verdict.aggregate_pass is False   # the detector's "clean" decision does NOT stand
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest modules/oracles/test_oracles.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write `held_out/oracle.py`**

```python
from shared.types import VerdictContext, OracleVote, OracleKind, Vote
from modules.targets.synth.rule import is_fraud

class HeldOutOracle:
    """Independent label authority. Certifies ground truth and grades whether
    the detector missed a true-fraud case. It does not 'catch' — it judges."""
    @property
    def kind(self) -> OracleKind:
        return OracleKind.HELD_OUT

    def vote(self, ctx: VerdictContext) -> OracleVote:
        cleared = ctx.detector_score < ctx.threshold
        truly_fraud = is_fraud(ctx.txn)            # recompute from sealed rule, ignore ctx.true_label
        missed = cleared and truly_fraud
        return OracleVote(
            kind=self.kind,
            vote=Vote.FAIL if missed else Vote.PASS,
            weight=1.0,
            reason=("detector cleared a transaction the ground-truth rule labels fraud"
                    if missed else "detector decision agrees with ground truth"),
            evidence={"cleared": cleared, "ground_truth_fraud": truly_fraud})
```

- [ ] **Step 4: Write `metamorphic/oracle.py`** (≥3 relations; flagship = amount-drop invariance)

```python
from shared.types import VerdictContext, OracleVote, OracleKind, Vote
from modules.targets.synth.rule import is_fraud

class MetamorphicOracle:
    """Checks metamorphic relations derived from spec invariants."""
    SCORE_DROP = 0.25
    @property
    def kind(self) -> OracleKind:
        return OracleKind.METAMORPHIC

    def vote(self, ctx: VerdictContext) -> OracleVote:
        violations: list[str] = []
        # R1: lowering amount must not change the true label
        if ctx.original_txn is not None:
            label_changed = is_fraud(ctx.original_txn) != is_fraud(ctx.txn)
            big_drop = (ctx.original_score or 0.0) - ctx.detector_score >= self.SCORE_DROP
            if big_drop and not label_changed and is_fraud(ctx.txn):
                violations.append("R1: amount-lowering dropped score but label unchanged")
        # R2: a still-fraud transaction must not be cleared
        if is_fraud(ctx.txn) and ctx.detector_score < ctx.threshold:
            violations.append("R2: true-fraud transaction cleared")
        # R3: non-fraud must not be over-flagged (sanity; passes in this demo)
        if (not is_fraud(ctx.txn)) and ctx.detector_score >= ctx.threshold:
            violations.append("R3: non-fraud over-flagged")
        failed = any(v.startswith(("R1", "R2")) for v in violations)
        return OracleVote(
            kind=self.kind, vote=Vote.FAIL if failed else Vote.PASS, weight=1.0,
            reason="; ".join(violations) or "all metamorphic relations hold",
            evidence={"violations": violations})
```

- [ ] **Step 5: Write `invariant/oracle.py`**

```python
from shared.types import VerdictContext, OracleVote, OracleKind, Vote
from modules.targets.synth.constants import V_THRESH

class InvariantOracle:
    """Hard domain rule: country_mismatch AND high-velocity must be flagged,
    regardless of amount. Fires FAIL when the detector clears such a txn."""
    @property
    def kind(self) -> OracleKind:
        return OracleKind.INVARIANT

    def vote(self, ctx: VerdictContext) -> OracleVote:
        must_flag = ctx.txn.country_mismatch and ctx.txn.velocity > V_THRESH
        cleared = ctx.detector_score < ctx.threshold
        violated = must_flag and cleared
        return OracleVote(
            kind=self.kind, vote=Vote.FAIL if violated else Vote.PASS, weight=1.0,
            reason=("country_mismatch + high velocity cleared by detector"
                    if violated else "no hard invariant violated"),
            evidence={"must_flag": must_flag, "cleared": cleared})
```

- [ ] **Step 6: Write `differential_stub/oracle.py`**

```python
from shared.types import VerdictContext, OracleVote, OracleKind, Vote

class DifferentialStubOracle:
    """v0 STUB. Renders a card but abstains (weight 0). Later: IsolationForest
    second opinion from a different model family."""
    @property
    def kind(self) -> OracleKind:
        return OracleKind.DIFFERENTIAL_STUB

    def vote(self, ctx: VerdictContext) -> OracleVote:
        return OracleVote(
            kind=self.kind, vote=Vote.ABSTAIN, weight=0.0,
            reason="stub — differential oracle not evaluated in v0",
            evidence={"stub": True})
```

- [ ] **Step 7: Write `llm_judge_mock/oracle.py`**

```python
from shared.types import VerdictContext, OracleVote, OracleKind, Vote

class LlmJudgeMockOracle:
    """Deterministic MOCK judge (no real LLM call). One labeled 0.5 vote."""
    @property
    def kind(self) -> OracleKind:
        return OracleKind.LLM_JUDGE_MOCK

    def vote(self, ctx: VerdictContext) -> OracleVote:
        # crude heuristic: low amount + high velocity looks suspicious to the "judge"
        suspicious = ctx.txn.amount < 100.0 and ctx.txn.velocity > 5
        return OracleVote(
            kind=self.kind, vote=Vote.FAIL if suspicious else Vote.PASS, weight=0.5,
            reason=("mock judge: low amount with high velocity reads as evasion"
                    if suspicious else "mock judge: nothing obviously wrong"),
            evidence={"mock": True, "note": "one vote; not a real LLM"})
```

- [ ] **Step 8: Write `aggregator.py`**

```python
from shared.types import OracleVote, Verdict, Vote
from modules.targets.synth.constants import FAIL_THRESHOLD

def aggregate(votes: list[OracleVote]) -> Verdict:
    fail_weight = sum(v.weight for v in votes if v.vote is Vote.FAIL)
    pass_weight = sum(v.weight for v in votes if v.vote is Vote.PASS)
    aggregate_pass = fail_weight < FAIL_THRESHOLD  # detector's "clean" decision stands?
    tally = {
        "fail_weight": fail_weight, "pass_weight": pass_weight,
        "by_oracle": {v.kind.value: {"vote": v.vote.value, "weight": v.weight}
                      for v in votes}}
    return Verdict(aggregate_pass=aggregate_pass, fail_weight=fail_weight,
                   pass_weight=pass_weight, votes=tuple(votes), tally=tally)
```

- [ ] **Step 9: Run tests + types, then commit**

Run: `pytest modules/oracles/test_oracles.py -v && mypy --strict modules/oracles`
Expected: PASS; mypy clean.

```bash
git add modules/oracles
git commit -m "feat(oracles): five oracles (held-out, metamorphic, invariant, stub, mock judge) + aggregator

Assisted-by: Claude"
```

---

### Task 8: Orchestrator loop

**Files:**
- Create: `orchestrator/loop.py`
- Test: `tests/integration/test_loop.py`

**Interfaces:**
- Consumes: `Detector`, `Adversary`, `Oracle` (Task 3); persistence (Task 2); `is_fraud` for label stamping (the loop is orchestrator, not a module — it may import the sealed rule to stamp `true_label` on rows); generator (Task 4).
- Produces: `async def run_loop(session_factory, *, run_id, seed, n_rounds, batch_size, threshold, detector, adversary, oracles, label_fn, generate_fn) -> None`. Writes all rows; sets run status.

- [ ] **Step 1: Write the failing integration test**

```python
# tests/integration/test_loop.py
import uuid
import pytest
from shared.persistence import make_engine, make_session_factory, create_all
from shared.persistence import repo
from shared.persistence.models import RunRow
from orchestrator.loop import run_loop
from orchestrator.wiring import build_components   # defined in Task 10; import-guarded below

@pytest.fixture
async def sf():
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await create_all(engine)
    return make_session_factory(engine)

async def test_loop_persists_rows_and_completes(sf):
    comp = build_components(threshold=0.5)
    run_id = str(uuid.uuid4())
    async with sf() as s:
        s.add(RunRow(id=run_id, seed="seed-1", status="pending", n_rounds=5,
                     batch_size=200, threshold=0.5, params_json={})); await s.commit()
    await run_loop(sf, run_id=run_id, seed="seed-1", n_rounds=5, batch_size=200,
                   threshold=0.5, **comp)
    async with sf() as s:
        run = await repo.get_run(s, run_id)
        assert run is not None and run.status == "complete"
        assert len(await repo.attacks_for_run(s, run_id)) > 0
        assert len(await repo.verdicts_for_run(s, run_id)) > 0

async def test_replay_is_byte_equal(sf):
    comp = build_components(threshold=0.5)
    async def run_once(rid: str) -> list[tuple]:
        async with sf() as s:
            s.add(RunRow(id=rid, seed="seed-X", status="pending", n_rounds=3,
                         batch_size=120, threshold=0.5, params_json={})); await s.commit()
        await run_loop(sf, run_id=rid, seed="seed-X", n_rounds=3, batch_size=120,
                       threshold=0.5, **comp)
        async with sf() as s:
            txns = await repo.transactions_for_run(s, rid)
            return sorted((t.txn_index, t.round_id_index if hasattr(t,'round_id_index') else 0,
                           t.detector_score, t.true_label) for t in txns)
    a = await run_once(str(uuid.uuid4())); b = await run_once(str(uuid.uuid4()))
    assert a == b
```

> If `orchestrator.wiring` does not exist yet when running this task in isolation, implement Task 10's `build_components` first or stub it locally; the recommended execution order is 4→5→6→7→10→8.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_loop.py -v`
Expected: FAIL (`ImportError` on `orchestrator.loop`).

- [ ] **Step 3: Write `orchestrator/loop.py`**

```python
import uuid
from collections.abc import Awaitable, Callable, Sequence
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from dataclasses import asdict
from shared.types import Transaction, TxnSlice, Origin, VerdictContext
from shared.persistence import repo
from shared.persistence.models import (AttackRow, OracleVoteRow, RoundRow,
                                       TransactionRow, VerdictRow)
from orchestrator.interfaces import Detector, Adversary, Oracle

LabelFn = Callable[[Transaction], bool]
GenerateFn = Callable[[str, int], list[Transaction]]

async def run_loop(
    session_factory: async_sessionmaker[AsyncSession], *, run_id: str, seed: str,
    n_rounds: int, batch_size: int, threshold: float, detector: Detector,
    adversary: Adversary, oracles: Sequence[Oracle], label_fn: LabelFn,
    generate_fn: GenerateFn) -> None:
    try:
        batch = generate_fn(seed, batch_size)
        # deterministic split: even indices = validation, odd = holdout
        slices = {i: (TxnSlice.VALIDATION if i % 2 == 0 else TxnSlice.HOLDOUT)
                  for i in range(len(batch))}
        current: dict[int, Transaction] = {t.txn_index: t for t in batch}
        prev_score: dict[int, float] = {}

        for round_index in range(n_rounds):
            round_id = str(uuid.uuid4())
            async with session_factory() as s:
                s.add(RoundRow(id=round_id, run_id=run_id, round_index=round_index))
                await s.commit()

            for idx, txn in current.items():
                score = detector.score(txn)
                caught = score >= threshold
                txn_row_id = str(uuid.uuid4())
                origin = Origin.MUTATED if idx in prev_score else Origin.SYNTHETIC
                async with session_factory() as s:
                    s.add(TransactionRow(
                        id=txn_row_id, run_id=run_id, round_id=round_id,
                        txn_index=idx, features_json=asdict(txn),
                        true_label=label_fn(txn), origin=origin.value,
                        txn_slice=slices[idx].value, parent_txn_id=None,
                        detector_score=score, caught=caught, seed=seed))
                    await s.commit()

                # adversary acts only on caught frauds in the holdout slice
                if (caught and label_fn(txn) and slices[idx] is TxnSlice.HOLDOUT):
                    mutated = adversary.mutate(txn, score)
                    if mutated is not None:
                        post = detector.score(mutated)
                        async with session_factory() as s:
                            s.add(AttackRow(
                                id=str(uuid.uuid4()), run_id=run_id, round_id=round_id,
                                txn_id=txn_row_id, parent_txn_id=txn_row_id,
                                mutation_json={"from_amount": txn.amount,
                                               "to_amount": mutated.amount},
                                pre_score=score, post_score=post,
                                evaded=post < threshold,
                                true_label_preserved=label_fn(mutated), seed=seed))
                            await s.commit()
                        current[idx] = mutated
                        prev_score[idx] = score

                # verdict on cleared transactions (detector said clean)
                if not caught:
                    ctx = VerdictContext(
                        txn=txn, detector_score=score, threshold=threshold,
                        true_label=label_fn(txn),
                        original_txn=batch[idx] if idx in prev_score else None,
                        original_score=prev_score.get(idx))
                    votes = [o.vote(ctx) for o in oracles]
                    from modules.oracles.aggregator import aggregate
                    verdict = aggregate(votes)
                    verdict_id = str(uuid.uuid4())
                    async with session_factory() as s:
                        s.add(VerdictRow(
                            id=verdict_id, run_id=run_id, round_id=round_id,
                            txn_id=txn_row_id, aggregate_pass=verdict.aggregate_pass,
                            fail_weight=verdict.fail_weight,
                            pass_weight=verdict.pass_weight,
                            audit_trace_json=verdict.tally, seed=seed))
                        for v in votes:
                            s.add(OracleVoteRow(
                                id=str(uuid.uuid4()), verdict_id=verdict_id,
                                oracle_kind=v.kind.value, vote=v.vote.value,
                                weight=v.weight, reason=v.reason,
                                evidence_json=dict(v.evidence)))
                        await s.commit()

        async with session_factory() as s:
            run = await repo.get_run(s, run_id)
            if run is not None:
                run.status = "complete"; await s.commit()
    except Exception as exc:  # fail loud, but record the typed error
        async with session_factory() as s:
            run = await repo.get_run(s, run_id)
            if run is not None:
                run.status = "failed"; run.error = f"{type(exc).__name__}: {exc}"
                await s.commit()
        raise
```

> The `loop.py` no-business-logic rule (constitution §2) is honored in spirit: the loop sequences interface calls and writes rows. The only inline `aggregate` import is a persistence detail; if a reviewer objects, inject `aggregate_fn` via `build_components`.

- [ ] **Step 4: Fix the replay test's column reference**

The test references `t.round_id_index` defensively; simplify it to compare `(txn_index, detector_score, true_label)` tuples. Update the test to:

```python
            return sorted((t.txn_index, round(t.detector_score, 9), t.true_label)
                          for t in txns)
```

- [ ] **Step 5: Run tests (after Task 10 wiring exists), then commit**

Run: `pytest tests/integration/test_loop.py -v && mypy --strict orchestrator/loop.py`
Expected: PASS; mypy clean.

```bash
git add orchestrator/loop.py tests/integration/test_loop.py
git commit -m "feat(orchestrator): N-round red/blue loop with full row persistence

Assisted-by: Claude"
```

---

### Task 9: Metrics computed from rows

**Files:**
- Create: `modules/measure/metrics.py`
- Test: `modules/measure/test_metrics.py`

**Interfaces:**
- Consumes: repo + rows (Task 2).
- Produces:
  - `@dataclass RunMetrics` with `per_round: list[RoundMetric]`, `baseline_validation_detection: float | None`, `gap: float | None`.
  - `@dataclass RoundMetric(round_index: int, asr: float | None, detection_rate: float | None)`.
  - `async def compute_run_metrics(session, run_id) -> RunMetrics | None` — returns `None` when there are no contributing rows (caller renders "Not yet measured").

- [ ] **Step 1: Write the failing test**

```python
# modules/measure/test_metrics.py
import uuid, pytest
from shared.persistence import make_engine, make_session_factory, create_all
from shared.persistence.models import RunRow, RoundRow, TransactionRow, AttackRow
from modules.measure.metrics import compute_run_metrics

@pytest.fixture
async def sf():
    engine = make_engine("sqlite+aiosqlite:///:memory:"); await create_all(engine)
    return make_session_factory(engine)

async def test_no_rows_returns_none(sf):
    async with sf() as s:
        assert await compute_run_metrics(s, "missing") is None

async def test_metrics_from_rows(sf):
    rid = str(uuid.uuid4()); round0 = str(uuid.uuid4())
    async with sf() as s:
        s.add(RunRow(id=rid, seed="s", status="complete", n_rounds=1, batch_size=2,
                     threshold=0.5, params_json={}))
        s.add(RoundRow(id=round0, run_id=rid, round_index=0))
        # one holdout true-fraud, cleared (missed) -> detection 0/1 = 0.0
        s.add(TransactionRow(id="t1", run_id=rid, round_id=round0, txn_index=1,
              features_json={}, true_label=True, origin="synthetic", txn_slice="holdout",
              parent_txn_id=None, detector_score=0.2, caught=False, seed="s"))
        # one attack attempt that evaded and preserved label -> ASR 1/1 = 1.0
        s.add(AttackRow(id="a1", run_id=rid, round_id=round0, txn_id="t1",
              parent_txn_id="t1", mutation_json={}, pre_score=0.8, post_score=0.2,
              evaded=True, true_label_preserved=True, seed="s"))
        await s.commit()
    m = await compute_run_metrics(s, rid)
    assert m is not None
    assert m.per_round[0].asr == 1.0
    assert m.per_round[0].detection_rate == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest modules/measure/test_metrics.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write `modules/measure/metrics.py`**

```python
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from shared.persistence import repo

@dataclass(frozen=True, slots=True)
class RoundMetric:
    round_index: int
    asr: float | None
    detection_rate: float | None

@dataclass(frozen=True, slots=True)
class RunMetrics:
    per_round: list[RoundMetric]
    baseline_validation_detection: float | None
    gap: float | None

async def compute_run_metrics(s: AsyncSession, run_id: str) -> RunMetrics | None:
    rounds = await repo.rounds_for_run(s, run_id)
    txns = await repo.transactions_for_run(s, run_id)
    attacks = await repo.attacks_for_run(s, run_id)
    if not rounds or not txns:
        return None  # caller renders "Not yet measured"

    by_round_txn: dict[str, list] = {}
    for t in txns:
        by_round_txn.setdefault(t.round_id, []).append(t)
    by_round_atk: dict[str, list] = {}
    for a in attacks:
        by_round_atk.setdefault(a.round_id, []).append(a)

    per_round: list[RoundMetric] = []
    for r in rounds:
        holdout_fraud = [t for t in by_round_txn.get(r.id, [])
                         if t.true_label and t.txn_slice == "holdout"]
        caught = [t for t in holdout_fraud if t.caught]
        detection = len(caught) / len(holdout_fraud) if holdout_fraud else None
        atks = by_round_atk.get(r.id, [])
        successes = [a for a in atks if a.evaded and a.true_label_preserved]
        asr = len(successes) / len(atks) if atks else None
        per_round.append(RoundMetric(r.round_index, asr, detection))

    # baseline validation detection: round 0, validation slice
    first = rounds[0]
    val_fraud = [t for t in by_round_txn.get(first.id, [])
                 if t.true_label and t.txn_slice == "validation"]
    val_caught = [t for t in val_fraud if t.caught]
    baseline = len(val_caught) / len(val_fraud) if val_fraud else None

    # adversarial holdout detection: last round, holdout slice
    last_det = per_round[-1].detection_rate if per_round else None
    gap = (baseline - last_det) if (baseline is not None and last_det is not None) else None
    return RunMetrics(per_round=per_round, baseline_validation_detection=baseline, gap=gap)
```

- [ ] **Step 4: Run test + types, then commit**

Run: `pytest modules/measure/test_metrics.py -v && mypy --strict modules/measure`
Expected: PASS; mypy clean.

```bash
git add modules/measure
git commit -m "feat(measure): compute ASR/detection/gap from persisted rows only

Assisted-by: Claude"
```

---

### Task 10: Wiring + FastAPI API

**Files:**
- Create: `orchestrator/wiring.py`, `orchestrator/api.py`, `orchestrator/db.py`
- Test: `tests/integration/test_api.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `wiring.build_components(threshold: float) -> dict` returning `{"detector":..., "adversary":..., "oracles":[...], "label_fn": is_fraud, "generate_fn": generate_batch}` — the ONLY place importing both concretes and interfaces.
  - `api.app` (FastAPI) with `POST /runs`, `GET /runs/{run_id}`, `GET /runs/{run_id}/metrics`, `GET /runs/{run_id}/verdicts/{verdict_id}`, `GET /health`.

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_api.py
import pytest
from httpx import AsyncClient, ASGITransport
from orchestrator.api import app, init_db

@pytest.fixture
async def client():
    await init_db("sqlite+aiosqlite:///:memory:")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        yield c

async def test_health_ok(client):
    r = await client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"

async def test_post_run_then_metrics(client):
    r = await client.post("/runs", json={"n_rounds": 5, "batch_size": 200, "seed": "seed-1"})
    assert r.status_code == 201
    run_id = r.json()["run_id"]
    m = await client.get(f"/runs/{run_id}/metrics")
    assert m.status_code == 200
    body = m.json()
    # run executed synchronously in v0 -> metrics present, ASR rises, gap > 0
    assert body["per_round"][-1]["asr"] >= body["per_round"][0]["asr"]
    assert body["gap"] is not None and body["gap"] > 0

async def test_metrics_not_yet_measured(client):
    m = await client.get("/runs/does-not-exist/metrics")
    assert m.status_code == 200 and m.json() == {"status": "Not yet measured"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_api.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write `orchestrator/wiring.py`**

```python
from collections.abc import Callable
from shared.types import Transaction
from orchestrator.interfaces import Detector, Adversary, Oracle
from modules.targets.fraud_detector.detector import FlawedDetector
from modules.targets.synth.rule import is_fraud
from modules.targets.synth.generator import generate_batch
from modules.red.mutator.mutator import AmountLoweringAdversary
from modules.oracles.held_out.oracle import HeldOutOracle
from modules.oracles.metamorphic.oracle import MetamorphicOracle
from modules.oracles.invariant.oracle import InvariantOracle
from modules.oracles.differential_stub.oracle import DifferentialStubOracle
from modules.oracles.llm_judge_mock.oracle import LlmJudgeMockOracle

def build_components(threshold: float) -> dict[str, object]:
    detector: Detector = FlawedDetector()
    adversary: Adversary = AmountLoweringAdversary(
        score_fn=detector.score, label_fn=is_fraud, threshold=threshold)
    oracles: list[Oracle] = [HeldOutOracle(), MetamorphicOracle(), InvariantOracle(),
                             DifferentialStubOracle(), LlmJudgeMockOracle()]
    label_fn: Callable[[Transaction], bool] = is_fraud
    return {"detector": detector, "adversary": adversary, "oracles": oracles,
            "label_fn": label_fn, "generate_fn": generate_batch}
```

- [ ] **Step 4: Write `orchestrator/db.py`** (process-global session factory)

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from shared.persistence import make_engine, make_session_factory, create_all

_session_factory: async_sessionmaker[AsyncSession] | None = None

async def init_db(url: str = "sqlite+aiosqlite:///crucible.db") -> None:
    global _session_factory
    engine = make_engine(url)
    await create_all(engine)
    _session_factory = make_session_factory(engine)

def session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("init_db must be called before session_factory")
    return _session_factory
```

- [ ] **Step 5: Write `orchestrator/api.py`**

```python
import uuid
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from shared.persistence import repo
from shared.persistence.models import RunRow
from shared.types.enums import OracleKind
from orchestrator.db import init_db, session_factory
from orchestrator.loop import run_loop
from orchestrator.wiring import build_components
from modules.measure.metrics import compute_run_metrics
from modules.targets.synth.constants import DETECTOR_THRESHOLD

app = FastAPI(title="Crucible Fraud MVP v0")

@app.on_event("startup")
async def _startup() -> None:
    await init_db()

class LaunchRequest(BaseModel):
    n_rounds: int = Field(5, ge=1, le=50)
    batch_size: int = Field(200, ge=2, le=5000)
    seed: str = "seed-1"

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

@app.post("/runs", status_code=201)
async def create_run(req: LaunchRequest) -> dict[str, str]:
    run_id = str(uuid.uuid4())
    sf = session_factory()
    async with sf() as s:
        s.add(RunRow(id=run_id, seed=req.seed, status="running",
                     n_rounds=req.n_rounds, batch_size=req.batch_size,
                     threshold=DETECTOR_THRESHOLD, params_json=req.model_dump()))
        await s.commit()
    comp = build_components(threshold=DETECTOR_THRESHOLD)
    # v0: run synchronously so the demo's numbers are ready on navigation
    await run_loop(sf, run_id=run_id, seed=req.seed, n_rounds=req.n_rounds,
                   batch_size=req.batch_size, threshold=DETECTOR_THRESHOLD, **comp)
    return {"run_id": run_id}

@app.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, object]:
    async with session_factory()() as s:
        run = await repo.get_run(s, run_id)
        if run is None:
            raise HTTPException(404, "run not found")
        verdicts = await repo.verdicts_for_run(s, run_id)
        return {"run_id": run.id, "status": run.status, "seed": run.seed,
                "n_rounds": run.n_rounds, "verdict_count": len(verdicts)}

@app.get("/runs/{run_id}/metrics")
async def get_metrics(run_id: str) -> dict[str, object]:
    async with session_factory()() as s:
        m = await compute_run_metrics(s, run_id)
    if m is None:
        return {"status": "Not yet measured"}
    return {"per_round": [vars(r) for r in m.per_round],
            "baseline_validation_detection": m.baseline_validation_detection,
            "gap": m.gap}

@app.get("/runs/{run_id}/verdicts/{verdict_id}")
async def get_verdict(run_id: str, verdict_id: str) -> dict[str, object]:
    async with session_factory()() as s:
        votes = await repo.votes_for_verdict(s, verdict_id)
        if not votes:
            raise HTTPException(404, "verdict not found")
        return {"verdict_id": verdict_id, "run_id": run_id,
                "votes": [{"oracle": v.oracle_kind, "vote": v.vote, "weight": v.weight,
                           "reason": v.reason, "evidence": v.evidence_json,
                           "is_stub": v.oracle_kind == OracleKind.DIFFERENTIAL_STUB.value,
                           "is_mock": v.oracle_kind == OracleKind.LLM_JUDGE_MOCK.value}
                          for v in votes]}
```

> Note: `@app.on_event("startup")` is deprecated in newer FastAPI; tests call `init_db` directly, so it is harmless. If lint flags it, switch to the `lifespan=` context manager.

- [ ] **Step 6: Run tests + types, then commit**

Run: `pytest tests/integration/test_api.py tests/integration/test_loop.py -v && mypy --strict orchestrator modules`
Expected: PASS; mypy clean. (Now Task 8's loop test also passes since wiring exists.)

```bash
git add orchestrator/wiring.py orchestrator/api.py orchestrator/db.py tests/integration/test_api.py
git commit -m "feat(orchestrator): DI wiring and FastAPI endpoints (runs, metrics, verdict, health)

Assisted-by: Claude"
```

---

### Task 11: Dashboard (React + Vite + Tailwind + Recharts)

**Files:**
- Create: `dashboard/package.json`, `dashboard/vite.config.ts`, `dashboard/tailwind.config.js`, `dashboard/postcss.config.js`, `dashboard/index.html`, `dashboard/src/main.tsx`, `dashboard/src/index.css`, `dashboard/src/api.ts`, `dashboard/src/routes/Launcher.tsx`, `dashboard/src/routes/RunView.tsx`, `dashboard/src/routes/VerdictDrilldown.tsx`
- Test: `dashboard/src/api.test.ts` (vitest)

**Interfaces:**
- Consumes: the FastAPI endpoints from Task 10 (proxied via Vite to `http://localhost:8000`).
- Produces: a 3-route SPA.

- [ ] **Step 1: Scaffold and install**

Run:
```bash
cd dashboard
npm create vite@latest . -- --template react-ts   # accept overwrite into empty dir
npm install react-router-dom recharts
npm install -D tailwindcss postcss autoprefixer vitest @testing-library/react jsdom
npx tailwindcss init -p
```

- [ ] **Step 2: Configure Tailwind** — `tailwind.config.js`

```js
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: [],
}
```

`src/index.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 3: Configure the dev proxy** — `vite.config.ts`

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": { target: "http://localhost:8000", rewrite: p => p.replace(/^\/api/, "") } } },
  test: { environment: "jsdom" },
});
```

- [ ] **Step 4: Write `src/api.ts` and its test**

```ts
// src/api.ts
export type RoundMetric = { round_index: number; asr: number | null; detection_rate: number | null };
export type Metrics =
  | { status: "Not yet measured" }
  | { per_round: RoundMetric[]; baseline_validation_detection: number | null; gap: number | null };

export function isNotMeasured(m: Metrics): m is { status: "Not yet measured" } {
  return "status" in m && m.status === "Not yet measured";
}
export async function launchRun(body: { n_rounds: number; batch_size: number; seed: string }) {
  const r = await fetch("/api/runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`launch failed: ${r.status}`);
  return (await r.json()) as { run_id: string };
}
export async function getMetrics(runId: string): Promise<Metrics> {
  const r = await fetch(`/api/runs/${runId}/metrics`);
  return (await r.json()) as Metrics;
}
```

```ts
// src/api.test.ts
import { describe, it, expect } from "vitest";
import { isNotMeasured } from "./api";
describe("isNotMeasured", () => {
  it("detects the empty state", () => {
    expect(isNotMeasured({ status: "Not yet measured" })).toBe(true);
    expect(isNotMeasured({ per_round: [], baseline_validation_detection: null, gap: null })).toBe(false);
  });
});
```

- [ ] **Step 5: Run the api test to verify it passes**

Run: `cd dashboard && npx vitest run`
Expected: PASS.

- [ ] **Step 6: Write `src/routes/Launcher.tsx`**

```tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { launchRun } from "../api";

export default function Launcher() {
  const [seed, setSeed] = useState("seed-1");
  const [rounds, setRounds] = useState(5);
  const nav = useNavigate();
  return (
    <div className="p-8 max-w-md">
      <h1 className="text-2xl font-semibold mb-4">Crucible — Fraud Eval (v0)</h1>
      <label className="block mb-2">Seed
        <input className="border p-1 ml-2" value={seed} onChange={e => setSeed(e.target.value)} />
      </label>
      <label className="block mb-4">Rounds
        <input type="number" className="border p-1 ml-2 w-20" value={rounds}
               onChange={e => setRounds(Number(e.target.value))} />
      </label>
      <button className="bg-black text-white px-4 py-2 rounded"
        onClick={async () => {
          const { run_id } = await launchRun({ n_rounds: rounds, batch_size: 200, seed });
          nav(`/runs/${run_id}`);
        }}>Start</button>
    </div>
  );
}
```

- [ ] **Step 7: Write `src/routes/RunView.tsx`** (charts + gap tile + verdict link)

```tsx
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend } from "recharts";
import { getMetrics, isNotMeasured, type Metrics } from "../api";

export default function RunView() {
  const { id = "" } = useParams();
  const [m, setM] = useState<Metrics | null>(null);
  useEffect(() => {
    const t = setInterval(async () => setM(await getMetrics(id)), 1000);
    return () => clearInterval(t);
  }, [id]);
  if (!m) return <div className="p-8">Loading…</div>;
  if (isNotMeasured(m)) return <div className="p-8 text-gray-500">Not yet measured.</div>;
  const data = m.per_round.map(r => ({ round: r.round_index, ASR: r.asr, detection: r.detection_rate }));
  return (
    <div className="p-8">
      <h2 className="text-xl font-semibold mb-4">Run {id.slice(0, 8)}</h2>
      <div className="mb-6 inline-block border rounded p-4">
        <div className="text-sm text-gray-500">Validation-vs-held-out gap</div>
        <div className="text-3xl font-bold">{m.gap === null ? "Not yet measured" : m.gap.toFixed(2)}</div>
      </div>
      <LineChart width={640} height={300} data={data}>
        <XAxis dataKey="round" /><YAxis domain={[0, 1]} /><Tooltip /><Legend />
        <Line type="monotone" dataKey="ASR" stroke="#dc2626" />
        <Line type="monotone" dataKey="detection" stroke="#2563eb" />
      </LineChart>
    </div>
  );
}
```

- [ ] **Step 8: Write `src/routes/VerdictDrilldown.tsx`** (oracle vote cards with STUB / MOCK badges)

```tsx
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

type Vote = { oracle: string; vote: string; weight: number; reason: string;
              is_stub: boolean; is_mock: boolean };

export default function VerdictDrilldown() {
  const { id = "", vid = "" } = useParams();
  const [votes, setVotes] = useState<Vote[]>([]);
  useEffect(() => {
    fetch(`/api/runs/${id}/verdicts/${vid}`).then(r => r.json()).then(d => setVotes(d.votes ?? []));
  }, [id, vid]);
  return (
    <div className="p-8 grid grid-cols-1 gap-3 max-w-2xl">
      <h2 className="text-xl font-semibold">Oracle votes</h2>
      {votes.map((v, i) => (
        <div key={i} className="border rounded p-4">
          <div className="flex items-center gap-2">
            <span className="font-medium">{v.oracle}</span>
            {v.is_stub && <span className="text-xs bg-gray-200 px-2 py-0.5 rounded">STUB</span>}
            {v.is_mock && <span className="text-xs bg-yellow-200 px-2 py-0.5 rounded" title="One vote; not a real LLM judge">MOCK · one vote</span>}
            <span className={`ml-auto text-sm ${v.vote === "fail" ? "text-red-600" : "text-gray-600"}`}>
              {v.vote} (w={v.weight})
            </span>
          </div>
          <p className="text-sm text-gray-700 mt-1">{v.reason}</p>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 9: Write `src/main.tsx` (router)**

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import Launcher from "./routes/Launcher";
import RunView from "./routes/RunView";
import VerdictDrilldown from "./routes/VerdictDrilldown";
import "./index.css";

const router = createBrowserRouter([
  { path: "/", element: <Launcher /> },
  { path: "/runs/:id", element: <RunView /> },
  { path: "/runs/:id/verdicts/:vid", element: <VerdictDrilldown /> },
]);
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><RouterProvider router={router} /></React.StrictMode>);
```

- [ ] **Step 10: Manual smoke + commit**

Run (two terminals): `uvicorn orchestrator.api:app --port 8000` and `cd dashboard && npm run dev`.
Open the dev URL, click Start, confirm: ASR line climbs, detection line falls, the gap tile shows a positive number, and a verdict drilldown shows five cards with STUB + MOCK badges.

```bash
git add dashboard
git commit -m "feat(dashboard): launcher, run view (ASR/detection/gap), verdict drilldown

Assisted-by: Claude"
```

---

### Task 12: End-to-end honesty + determinism gate

**Files:**
- Create: `tests/integration/test_end_to_end.py`
- Create: `scripts/check_module_imports.py`
- Modify: `pyproject.toml` (add a `[tool.coverage]` note if needed)

**Interfaces:**
- Consumes: the full stack.
- Produces: the v0 definition-of-done gate.

- [ ] **Step 1: Write the import-discipline check** `scripts/check_module_imports.py`

```python
"""Fail if any modules/<x>/ file imports from modules.<y> (x != y) — constitution §2."""
import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PATTERN = re.compile(r"^\s*from\s+modules\.([a-z_]+)", re.M)
violations: list[str] = []
for path in (ROOT / "modules").rglob("*.py"):
    own = path.relative_to(ROOT / "modules").parts[0]
    for m in PATTERN.finditer(path.read_text()):
        if m.group(1) != own:
            violations.append(f"{path}: imports modules.{m.group(1)} (own pkg: {own})")
if violations:
    print("\n".join(violations)); sys.exit(1)
print("module import discipline OK")
```

> Known allowed exceptions in v0: `modules/red/mutator` and `modules/oracles/*` import `modules.targets.synth.rule`/`constants` in tests and (for oracles) at runtime as the sealed-rule authority. To keep the check honest, the check scans `*.py` EXCLUDING `test_*.py`, and the runtime cross-import of the sealed rule is wired via callables in `wiring.py` for `red`; `oracles/held_out` legitimately uses the rule as label authority. Update the check to allow `oracles -> targets.synth` only:

```python
ALLOW = {("oracles", "targets"), ("measure", "targets")}
# ...inside the loop:
        if m.group(1) != own and (own, m.group(1)) not in ALLOW:
            violations.append(...)
# ...and skip test files:
for path in (ROOT / "modules").rglob("*.py"):
    if path.name.startswith("test_"):
        continue
```

- [ ] **Step 2: Write the end-to-end test**

```python
# tests/integration/test_end_to_end.py
import uuid, pytest
from httpx import AsyncClient, ASGITransport
from orchestrator.api import app, init_db

@pytest.fixture
async def client():
    await init_db("sqlite+aiosqlite:///:memory:")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c

async def test_full_run_tells_the_story(client):
    r = await client.post("/runs", json={"n_rounds": 6, "batch_size": 300, "seed": "story"})
    run_id = r.json()["run_id"]
    body = (await client.get(f"/runs/{run_id}/metrics")).json()
    asrs = [x["asr"] for x in body["per_round"] if x["asr"] is not None]
    dets = [x["detection_rate"] for x in body["per_round"] if x["detection_rate"] is not None]
    assert asrs[-1] >= asrs[0]            # ASR climbs
    assert dets[-1] <= dets[0]            # detection falls
    assert body["gap"] is not None and body["gap"] > 0   # silent-wrongness gap is real
```

- [ ] **Step 3: Run the whole suite + checks**

Run:
```bash
python scripts/check_module_imports.py
ruff check . && mypy --strict . && pytest
```
Expected: import check OK; ruff clean; mypy clean; all tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_end_to_end.py scripts/check_module_imports.py
git commit -m "test(orchestrator): end-to-end honesty/determinism gate + import-discipline check

Assisted-by: Claude"
```

---

## Self-Review

**1. Spec coverage:**

| Spec element | Task(s) |
|---|---|
| (1) Operator launches a run | Task 10 (`POST /runs`), Task 11 (Launcher) |
| (2) Synthetic txns, deterministic labels | Task 4 |
| (3) Deliberately-flawed detector | Task 5 |
| (4) Red/mock adversary mutates to evade | Task 6 |
| (5) Five oracles (held-out, metamorphic, invariant, differential stub, judge mock=one vote) | Task 7 |
| (6) Dashboard: ASR / detection / gap / verdict drilldown / oracle vote cards | Task 11 |
| (7) Metrics from persisted rows only; "Not yet measured" | Task 9 (compute), Task 10 (empty state), Task 11 (render) |
| Determinism / replay | Task 8 (replay test), Task 12 |
| Hexagonal boundaries + import discipline | Tasks 1–10 layout, Task 12 check |
| Fail-loud error handling | Task 8 (try/except → status=failed, re-raise) |

No spec element is unmapped.

**2. Placeholder scan:** No "TBD"/"implement later"/"add error handling" — every code step contains real code. The one tuning loop (Task 5 `BIAS`) gives an explicit adjustment rule, not a placeholder.

**3. Type consistency:** `score(txn)->float`, `mutate(txn, score)->Transaction|None`, `vote(ctx)->OracleVote`, `aggregate(list[OracleVote])->Verdict`, `compute_run_metrics(s, run_id)->RunMetrics|None`, `build_components(threshold)->dict` are used identically wherever referenced. `OracleKind`/`Vote`/`TxnSlice` enum values are consistent across loop, oracles, metrics, and API.

**Recommended execution order:** 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 10 → 8 → 9 → 11 → 12. (Wiring/Task 10 lands before the loop integration test in Task 8 can pass; Task 9 metrics before Task 11 renders them.)
