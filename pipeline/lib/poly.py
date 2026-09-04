"""Parses Osmosis ".poly" boundary-polygon files - the format Geofabrik publishes alongside every
regional .osm.pbf extract, describing the exact admin-boundary shape that extract was clipped to
(the same shape osmium/osmconvert consume for --polygon extraction). Used by fetch_huts.py to
filter the AV hut catalog to real AT+Bavaria coverage instead of a coarse bbox - see
docs/backlog/hut-catalog-bbox-includes-foreign-huts.md.

File shape (whitespace-delimited "lng lat" pairs, one ring per section):

    <set name>
    <ring name>
       <lng> <lat>
       ...
    END
    !<hole ring name>
       <lng> <lat>
       ...
    END
    END

A ring name starting with "!" is a hole, subtracted from the union of the outer rings."""

from shapely.geometry import Polygon
from shapely.ops import unary_union


def parse_poly_file(path):
    """Returns the (Multi)Polygon described by the .poly file at path."""
    with open(path, encoding="utf-8") as f:
        lines = iter(f.readlines())

    next(lines)  # set name, unused

    outer_rings = []
    hole_rings = []
    for ring_header in lines:
        ring_header = ring_header.strip()
        if ring_header == "END":
            break
        coords = []
        for line in lines:
            line = line.strip()
            if line == "END":
                break
            lng, lat = line.split()
            coords.append((float(lng), float(lat)))
        (hole_rings if ring_header.startswith("!") else outer_rings).append(Polygon(coords))

    polygon = unary_union(outer_rings)
    if hole_rings:
        polygon = polygon.difference(unary_union(hole_rings))
    return polygon


def region_boundary(poly_paths):
    """Unions the (Multi)Polygons parsed from poly_paths into one boundary covering every
    region."""
    return unary_union([parse_poly_file(p) for p in poly_paths])
