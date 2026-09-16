from pathlib import Path

from agregator.models import (
    ChannelKind,
    ChannelPurpose,
    CompanyIdentity,
    ContactChannel,
    Decision,
    DiscoveryResult,
    Evidence,
    JobPosting,
)
from agregator.storage import SQLiteStore


def test_save_discovery_result_persists_green_channel(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "enrichment.sqlite3")
    store.init_schema()
    store.upsert_jobs(
        [
            JobPosting(
                source="test",
                source_id="1",
                url="https://jobs.test/1",
                title="Sprzedawca",
                company_name="Firma Testowa",
                company_name_source="company.name",
                company_name_confidence=0.98,
                city="Gdynia",
            )
        ]
    )
    company = store.list_companies()[0]

    result = DiscoveryResult(
        company=CompanyIdentity(
            name="Firma Testowa",
            city="Gdynia",
            website_url="https://firma.test",
            domain="firma.test",
            website_confidence=0.94,
        ),
        channels=[
            ContactChannel(
                kind=ChannelKind.EMAIL,
                value="wspolpraca@firma.test",
                purpose=ChannelPurpose.BUSINESS_PARTNERSHIP,
                decision=Decision.GREEN,
                confidence=0.99,
                evidence=Evidence(
                    url="https://firma.test/wspolpraca",
                    text="Propozycje współpracy: wspolpraca@firma.test",
                    signal="propozycje wspolpracy",
                ),
            )
        ],
    )

    store.save_discovery_result(int(company["id"]), result)
    channels = store.list_green_channels()
    updated_company = store.list_companies()[0]

    assert len(channels) == 1
    assert channels[0]["value"] == "wspolpraca@firma.test"
    assert channels[0]["evidence_url"] == "https://firma.test/wspolpraca"
    assert updated_company["green_channels"] == 1
    assert updated_company["website_url"] == "https://firma.test"
