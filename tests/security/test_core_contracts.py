"""Security acceptance imports, kept executable as a standalone release gate."""
# ruff: noqa: F401 -- pytest intentionally collects these imported acceptance tests

import re
import subprocess
import sys
from pathlib import Path

from tests.unit.test_errors import test_security_content_is_bounded_and_sanitized
from tests.unit.test_ir_edge_cases import (
    test_duplicate_bibliography_ids_are_rejected,
    test_nested_abstract_has_complete_asset_and_ref_validation,
)
from tests.unit.test_logsetup import (
    test_exception_traceback_is_redacted,
    test_redact_masks_all_secret_shapes,
)
from tests.unit.test_netgate import (
    test_decoded_response_cap_blocks_compressed_bomb,
    test_download_cap_leaves_no_destination,
    test_offline_blocks_before_transport,
    test_redirect_host_is_rechecked,
)


def test_security_collection_floor():
    """Increase the floor with suite additions; never reduce it to hide deletions."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/security", "--collect-only", "-q"],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    count = re.search(r"(\d+) tests? collected", result.stdout)
    assert count is not None, result.stdout
    assert int(count[1]) >= 20
