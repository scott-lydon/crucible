from crucible.catalog import StrategyCatalog


def test_catalog_persists_across_sessions(tmp_path):
    db = str(tmp_path / "cat.db")
    c = StrategyCatalog(db)
    c.record_win("jailbreak", "roleplay")
    c.record_win("jailbreak", "roleplay")
    c.record_win("tool_abuse", "base64")
    assert c.total_wins() == 3
    c.close()

    c2 = StrategyCatalog(db)  # reopen: persistence
    assert c2.total_wins() == 3
    assert c2.top_techniques("jailbreak")[0] == "roleplay"
    c2.close()
