from agregator.sources import default_registry


def test_default_registry_contains_olx() -> None:
    registry = default_registry()

    assert registry.names() == ["olx"]
    source = registry.create("OLX")
    assert source.name == "olx"
