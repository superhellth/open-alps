import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import timing  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_timings(tmp_path, monkeypatch):
    """Keeps tests that run a script's `main()` (in-process or via subprocess) from appending to the real data/timings.jsonl."""
    monkeypatch.setattr(timing, "TIMINGS_PATH", tmp_path / "timings.jsonl")
    monkeypatch.setenv("OPEN_ALPS_TIMINGS_PATH", str(tmp_path / "timings.jsonl"))
