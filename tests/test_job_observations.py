import json
from pathlib import Path

from agregator.ingest import ingest_source
from agregator.models import CompanyIdentifier, CompanyWebsiteCandidate, JobPosting
from agregator.sources.base import SourceBatch
from agregator.storage import SQLiteStore


class SequenceSource:
    def __init__(self, name: str, batches: list[SourceBatch]) -> None:
        self.name = name
        self._batches = batches

    async def collect(self, cursor: str | None = None) -> SourceBatch:
        index = int(cursor or "0")
        return self._batches[index]


def _job(
    source: str,
    source_id: str,
    *,
    description: str,
    website: str | None = None,
) -> JobPosting:
    candidates = []
    if website:
        candidates.append(
            CompanyWebsiteCandidate(
                url=website,
                source=f"{source}.employer_url",
                confidence=0.9,
            )
        )
    return JobPosting(
        source=source,
        source_id=source_id,
        url=f"https://{source}.test/jobs/{source_id}",
        title="Specjalista ds. sprzedaży",
        company_name="ACME Sp. z o.o.",
        company_name_source=f"{source}.company",
        company_name_confidence=0.95,
        company_identifiers=[
            CompanyIdentifier(
                kind="nip",
                value="1234567890",
                source=f"{source}.nip",
                confidence=0.98,
            )
        ],
        company_website_candidates=candidates,
        city="Gdańsk",
        description=description,
    )


async def test_same_vacancy_from_two_sources_is_never_cross_source_deduplicated(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "all-sources.sqlite3")

    await ingest_source(
        SequenceSource(
            "portal_a",
            [SourceBatch(jobs=[_job("portal_a", "42", description="Wersja A")], next_cursor=None)],
        ),
        store,
    )
    await ingest_source(
        SequenceSource(
            "portal_b",
            [
                SourceBatch(
                    jobs=[
                        _job(
                            "portal_b",
                            "99",
                            description="Wersja B z dodatkowym kontaktem w treści",
                            website="https://acme.test",
                        )
                    ],
                    next_cursor=None,
                )
            ],
        ),
        store,
    )

    with store.connect() as connection:
        jobs = connection.execute(
            "SELECT source, source_id, description FROM job_postings ORDER BY source"
        ).fetchall()
        observations = connection.execute(
            """
            SELECT source, source_id, description, payload_json
            FROM job_posting_observations
            ORDER BY id
            """
        ).fetchall()

    assert [(row["source"], row["source_id"]) for row in jobs] == [
        ("portal_a", "42"),
        ("portal_b", "99"),
    ]
    assert len(observations) == 2
    assert observations[0]["description"] == "Wersja A"
    assert observations[1]["description"] == "Wersja B z dodatkowym kontaktem w treści"

    second_payload = json.loads(observations[1]["payload_json"])
    assert second_payload["company_website_candidates"][0]["url"] == "https://acme.test"
    assert second_payload["company_identifiers"][0]["value"] == "1234567890"


async def test_repeated_source_record_keeps_every_observation_even_when_current_view_updates(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "history.sqlite3")
    source = SequenceSource(
        "portal",
        [
            SourceBatch(
                jobs=[_job("portal", "1", description="Pierwsza wersja")],
                next_cursor="1",
            ),
            SourceBatch(
                jobs=[
                    _job(
                        "portal",
                        "1",
                        description="Druga wersja z dodatkowymi danymi",
                        website="https://acme.test",
                    )
                ],
                next_cursor=None,
            ),
        ],
    )

    result = await ingest_source(source, store, pages=2)

    assert result.stats.jobs_seen == 2
    assert result.stats.jobs_inserted == 1
    assert result.stats.jobs_updated == 1

    with store.connect() as connection:
        current = connection.execute(
            "SELECT description FROM job_postings WHERE source = 'portal' AND source_id = '1'"
        ).fetchone()
        observations = connection.execute(
            """
            SELECT description, source_run_id, payload_json
            FROM job_posting_observations
            WHERE source = 'portal' AND source_id = '1'
            ORDER BY id
            """
        ).fetchall()

    assert current["description"] == "Druga wersja z dodatkowymi danymi"
    assert [row["description"] for row in observations] == [
        "Pierwsza wersja",
        "Druga wersja z dodatkowymi danymi",
    ]
    assert all(row["source_run_id"] == result.run_id for row in observations)
    assert json.loads(observations[0]["payload_json"])["company_website_candidates"] == []
    assert json.loads(observations[1]["payload_json"])["company_website_candidates"][0][
        "url"
    ] == "https://acme.test"
