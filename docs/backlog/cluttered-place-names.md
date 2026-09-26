# Cluttered place names in huts, stations and parking

**Priority:** Low

Names that reach the client come straight from the sources and are often not usable as labels.
Everything in the UI that shows a place name (trip names, start labels, stage list, map tooltips)
inherits the clutter. Per the root-layer rule, the fix belongs in the pipeline, not in client-side
string trimming.

Measured on `huts/public/data/*.geojson`:

- **Parking** (`parking.geojson`, 237 969 features, 16 969 named, median 16 chars): some names are
  whole signs, e.g. `Parkplatz Gemeindeamt - beschränktes Parkverbot von 00.00 bis 06.00 Uhr im
  Zeitraum der allgemeinen Winterreifenpflicht - Keine Dauerparker!` or `Parkplatz Kirchengasse,
  öffentlich, gebührenfrei, Kurzparkzone. …`.
- **Stations** (`stations.geojson`, 130 781 features, median 19 chars): merged or duplicated
  variants joined with `,` or `;`, e.g. `Bieberbach (b. Sonnefeld) Aussiedlerhöfe,Bieberbach
  (Sonnefd)`, `Bad Mühllacken Abzw. Wolfsbach (B132);Bad Mühllacken Abzw. Wolfsbach`, and long
  street-crossing names like `Kemnath, Werner-von-Siemens-Straße/Josef-von-Eichendorff-Straße`.
- **Huts** (`huts.geojson`, 626 named, median 15 chars, max 47): alternate names in parentheses,
  e.g. `Landshuter-Europa-Hütte (Rif. Venna alla Gerla)`, `Gamskarkogel-Hütte (Badgasteiner
  Hütte)`, and descriptive suffixes like `Wittgruber-Hof, Jugend- und Familienstützpunkt`.

## Direction

Emit a clean display name next to (or instead of) the raw one:

- Parking: drop names that are notices rather than names (length, sentence punctuation, keywords
  like `Parkverbot`, `gebührenfrei`), fall back to the unnamed label.
- Stations: split `;`-joined OSM values and keep one; dedupe near-identical variants.
- Huts: keep the primary name, move a parenthesised alternate into a separate field so the
  client can still show it where there is room.

## Pointers

- `pipeline/phases/downloads/fetch_stations_parking.py`: builds `stations.geojson`/`parking.geojson`
  from OSM `name`.
- `pipeline/phases/downloads/fetch_huts.py`: builds `huts.geojson` from the ArcGIS `name` field.
- `huts/src/data/labels.ts` (`makeStartLabel`): the client's start label, which adds a
  `(Parkplatz)`-style kind suffix.
