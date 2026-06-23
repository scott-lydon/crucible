from shared.types import OracleVote, Verdict, Vote
from modules.targets.synth.constants import FAIL_THRESHOLD


def aggregate(votes: list[OracleVote]) -> Verdict:
    fail_weight = sum(v.weight for v in votes if v.vote is Vote.FAIL)
    pass_weight = sum(v.weight for v in votes if v.vote is Vote.PASS)
    aggregate_pass = fail_weight < FAIL_THRESHOLD  # detector's "clean" decision stands?
    tally: dict[str, object] = {
        "fail_weight": fail_weight, "pass_weight": pass_weight,
        "by_oracle": {v.kind.value: {"vote": v.vote.value, "weight": v.weight}
                      for v in votes}}
    return Verdict(aggregate_pass=aggregate_pass, fail_weight=fail_weight,
                   pass_weight=pass_weight, votes=tuple(votes), tally=tally)
