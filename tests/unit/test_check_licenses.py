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
