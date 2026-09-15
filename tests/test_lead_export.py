from pathlib import Path

from agregator.company_identifiers import persist_job_company_identifiers
from agregator.lead_export import build_company_lead_rows, export_company_leads_xlsx
from agregator.models import (
    ChannelKind,
    ChannelPurpose,
    CompanyIdentifier,
    CompanyIdentity,
    ContactChannel,
    Decision,
    DiscoveryResult,
    Evidence,
    JobPosting,
)
from agregator.storage import SQLiteStore


def _job(source: str, source_id: str, *, with_nip: bool = False) -> JobPosting:
    identifiers = []
    if with_nip:
        identifiers.append(
            CompanyIdentifier(
                kind="nip",
                value="1234567890",
                source=f"{source}.nip",
                confidence=0.99,
            )
        )
    return JobPosting(
        source=source,
        source_id=source_id,
        url=f"https://{source}.test/{source_id}",
        title="Specjalista ds. sprzedaży",
        company_name="ACME Sp. z o.o.",
        company_name_source=f"{source}.company",
        company_name_confidence=0.99,
        company_identifiers=identifiers,
        city="Gdańsk",
        description=f"Treść z portalu {source}",
    )


def test_final_export_has_one_company_but_preserves_cross_source_coverage(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "leads.sqlite3")
    store.init_schema()
    jobs = [_job("portal_a", "1", with_nip=True), _job("portal_b", "99")]
    store.upsert_jobs(jobs)
    persist_job_company_identifiers(store, jobs)

    company_id = int(store.list_companies()[0]["id"])
    store.save_discovery_result(
        company_id,
        DiscoveryResult(
            company=CompanyIdentity(
                name="ACME Sp. z o.o.",
                city="Gdańsk",
                website_url="https://acme.test",
                domain="acme.test",
                website_confidence=0.99,
            ),
            channels=[
                ContactChannel(
                    kind=ChannelKind.EMAIL,
                    value="partnerzy@acme.test",
                    purpose=ChannelPurpose.BUSINESS_PARTNERSHIP,
                    decision=Decision.GREEN,
                    confidence=0.98,
                    evidence=Evidence(
                        url="https://acme.test/wspolpraca",
                        text="Propozycje współpracy: partnerzy@acme.test",
                        signal="współpraca",
                    ),
                ),
                ContactChannel(
                    kind=ChannelKind.FORM,
                    value="https://acme.test/partnerzy/formularz",
                    purpose=ChannelPurpose.BUSINESS_PARTNERSHIP,
                    decision=Decision.GREEN,
                    confidence=0.95,
                    evidence=Evidence(
                        url="https://acme.test/partnerzy",
                        text="Zostań partnerem — formularz współpracy",
                        signal="zostań partnerem",
                    ),
                ),
            ],
        ),
    )

    rows = build_company_lead_rows(store)

    assert len(rows) == 1
    row = rows[0]
    assert row["company_name"] == "ACME Sp. z o.o."
    assert row["job_count"] == 2
    assert set(str(row["job_sources"]).split(",")) == {"portal_a", "portal_b"}
    assert row["nip"] == "1234567890"
    assert "partnerzy@acme.test" in row["all_contacts"]
    assert "https://acme.test/partnerzy/formularz" in row["all_contacts"]

    result = export_company_leads_xlsx(store, tmp_path / "firmy.xlsx")
    assert result.companies == 1
    assert result.path.exists()
    assert result.path.read_bytes().startswith(b"PK")


def test_final_export_excludes_company_without_green_contact(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "review.sqlite3")
    store.init_schema()
    store.upsert_jobs([_job("portal_a", "1")])
    company_id = int(store.list_companies()[0]["id"])
    store.save_discovery_result(
        company_id,
        DiscoveryResult(
            company=CompanyIdentity(name="ACME Sp. z o.o.", city="Gdańsk"),
            channels=[
                ContactChannel(
                    kind=ChannelKind.EMAIL,
                    value="kontakt@acme.test",
                    purpose=ChannelPurpose.GENERIC,
                    decision=Decision.REVIEW,
                    confidence=0.50,
                    evidence=Evidence(
                        url="https://acme.test/kontakt",
                        text="Kontakt: kontakt@acme.test",
                    ),
                )
            ],
        ),
    )

    assert build_company_lead_rows(store) == []
