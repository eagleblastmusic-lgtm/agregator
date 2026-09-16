from agregator.sources.manpower import parse_manpower_detail
from agregator.storage import SQLiteStore


def _fallback_job(source_id: str, city: str):
    html = f"""
    <html><body>
      <h1>Pracownik produkcji</h1>
      <div>Reference Number: {source_id}</div>
      <main>Dla naszego klienta poszukujemy kandydata.</main>
      <div>Miejsce pracy: {city}, Polska</div>
    </body></html>
    """
    job = parse_manpower_detail(
        f"https://www.manpower.pl/pl/job/{source_id}/pracownik-produkcji",
        html,
    )
    assert job is not None
    return job


def test_manpower_listing_agency_merges_across_cities(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "manpower.sqlite3")
    store.init_schema()

    first = _fallback_job("31001", "Warszawa")
    second = _fallback_job("31002", "Poznań")
    stats = store.upsert_jobs([first, second])

    assert stats.jobs_seen == 2
    assert stats.companies_created == 1

    with store.connect() as connection:
        companies = connection.execute(
            "SELECT id, canonical_name, identity_confidence FROM companies"
        ).fetchall()
        assert len(companies) == 1
        assert companies[0]["canonical_name"] == "ManpowerGroup Sp. z o.o."
        assert companies[0]["identity_confidence"] == 0.98

        jobs = connection.execute(
            "SELECT company_id, company_resolution_method FROM job_postings ORDER BY source_id"
        ).fetchall()
        assert len({row["company_id"] for row in jobs}) == 1
        assert jobs[0]["company_resolution_method"] == "new_company"
        assert jobs[1]["company_resolution_method"] == "exact_name_cross_city"

        locations = {
            row["city"]
            for row in connection.execute(
                "SELECT city FROM company_locations WHERE company_id = ?",
                (companies[0]["id"],),
            )
        }
        assert locations == {"Warszawa", "Poznań"}
