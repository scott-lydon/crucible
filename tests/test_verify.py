"""Ground-truth verification: Crucible measured against targets whose
vulnerabilities are known. Perfect recall, zero false positives on the suite."""

from crucible.verify import run_suite


def test_ground_truth_suite_perfect_recall_zero_fpr():
    res = run_suite()
    assert res["macro_recall"] == 1.0
    assert res["macro_false_positive_rate"] == 0.0
    assert res["targets"]["vulnerable"]["recall"] == 1.0
    assert res["targets"]["fully_hardened"]["found"] == []   # negative control: stays quiet
    assert res["targets"]["tool_hardened"]["false_positives"] == []
