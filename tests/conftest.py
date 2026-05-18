from __future__ import annotations

import pytest


@pytest.fixture(scope="session", autouse=True)
def _disable_headless_env_inheritance():
    """Belt and suspenders: prevent a developer's local `somatic headless start`
    session from bleeding into pytest. `headless.apply_active_env()` exits
    early when this is set, and `subprocess_env()` skips its overlay too.
    """
    import os

    previous = os.environ.get("SOMATIC_HEADLESS_DISABLE")
    os.environ["SOMATIC_HEADLESS_DISABLE"] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("SOMATIC_HEADLESS_DISABLE", None)
        else:
            os.environ["SOMATIC_HEADLESS_DISABLE"] = previous
