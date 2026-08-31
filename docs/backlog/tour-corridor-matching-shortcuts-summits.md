# Corridor matching shortcuts summit-visiting legs

**Priority:** Medium

`match_tour_edges.py`'s `match_leg` (`pipeline/phases/graph_building/match_tour_edges.py:72`)
routes each leg as a single shortest-path Dijkstra between its two endpoint hubs, inside a corridor
subgraph that's just a padded bbox around the whole GPX trace (`corridor_bounds`). The corridor
constrains which *edges* are eligible but never forces the matched path through any of the trace's
own intermediate points — so a leg whose official route deliberately detours over a summit gets
shortcut whenever a lower/flatter path exists between the same two hubs inside that bbox.

**Concrete case:** Kaisertour leg 1's GPX trace climbs from 682 m to a summit at 1589 m (80% of the
way through the trace), then only descends partway to 1386 m at the endpoint hub — the official
route goes over a peak on the way to the next hut, not straight there. The matched route came back
with a 0.63 length ratio (37% shorter than the trace) and a 1237 m max deviation, both centered
around the summit — measured by `pipeline/analysis/corridor_match_quality.py`.

**Root cause:** endpoint-only shortest-pathing has no way to represent "pass through this
waypoint," only "start here, end there, stay near this bbox." This is a structural limit of the
current matching approach, not a corridor-buffer tuning issue.

**Candidate fix:** HMM-style map matching (Newson & Krumm) — snap each trace point (or a decimated
subset) to candidate edges and Viterbi-decode the maximum-likelihood edge sequence, instead of one
`get_shortest_paths` call between endpoints. The existing corridor bbox is still useful as the
candidate-edge prefilter. Real complexity to add: emission probabilities (trace-point-to-edge
distance), transition probabilities (path-length vs. great-circle-distance ratio between
consecutive matched points), and handling for trace segments that briefly leave the graph (a via
ferrata missing from OSM, GPS noise near a peak) without spurious match breaks.

This is a real design change to `match_tour_edges.py`, not a quick patch — worth its own spec under
`docs/superpowers/specs/` before implementation.
