from agregator.models import SearchCandidate
from agregator.resolver import choose_official_website, score_candidate


def test_job_portal_is_blocked() -> None:
    candidate = SearchCandidate(
        title="ABC Sp. z o.o. — oferty pracy",
        url="https://www.pracuj.pl/praca/abc",
        snippet="ABC Gdynia",
    )
    assert score_candidate(candidate, "ABC Sp. z o.o.", "Gdynia") == 0.0


def test_matching_company_domain_wins() -> None:
    candidates = [
        SearchCandidate(
            title="Katalog firm — Słodka Chatka",
            url="https://katalog.example/slodka-chatka",
            snippet="Koleczkowo",
        ),
        SearchCandidate(
            title="Słodka Chatka — kontakt",
            url="https://slodkachatka.pl/kontakt",
            snippet="Piekarnia w Koleczkowie",
        ),
    ]
    chosen = choose_official_website(candidates, "Słodka Chatka", "Koleczkowo")
    assert chosen is not None
    assert chosen.url == "https://slodkachatka.pl/kontakt"
    assert chosen.score >= 0.45
