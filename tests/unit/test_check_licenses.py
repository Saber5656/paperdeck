from scripts.check_licenses import check_licenses


def test_gpl_runtime_is_rejected_but_dev_only_is_reported() -> None:
    rows = [
        {"Name": "runtime-gpl", "License": "GPL-3.0-only"},
        {"Name": "dev-gpl", "License": "GPL-3.0-only"},
    ]
    violations, notices = check_licenses(rows, {"runtime-gpl"})
    assert [row["Name"] for row in violations] == ["runtime-gpl"]
    assert any(row["Name"] == "dev-gpl" for row in notices)


def test_dual_license_passes_when_one_license_is_allowed() -> None:
    violations, _ = check_licenses([{"Name": "dual", "License": "GPL-3.0-only OR MIT"}], {"dual"})
    assert violations == []


def test_and_expression_cannot_hide_a_copyleft_obligation():
    rows = [{"Name": "mixed", "License": "MIT AND GPL-3.0-only"}]
    assert check_licenses(rows, {"mixed"})[0] == rows


def test_certifi_exception_is_limited_to_its_existing_mpl_license():
    rows = [
        {"Name": "certifi", "License": "Mozilla Public License 2.0 (MPL 2.0)"},
        {"Name": "other", "License": "MPL-2.0"},
    ]
    assert check_licenses(rows, {"certifi", "other"})[0] == [rows[1]]
    changed = [{"Name": "certifi", "License": "GPL-3.0-only"}]
    assert check_licenses(changed, {"certifi"})[0] == changed


def test_pdfium_dependency_notice_review_is_version_bound():
    row = {
        "Name": "pypdfium2",
        "Version": "5.13.0",
        "License": "BSD-3-Clause, Apache-2.0, dependency licenses",
    }
    assert check_licenses([row], {"pypdfium2"})[0] == []
    new = {**row, "Version": "5.14.0"}
    assert check_licenses([new], {"pypdfium2"})[0] == [new]
