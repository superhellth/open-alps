# GPX editor (dev only)

Browser tool to inspect tour legs against the pipeline's hubs and repair GPX tracks. Spec:
`docs/superpowers/specs/2026-09-18-gpx-editor-design.md`.

## Run

1. Build the hub set once (and after any hub change): from `pipeline/`, `pixi run doit match_tour_edges`.
   This writes `data/build/tour-edges/hubs.json`. Without it the editor still edits, but the snap overlay is disabled.
2. `cd huts && npm run dev`, open `http://localhost:5173/gpx-editor.html`.
3. Pick a leg. Green ring = endpoint snaps, red = unsnapped (dashed line shows the nearest hub and its distance).
4. Drag handles to move points, click the line to insert a point, right-click a handle (or select it and press
   `Del`) to delete, `Ctrl+Z` / `Ctrl+Shift+Z` undo/redo, "Snap start/end to hub" fixes a red endpoint,
   `Ctrl+S` saves to `pipeline/tours/<Tour>/<N>.gpx`.
5. After saving, re-run `doit` as usual. Git is the undo for saved files: the tool makes no backups.

The editor is dev-only: `vite build` builds only `index.html`.
