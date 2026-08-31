import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.pipeline import TOURS_DIR  # noqa: E402


def test_tours_dir_is_pipeline_tours():
    assert TOURS_DIR.name == "tours"
    assert TOURS_DIR.parent.name == "pipeline"
    assert (TOURS_DIR / "Kaisertour").is_dir()
