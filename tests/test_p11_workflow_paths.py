from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

COMMON_PATHS = (
    '"src/agregator/*.py"',
    '"src/agregator/sources/__init__.py"',
    '"src/agregator/sources/base.py"',
    '"src/agregator/sources/registry.py"',
)

EXPECTED_SOURCE_PATHS = {
    "p11-aplikuj-e2e.yml": (
        '"src/agregator/sources/aplikuj.py"',
    ),
    "p11-justjoinit-e2e.yml": (
        '"src/agregator/sources/public_sources.py"',
        '"src/agregator/sources/public_html.py"',
    ),
    "p11-karierawfinansach-e2e.yml": (
        '"src/agregator/sources/public_sources.py"',
        '"src/agregator/sources/public_html.py"',
        '"src/agregator/sources/karierawfinansach.py"',
    ),
    "p11-manpower-e2e.yml": (
        '"src/agregator/sources/manpower.py"',
    ),
    "p11-ngo-e2e.yml": (
        '"src/agregator/sources/ngo.py"',
    ),
    "p11-nofluffjobs-e2e.yml": (
        '"src/agregator/sources/public_sources.py"',
        '"src/agregator/sources/public_html.py"',
    ),
    "p11-ofertypracyedu-e2e.yml": (
        '"src/agregator/sources/ofertypracy_edu.py"',
    ),
    "p11-rocketjobs-e2e.yml": (
        '"src/agregator/sources/public_sources.py"',
        '"src/agregator/sources/public_html.py"',
        '"src/agregator/sources/rocketjobs.py"',
    ),
    "p11-skillshot-e2e.yml": (
        '"src/agregator/sources/public_sources.py"',
        '"src/agregator/sources/public_html.py"',
        '"src/agregator/sources/skillshot.py"',
    ),
}


def test_p11_workflows_use_selective_pull_request_paths() -> None:
    actual = {path.name for path in WORKFLOWS.glob("p11-*-e2e.yml")}
    assert actual == set(EXPECTED_SOURCE_PATHS)

    for filename, source_paths in EXPECTED_SOURCE_PATHS.items():
        text = (WORKFLOWS / filename).read_text(encoding="utf-8")

        assert '"src/agregator/**"' not in text
        assert '"tests/**"' not in text
        assert f'".github/workflows/{filename}"' in text

        for path in COMMON_PATHS:
            assert path in text, f"{filename} does not watch shared runtime path {path}"
        for path in source_paths:
            assert path in text, f"{filename} does not watch source path {path}"


def test_source_specific_adapters_do_not_trigger_unrelated_p11_workflows() -> None:
    dedicated = {
        "p11-aplikuj-e2e.yml": "aplikuj.py",
        "p11-karierawfinansach-e2e.yml": "karierawfinansach.py",
        "p11-manpower-e2e.yml": "manpower.py",
        "p11-ngo-e2e.yml": "ngo.py",
        "p11-ofertypracyedu-e2e.yml": "ofertypracy_edu.py",
        "p11-rocketjobs-e2e.yml": "rocketjobs.py",
        "p11-skillshot-e2e.yml": "skillshot.py",
    }

    for filename, own_adapter in dedicated.items():
        text = (WORKFLOWS / filename).read_text(encoding="utf-8")
        for other_filename, other_adapter in dedicated.items():
            if other_filename == filename:
                continue
            assert f'"src/agregator/sources/{other_adapter}"' not in text

        assert f'"src/agregator/sources/{own_adapter}"' in text
