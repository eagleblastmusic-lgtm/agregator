from agregator.company_resolution import (
    CompanyCandidate,
    choose_company_candidate,
    is_distinctive_company_name,
)


def _candidate(
    *,
    company_id: int = 1,
    name: str = "acme logistics",
    city: str | None = "gdansk",
    confidence: float = 0.95,
) -> CompanyCandidate:
    return CompanyCandidate(
        id=company_id,
        normalized_name=name,
        normalized_city=city,
        identity_confidence=confidence,
    )


def test_distinctive_name_guard_rejects_short_or_generic_names() -> None:
    assert not is_distinctive_company_name("abc")
    assert not is_distinctive_company_name("firma")
    assert is_distinctive_company_name("acme logistics")
    assert is_distinctive_company_name("biedronka")


def test_exact_name_and_city_is_strongest_match() -> None:
    decision = choose_company_candidate(
        "ACME Logistics Sp. z o.o.",
        "Gdańsk",
        0.95,
        [_candidate()],
    )

    assert decision.company_id == 1
    assert decision.method == "exact_name_city"
    assert decision.confidence == 1.0


def test_strong_distinctive_name_can_match_across_cities() -> None:
    decision = choose_company_candidate(
        "ACME Logistics",
        "Warszawa",
        0.95,
        [_candidate()],
    )

    assert decision.company_id == 1
    assert decision.method == "exact_name_cross_city"
    assert decision.confidence == 0.88


def test_low_confidence_name_does_not_match_across_cities() -> None:
    decision = choose_company_candidate(
        "ACME Logistics",
        "Warszawa",
        0.45,
        [_candidate()],
    )

    assert decision.company_id is None
    assert decision.method == "insufficient_cross_city_evidence"


def test_short_name_does_not_match_across_cities() -> None:
    decision = choose_company_candidate(
        "ABC",
        "Warszawa",
        0.95,
        [_candidate(name="abc")],
    )

    assert decision.company_id is None
    assert decision.method == "insufficient_cross_city_evidence"


def test_multiple_exact_candidates_without_city_are_ambiguous() -> None:
    decision = choose_company_candidate(
        "ACME Logistics",
        None,
        0.95,
        [
            _candidate(company_id=1, city="gdansk"),
            _candidate(company_id=2, city="warszawa"),
        ],
    )

    assert decision.company_id is None
    assert decision.method == "ambiguous_exact_name"
