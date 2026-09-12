"""Collect the Issue 52 PDF acceptance tests in the security suite."""

from tests.e2e.test_pipeline_pdf import (
    test_pdf_cli_budget_zero_and_decline_send_no_requests,
    test_pdf_cli_e2e_has_images_citations_and_real_cost,
    test_pdf_prompt_injection_is_escaped_and_no_external_request,
)

__all__ = [
    "test_pdf_cli_budget_zero_and_decline_send_no_requests",
    "test_pdf_cli_e2e_has_images_citations_and_real_cost",
    "test_pdf_prompt_injection_is_escaped_and_no_external_request",
]
