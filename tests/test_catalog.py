from agregator.catalog import catalog_summary, filter_catalog, load_source_catalog


def test_source_catalog_matches_master_list() -> None:
    entries = load_source_catalog()
    summary = catalog_summary(entries)

    assert summary["total"] == 91
    assert summary["implemented"] == 11
    assert summary["remaining"] == 80
    assert summary["priorities"] == {"A0": 14, "A1": 36, "B": 24, "C": 17}
    assert summary["implemented_adapters"] == [
        "pracuj",
        "olx",
        "justjoinit",
        "nofluffjobs",
        "rocketjobs",
        "epraca",
        "jooble",
        "careerjet",
        "karierawfinansach",
        "skillshot",
        "adzuna",
    ]


def test_filter_catalog_a0_pending() -> None:
    entries = load_source_catalog()
    pending_a0 = filter_catalog(entries, priority="A0", implemented=False)

    assert len(pending_a0) == 5
    assert all(entry.priority == "A0" for entry in pending_a0)
    assert all(not entry.implemented for entry in pending_a0)
