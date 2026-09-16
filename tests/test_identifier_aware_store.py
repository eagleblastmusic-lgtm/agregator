from pathlib import Path

from agregator.identifier_store import IdentifierAwareSQLiteStore, strongest_company_identifier
from agregator.models import CompanyIdentifier, JobPosting


def _job(
    source_id: str,
    *,
    company_name: str = "PwC",
    city: str | None = None,
    identifiers: list[CompanyIdentifier] | None = None,
) -> JobPosting:
    return JobPosting(
        source="karierawfinansach",
        source_id=source_id,
        url=f"https://jobs.example/{source_id}",
        title=f"Oferta {source_id}",
        company_name=company_name,
        company_name_source="html.selector",
        company_name_confidence=0.80,
        company_identifiers=identifiers or [],
        city=city,
    )


def _profile(confidence: float = 0.99) -> CompanyIdentifier:
    return CompanyIdentifier(
        kind="karierawfinansach_employer_profile",
        value="https://www.karierawfinansach.pl/pracodawca/pwc/",
        source="karierawfinansach.detail.employer_profile",
        confidence=confidence,
    )


def test_same_strong_employer_profile_merges_short_name_jobs(tmp_path: Path) -> None:
    store = IdentifierAwareSQLiteStore(tmp_path / "profile.sqlite3")
    store.init_schema()

    stats = store.upsert_jobs(
        [
            _job("101", identifiers=[_profile()]),
            _job("102", identifiers=[_profile()]),
            _job("103", identifiers=[_profile()]),
        ]
    )

    companies = store.list_companies()
    assert stats.jobs_inserted == 3
    assert stats.companies_created == 1
    assert len(companies) == 1
    assert companies[0]["canonical_name"] == "PwC"
    assert companies[0]["job_count"] == 3

    methods = {row["method"]: row["job_count"] for row in store.company_resolution_stats()}
    assert methods["new_company"] == 1
    assert methods["stable_source_key"] == 2


def test_short_name_without_strong_identifier_remains_separate(tmp_path: Path) -> None:
    store = IdentifierAwareSQLiteStore(tmp_path / "no-id.sqlite3")
    store.init_schema()

    stats = store.upsert_jobs([_job("201"), _job("202")])

    assert stats.companies_created == 2
    assert len(store.list_companies()) == 2


def test_low_confidence_profile_does_not_merge(tmp_path: Path) -> None:
    store = IdentifierAwareSQLiteStore(tmp_path / "weak-profile.sqlite3")
    store.init_schema()

    stats = store.upsert_jobs(
        [
            _job("301", identifiers=[_profile(0.94)]),
            _job("302", identifiers=[_profile(0.94)]),
        ]
    )

    assert stats.companies_created == 2
    assert len(store.list_companies()) == 2


def test_same_nip_can_merge_alias_names(tmp_path: Path) -> None:
    store = IdentifierAwareSQLiteStore(tmp_path / "nip.sqlite3")
    store.init_schema()
    nip = CompanyIdentifier(
        kind="nip",
        value="525-000-77-38",
        source="official.nip",
        confidence=0.99,
    )

    stats = store.upsert_jobs(
        [
            _job("401", company_name="Example Polska S.A.", identifiers=[nip]),
            _job("402", company_name="Example Polska", identifiers=[nip]),
        ]
    )

    companies = store.list_companies()
    assert stats.companies_created == 1
    assert len(companies) == 1
    aliases = str(companies[0]["aliases"])
    assert "Example Polska S.A." in aliases
    assert "Example Polska" in aliases


def test_generic_organization_id_is_not_used_as_strong_key(tmp_path: Path) -> None:
    store = IdentifierAwareSQLiteStore(tmp_path / "generic.sqlite3")
    store.init_schema()
    generic = CompanyIdentifier(
        kind="organization_id",
        value="123",
        source="jsonld.identifier",
        confidence=0.99,
    )

    stats = store.upsert_jobs(
        [
            _job("501", identifiers=[generic]),
            _job("502", identifiers=[generic]),
        ]
    )

    assert stats.companies_created == 2
    assert len(store.list_companies()) == 2


def test_profile_identifier_normalizes_www_query_fragment_and_trailing_slash() -> None:
    first = _job(
        "601",
        identifiers=[
            CompanyIdentifier(
                kind="karierawfinansach_employer_profile",
                value="https://WWW.KARIERAWFINANSACH.PL/pracodawca/pwc/?utm_source=x#jobs",
                confidence=0.99,
            )
        ],
    )
    second = _job("602", identifiers=[_profile()])

    assert strongest_company_identifier(first) == strongest_company_identifier(second)
