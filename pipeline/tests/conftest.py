import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import timing  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_timings(tmp_path, monkeypatch):
    """Keeps tests that run a script's `main()` from appending to the real data/timings.jsonl."""
    monkeypatch.setattr(timing, "TIMINGS_PATH", tmp_path / "timings.jsonl")
