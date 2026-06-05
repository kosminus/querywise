"""Shared pytest fixtures.

These tests run without a live database or LLM provider — they exercise the
Phase 0 platform plumbing (secrets, jobs, rate limiting, telemetry, SQL safety,
health probes) in isolation.
"""

import pytest

from app.core.secrets import reset_secrets_provider
from app.jobs import reset_job_queue


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset process-wide singletons between tests so config changes take effect."""
    reset_secrets_provider()
    reset_job_queue()
    yield
    reset_secrets_provider()
    reset_job_queue()
