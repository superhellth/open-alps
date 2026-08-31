# Hut catalog gaps — privately-run mountain inns

**Priority:** High

Tour stages legitimately overnight at Berggasthöfe that are neither Alpine Club huts
(`huts.geojson`) nor Bergsteigerdörfer partner businesses (`partner_betriebe.geojson`, only 110
features nationwide).

**Concrete case:** Kaisertour's leg 3→4 boundary is the **Weinbergerhaus**, a Berggasthof. Nearest
`huts.geojson` entry is Kaindlhütte at **2,101 m**; nearest partner business is 72 km away. So the
stop exists, is a real overnight hut, and is in neither catalog.

This is a **data-coverage problem, not an algorithmic one** — the fix is to get such places into a
hub layer, not to loosen snapping thresholds or invent per-tour endpoint types.

**Open question:** which layer they belong in — an extension of `partner_betriebe.geojson`, a new
`TYPE_*`, or a source other than the AV catalog entirely.
