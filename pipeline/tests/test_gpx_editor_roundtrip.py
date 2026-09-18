import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.tour_folder import parse_leg_gpx  # noqa: E402

_FIXTURES = Path(__file__).parent / "fixtures" / "gpx_edited"


def test_parse_leg_gpx_reads_editor_output():
    """edited.gpx is produced by huts/src/gpxEditor (gpxDoc.fixture.test.ts): point 1 moved,
    a point inserted after point 2, point 0 deleted. Proves the namespaced findall sees the
    editor's inserted <trkpt> (a null-namespace element would be silently skipped)."""
    assert parse_leg_gpx(_FIXTURES / "edited.gpx") == [
        (11.25, 47.25), (11.3, 47.3), (11.35, 47.35), (11.4, 47.4),
    ]
