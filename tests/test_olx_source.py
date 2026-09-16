from agregator.sources.olx import parse_olx_payload


def test_parse_olx_prefers_company_name() -> None:
    payload = {
        "data": [
            {
                "id": 1034527314,
                "title": "Kasjer Sprzedawca",
                "url": "https://www.olx.pl/oferta/praca/test.html",
                "description": "Opis",
                "created_time": "2026-09-10T10:00:00+02:00",
                "last_refresh_time": "2026-09-12T10:00:00+02:00",
                "location": {"city": {"name": "Koleczkowo"}},
                "user": {
                    "company_name": "Słodka Chatka Sp. z o.o.",
                    "name": "Kazimierz",
                },
            }
        ]
    }

    jobs = parse_olx_payload(payload)

    assert len(jobs) == 1
    assert jobs[0].source == "olx"
    assert jobs[0].source_id == "1034527314"
    assert jobs[0].company_name == "Słodka Chatka Sp. z o.o."
    assert jobs[0].company_name_source == "user.company_name"
    assert jobs[0].company_name_confidence == 0.95
    assert jobs[0].city == "Koleczkowo"


def test_parse_olx_marks_account_name_as_low_confidence_fallback() -> None:
    payload = {
        "data": [
            {
                "id": 1,
                "title": "Piekarz",
                "url": "https://www.olx.pl/oferta/praca/piekarz.html",
                "location": {"city": {"name": "Gdynia"}},
                "user": {"company_name": "", "name": "Kazimierz"},
                "contact": {"name": "Kazimierz"},
            }
        ]
    }

    job = parse_olx_payload(payload)[0]

    assert job.company_name == "Kazimierz"
    assert job.company_name_source == "user.name"
    assert job.company_name_confidence == 0.45


def test_parse_olx_skips_offer_without_identity() -> None:
    payload = {
        "data": [
            {
                "id": 1,
                "title": "Piekarz",
                "url": "https://www.olx.pl/oferta/praca/piekarz.html",
                "user": {"company_name": "", "name": ""},
            }
        ]
    }

    assert parse_olx_payload(payload) == []
