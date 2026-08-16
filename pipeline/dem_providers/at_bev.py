"""Austria BEV Digitales Gelaendemodell (DGM), 10m, Lambert (EPSG:31287), CC-BY-4.0, via
data.gv.at - no auth. Higher resolution than Copernicus GLO-30 (30m), which matters for
switchback-heavy alpine trails a 30m grid can't resolve (see docs/osm-trail-pipeline.md's DEM
section). providerConfig: {"downloadUrl": "<direct link to the 10m GeoTIFF/zip resource>"} -
confirmed via the CKAN/DCAT metadata for data.gv.at dataset d88a1246-9684-480b-a480-ff63286b35b7
("Digitales Gelaendemodell (DGM) Oesterreich"), which lists
https://gis.ktn.gv.at/OGD/Geographie_Planung/ogd-10m-at.zip as the distribution's accessURL
(verified live: HTTP 200, ~1.9GB, application/x-zip-compressed). Downloaded and inspected by hand:
the zip is flat (no subfolders) and contains exactly one national-coverage GeoTIFF,
dhm_at_lamb_10m_2018.tif, plus its .tfw world file - not per-tile files. fetch()'s rglob("*.tif")
(rather than glob) is defensive against a future re-upload nesting things in a subfolder; today it
finds the same single flat file glob would.
"""

import subprocess
import urllib.request
import zipfile
from pathlib import Path


def download_url(provider_config: dict) -> str:
    return provider_config["downloadUrl"]


def fetch(provider_config: dict, raw_dir: Path) -> list[Path]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    url = download_url(provider_config)
    dst = raw_dir / Path(url).name

    if not dst.exists():
        print(f"downloading {url} ...")
        urllib.request.urlretrieve(url, dst)

    if dst.suffix == ".zip":
        extract_dir = raw_dir / dst.stem
        if not extract_dir.exists():
            with zipfile.ZipFile(dst) as zf:
                zf.extractall(extract_dir)
        return sorted(extract_dir.rglob("*.tif"))

    return [dst]


def to_4326_vrt(tile_paths: list[Path], out_vrt_path: Path) -> Path:
    # Source is EPSG:31287 (Lambert) - gdalwarp reprojects each tile into a temp VRT in EPSG:4326
    # before the final mosaic, so 08-add-elevation.py never has to know the source CRS.
    warped_dir = out_vrt_path.parent / "at_bev_warped"
    warped_dir.mkdir(exist_ok=True)
    warped_paths = []
    for tile in tile_paths:
        warped = warped_dir / f"{tile.stem}_4326.vrt"
        subprocess.run(
            ["gdalwarp", "-t_srs", "EPSG:4326", "-of", "VRT", "-overwrite",
             str(tile), str(warped)],
            check=True,
        )
        warped_paths.append(warped)

    # -input_file_list reads paths from a file instead of argv - avoids Windows' ~32KB
    # CreateProcess argv limit, which enough warped tile paths can blow past (see bavaria_dgm.py).
    file_list_path = warped_dir / "warped_files.txt"
    file_list_path.write_text("\n".join(str(p) for p in warped_paths), encoding="utf-8")
    subprocess.run(
        ["gdalbuildvrt", "-overwrite", "-input_file_list", str(file_list_path), str(out_vrt_path)],
        check=True,
    )
    return out_vrt_path
