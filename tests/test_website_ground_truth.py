from pathlib import Path

from agregator.models import JobPosting
from agregator.storage import SQLiteStore
from agregator.website_ground_truth import (
    NO_WEBSITE,
    WebsiteGroundTruthLabel,
    evaluate_website_resolution,
    evaluate_website_resolution_csv,
    export_website_ground_truth_template,
    load_website_ground_truth_csv,
    normalize_domain,
)


def _seed(store: SQLiteStore) -> list[int]:
    store.init_schema()
    store.upsert_jobs(
        [
            JobPosting(
                source="a",
                source_id="1",
                url="https://jobs.test/1",
                title="A",
                company_name="Alpha Systems",
                company_name_source="api.company",
                company_name_confidence=0.95,
                city="Gdańsk",
            ),
            JobPosting(
                source="b",
                source_id="2",
                url="https://jobs.test/2",
                title="B",
                company_name="Beta Labs",
                company_name_source="api.company",
                company_name_confidence=0.95,
                city="Gdynia",
            ),
            JobPosting(
                source="c",
                source_id="3",
                url="https://jobs.test/3",
                title="C",
                company_name="Gamma Trade",
                company_name_source="api.company",
                company_name_confidence=0.95,
                city="Sopot",
            ),
        ]
    )
    companies = store.list_companies(limit=10)
    ids = {str(row["canonical_name"]): int(row["id"]) for row in companies}
    with store.connect() as connection:
        connection.execute(
            "UPDATE companies SET website_url = ?, website_confidence = ? WHERE id = ?",
            ("https://www.alpha.example/contact", 0.91, ids["Alpha Systems"]),
        )
        connection.execute(
            "UPDATE companies SET website_url = ?, website_confidence = ? WHERE id = ?",
            ("https://wrong.example", 0.80, ids["Beta Labs"]),
        )
    return [ids["Alpha Systems"], ids["Beta Labs"], ids["Gamma Trade"]]


def test_website_resolution_metrics_count_wrong_domain_as_fp_and_fn(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "website.sqlite3")
    alpha_id, beta_id, gamma_id = _seed(store)

    report = evaluate_website_resolution(
        store,
        [
            WebsiteGroundTruthLabel(alpha_id, "alpha.example"),
            WebsiteGroundTruthLabel(beta_id, "beta.example"),
            WebsiteGroundTruthLabel(gamma_id, None),
        ],
    )

    assert report.labeled_rows == 3
    assert report.matched_rows == 3
    assert report.true_positive == 1
    assert report.false_positive == 1
    assert report.false_negative == 1
    assert report.true_negative == 1
    assert report.wrong_domain == 1
    assert report.precision == 0.5
    assert report.recall == 0.5
    assert report.f1 == 0.5
    assert report.accuracy == 0.6667
    assert report.excluded_rows == 0


def test_website_ground_truth_loader_and_template(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "template.sqlite3")
    _seed(store)

    output = export_website_ground_truth_template(store, tmp_path / "website_truth.csv")
    text = output.read_text(encoding="utf-8-sig")
    assert "truth_domain" in text
    assert "predicted_domain" in text
    assert "alpha.example" in text

    truth = tmp_path / "labeled.csv"
    truth.write_text(
        "company_id,truth_domain\n"
        "1,https://www.alpha.example/path\n"
        f"2,{NO_WEBSITE}\n"
        "3,\n",
        encoding="utf-8",
    )
    labels = load_website_ground_truth_csv(truth)
    assert len(labels) == 2
    assert labels[0].truth_domain == "alpha.example"
    assert labels[1].truth_domain is None
    assert normalize_domain("WWW.Example.COM/path") == "example.com"


def test_website_ground_truth_exclusion_is_separate_from_no_website(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "excluded.sqlite3")
    alpha_id, beta_id, gamma_id = _seed(store)
    truth = tmp_path / "excluded_truth.csv"
    truth.write_text(
        "company_id,truth_domain\n"
        f"{alpha_id},alpha.example\n"
        f"{beta_id},__exclude__\n"
        f"{gamma_id},{NO_WEBSITE}\n",
        encoding="utf-8",
    )

    labels = load_website_ground_truth_csv(truth)
    report = evaluate_website_resolution_csv(store, truth)

    assert len(labels) == 2
    assert labels[0].company_id == alpha_id
    assert labels[0].truth_domain == "alpha.example"
    assert labels[1].company_id == gamma_id
    assert labels[1].truth_domain is None
    assert report.labeled_rows == 2
    assert report.excluded_rows == 1
    assert report.true_positive == 1
    assert report.true_negative == 1
    assert report.f1 == 1.0
