import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from elevation import sample_base_elevation as sbe  # noqa: E402


def test_bilinear_sampling_interpolates_between_cells():
    from affine import Affine
    window = np.array([[0.0, 10.0], [20.0, 30.0]], dtype=np.float32)
    transform = Affine(1.0, 0.0, 0.0, 0.0, -1.0, 0.0)
    got = sbe.sample_bilinear(window, transform, np.array([1.0]), np.array([-1.0]))
    assert got[0] == pytest.approx(15.0)
