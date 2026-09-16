from agregator.url_utils import canonicalize_http_url, is_tracking_query_key


def test_canonicalize_url_normalizes_host_default_port_and_tracking_params() -> None:
    value = canonicalize_http_url(
        "HTTPS://Example.COM:443/partner?utm_source=footer&mode=b2b&fbclid=abc#form"
    )
    assert value == "https://example.com/partner?mode=b2b"


def test_canonicalize_url_resolves_relative_and_preserves_functional_query_order() -> None:
    value = canonicalize_http_url(
        "../partner?mode=b2b&locale=pl&utm_campaign=spring#send",
        base_url="https://example.com/kontakt/formularz",
    )
    assert value == "https://example.com/partner?mode=b2b&locale=pl"


def test_canonicalize_url_rejects_non_http_and_userinfo() -> None:
    assert canonicalize_http_url("mailto:partner@example.com") is None
    assert canonicalize_http_url("javascript:void(0)") is None
    assert canonicalize_http_url("https://user:secret@example.com/form") is None


def test_tracking_query_key_is_deliberately_conservative() -> None:
    assert is_tracking_query_key("utm_medium") is True
    assert is_tracking_query_key("GCLID") is True
    assert is_tracking_query_key("campaign") is False
    assert is_tracking_query_key("source") is False
