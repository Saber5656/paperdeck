"""Explicitly collect existing SEC-AC coverage in the CI-visible suite.

The source modules remain in their owning layer for local development. Re-exporting
selected attack tests here makes ``pytest tests/security`` execute the same controls.
"""

from tests.e2e import test_doctor as issue50
from tests.engine import test_arxiv_html_engine as issue25
from tests.unit import (
    test_arxiv_metadata as issue11_12,
)
from tests.unit import (
    test_latex_bib as issue20,
)
from tests.unit import (
    test_latex_engine as issue18,
)
from tests.unit import (
    test_latex_graphics as issue21,
)
from tests.unit import (
    test_render_assets as issue39,
)
from tests.unit.test_arxiv_metadata import test_dtd_rejected_before_cache
from tests.unit.test_config import test_unknown_keys_and_schema_version
from tests.unit.test_errors import test_security_content_is_bounded_and_sanitized
from tests.unit.test_html_structure import test_structure_maps_tree_table_list_and_safe_svg
from tests.unit.test_latex_project import test_include_escape_and_cycle_fail
from tests.unit.test_llm_cache_local import test_llm_cache_key_and_private_value_file
from tests.unit.test_llm_client_local import test_invalid_json_retry_is_recorded_before_validation
from tests.unit.test_llm_schemas_local import test_bib_rejects_unsafe_url
from tests.unit.test_logsetup import test_redact_masks_all_secret_shapes
from tests.unit.test_netgate import (
    test_redirect_host_is_rechecked,
    test_remote_plain_http_llm_is_rejected,
)
from tests.unit.test_pdf_citations_local import test_numeric_and_structural_links_are_conservative
from tests.unit.test_pdf_equations_local import test_budget_degradation_keeps_image_asset
from tests.unit.test_prompts_local import test_prompts_have_guard_and_validate_slots
from tests.unit.test_renderer import test_render_escaping_csp_determinism_and_refs
from tests.unit.test_selfcontain_validator import test_reject_active_content
from tests.unit.test_tarsafe import (
    test_rejects_links_devices_and_rolls_back_after_stream_cap,
    test_rejects_traversal,
)

# pytest uses this export list to retain the imported tests; it also makes the
# collection contract explicit to reviewers and the suite-count meta-test.
__all__ = (
    "test_bib_rejects_unsafe_url",
    "test_budget_degradation_keeps_image_asset",
    "test_dtd_rejected_before_cache",
    "test_include_escape_and_cycle_fail",
    "test_invalid_json_retry_is_recorded_before_validation",
    "test_llm_cache_key_and_private_value_file",
    "test_numeric_and_structural_links_are_conservative",
    "test_prompts_have_guard_and_validate_slots",
    "test_redact_masks_all_secret_shapes",
    "test_redirect_host_is_rechecked",
    "test_reject_active_content",
    "test_rejects_links_devices_and_rolls_back_after_stream_cap",
    "test_rejects_traversal",
    "test_remote_plain_http_llm_is_rejected",
    "test_render_escaping_csp_determinism_and_refs",
    "test_security_content_is_bounded_and_sanitized",
    "test_structure_maps_tree_table_list_and_safe_svg",
    "test_unknown_keys_and_schema_version",
)

# SEC-AC modules with tests in the owning layer. Keep this tuple synchronized
# with the issue list when tests are added or moved.
SEC_AC_MODULES = (
    "02-errors",
    "03-logging",
    "04-config",
    "08-netgate",
    "10-tarsafe",
    issue11_12.__name__,
    "13-latex-project",
    issue18.__name__,
    issue20.__name__,
    issue21.__name__,
    "24-html-structure",
    issue25.__name__,
    "27-llm-client",
    "28-llm-cache",
    "30-llm-schemas-prompts",
    "34-pdf-equations",
    "35-pdf-citations",
    "38-renderer",
    issue39.__name__,
    "40-selfcontain-validator",
    issue50.__name__,
)
