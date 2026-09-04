import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from lib.pipeline import safe_extractall  # noqa: E402


def _make_zip(path: Path, entries: dict) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)


def test_safe_extractall_extracts_well_formed_archive(tmp_path):
    zip_path = tmp_path / "good.zip"
    _make_zip(zip_path, {"a.txt": "hello", "sub/b.txt": "world"})
    extract_dir = tmp_path / "out"
    with zipfile.ZipFile(zip_path) as zf:
        safe_extractall(zf, extract_dir)
    assert (extract_dir / "a.txt").read_text() == "hello"
    assert (extract_dir / "sub" / "b.txt").read_text() == "world"


def test_safe_extractall_rejects_path_traversal(tmp_path):
    zip_path = tmp_path / "evil.zip"
    _make_zip(zip_path, {"../../evil.txt": "pwned"})
    extract_dir = tmp_path / "out"
    with zipfile.ZipFile(zip_path) as zf:
        with pytest.raises(ValueError):
            safe_extractall(zf, extract_dir)
    assert not (tmp_path.parent.parent / "evil.txt").exists()


def test_safe_extractall_rejects_absolute_path(tmp_path):
    zip_path = tmp_path / "evil_abs.zip"
    # zipfile normally strips a leading "/" on extractall, but ZipInfo can still carry one -
    # writestr with an absolute-looking name to exercise the check regardless of that stripping.
    _make_zip(zip_path, {"/etc/evil.txt": "pwned"})
    extract_dir = tmp_path / "out"
    with zipfile.ZipFile(zip_path) as zf:
        with pytest.raises(ValueError):
            safe_extractall(zf, extract_dir)
