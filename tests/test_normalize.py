from agregator.normalize import company_key, normalize_company_name, normalize_text


def test_normalize_text_handles_polish_diacritics_and_punctuation() -> None:
    assert normalize_text("  Łódź / Gdańsk  ") == "lodz gdansk"


def test_company_name_removes_common_polish_legal_forms() -> None:
    variants = [
        "ACME Sp. z o.o.",
        "ACME spółka z ograniczoną odpowiedzialnością",
        "ACME S.A.",
        "ACME spółka akcyjna",
        "ACME sp. k.",
        "ACME spółka komandytowa",
        "ACME sp. z o.o. sp. k.",
    ]

    assert {normalize_company_name(value) for value in variants} == {"acme"}


def test_company_name_removes_selected_international_legal_forms() -> None:
    variants = [
        "ACME Ltd.",
        "ACME LLC",
        "ACME Inc.",
        "ACME GmbH",
    ]

    assert {normalize_company_name(value) for value in variants} == {"acme"}


def test_company_key_keeps_location_separate_from_normalized_name() -> None:
    assert company_key("ACME Sp. z o.o.", "Gdańsk") == "acme|gdansk"
