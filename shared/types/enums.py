from enum import StrEnum


class Pillar(StrEnum):
    TARGETS = "targets"
    ORACLES = "oracles"
    RED = "red"
    BLUE = "blue"
    MEASURE = "measure"
    ORCHESTRATOR = "orchestrator"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class OracleKind(StrEnum):
    HELD_OUT = "held_out"
    METAMORPHIC = "metamorphic"
    INVARIANT = "invariant"
    DIFFERENTIAL = "differential"
    PROPERTY_FUZZ = "property_fuzz"
    LLM_JUDGE = "llm_judge"


class Vote(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    ABSTAIN = "abstain"


class TxnSlice(StrEnum):
    VALIDATION = "validation"
    HOLDOUT = "holdout"


class Origin(StrEnum):
    SYNTHETIC = "synthetic"
    MUTATED = "mutated"
