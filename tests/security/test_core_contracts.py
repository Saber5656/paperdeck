"""Security acceptance imports, kept executable as a standalone release gate."""
# ruff: noqa: F401 -- pytest intentionally collects these imported acceptance tests

import re
import subprocess
import sys
from pathlib import Path

from tests.e2e.test_doctor import (
    doctor_environment,
    test_doctor_isolates_failures_and_redacts_key,
)
from tests.unit.test_errors import test_security_content_is_bounded_and_sanitized
from tests.unit.test_input_security_acceptance import (
    test_config_is_frozen_hashable_and_never_serializes_secret,
    test_netgate_user_agent_rate_limit_and_local_llm_cap,
    test_tar_header_count_bomb_is_rejected_before_writes,
)
from tests.unit.test_ir_cache_acceptance import (
    test_cache_rejects_symlink_escape_for_read_and_write,
)
from tests.unit.test_ir_edge_cases import (
    test_duplicate_bibliography_ids_are_rejected,
    test_nested_abstract_has_complete_asset_and_ref_validation,
)
from tests.unit.test_latex_bib import test_bbl_cleaner_handles_links_math_and_duplicate_keys
from tests.unit.test_latex_graphics_resolution import test_graphics_escape_is_security_error
from tests.unit.test_latex_refs_resolution import (
    test_reference_resolution_rejects_unmatched_sentinel,
)
from tests.unit.test_llm_schema_acceptance import (
    test_model_response_limits_reject_untrusted_oversized_or_invalid_data,
)
from tests.unit.test_llm_terminal_errors import (
    test_terminal_http_errors_have_a_stable_boundary_error,
)
from tests.unit.test_llm_token_budget import (
    test_unknown_price_token_reservations_cannot_exceed_two_million,
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
from tests.unit.test_render_assets import (
    test_budget_drops_figures_before_tables_and_preserves_equations,
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
    assert int(count[1]) >= 92
