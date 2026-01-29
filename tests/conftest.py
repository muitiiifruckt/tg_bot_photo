import importlib
import os
import sys
from pathlib import Path

import pytest


# Ensure project root is importable (so `import tg_bot` works)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def tmp_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Provide isolated DATABASE_PATH/FEEDBACK_PATH for tests.

    IMPORTANT: tg_bot.core.config reads env vars at import time, so tests must
    set env BEFORE importing modules that depend on it.
    """
    db_path = tmp_path / "bot_database.db"
    feedback_path = tmp_path / "feedback.jsonl"

    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("FEEDBACK_PATH", str(feedback_path))

    # Ensure repo-root old db doesn't interfere with migration code.
    monkeypatch.chdir(tmp_path)

    return {"db_path": db_path, "feedback_path": feedback_path}


@pytest.fixture
def reload_module():
    def _reload(module_name: str):
        if module_name in sys.modules:
            return importlib.reload(sys.modules[module_name])
        return importlib.import_module(module_name)

    return _reload


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "y", "on"}


def pytest_collection_modifyitems(config, items):
    """
    Skip integration/expensive tests unless explicitly enabled via env vars.

    - RUN_INTEGRATION=1 enables @pytest.mark.integration
    - RUN_EXPENSIVE=1 enables @pytest.mark.expensive (implies integration)
    """
    run_integration = _env_truthy("RUN_INTEGRATION") or _env_truthy("RUN_EXPENSIVE")
    run_expensive = _env_truthy("RUN_EXPENSIVE")

    for item in items:
        if "integration" in item.keywords and not run_integration:
            item.add_marker(pytest.mark.skip(reason="Set RUN_INTEGRATION=1 to run real API tests"))
        if "expensive" in item.keywords and not run_expensive:
            item.add_marker(pytest.mark.skip(reason="Set RUN_EXPENSIVE=1 to run expensive real API tests"))

