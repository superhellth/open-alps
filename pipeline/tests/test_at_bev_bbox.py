import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from downloads.dem_providers import at_bev  # noqa: E402


def test_download_url_uses_configured_url():
    config = {"downloadUrl": "https://example.data.gv.at/dgm10.zip"}
    assert at_bev.download_url(config) == "https://example.data.gv.at/dgm10.zip"


def test_download_url_missing_key_raises():
    try:
        at_bev.download_url({})
        assert False, "expected KeyError"
    except KeyError:
        pass
