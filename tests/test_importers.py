from pathlib import Path

from agregator.importers import load_jobs_csv


def test_load_jobs_csv(tmp_path: Path) -> None:
    path = tmp_path / "jobs.csv"
    path.write_text(
        "source,source_id,url,title,company_name,city\n"
        "portal-x,42,https://example.test/42,Kasjer,Firma Testowa,Gdynia\n",
        encoding="utf-8",
    )

    jobs = load_jobs_csv(path)

    assert len(jobs) == 1
    assert jobs[0].source == "portal-x"
    assert jobs[0].source_id == "42"
    assert jobs[0].company_name == "Firma Testowa"
    assert jobs[0].company_name_confidence == 1.0


def test_load_jobs_csv_requires_core_columns(tmp_path: Path) -> None:
    path = tmp_path / "broken.csv"
    path.write_text("url,title\nhttps://example.test/1,Kasjer\n", encoding="utf-8")

    try:
        load_jobs_csv(path)
    except ValueError as exc:
        assert "company_name" in str(exc)
    else:
        raise AssertionError("missing columns should raise ValueError")
