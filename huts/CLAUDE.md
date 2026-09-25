# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Run from `huts/`:

- `npm run dev` — Vite dev server (also serves `/gpx-editor.html`, see `docs/gpx-editor.md` at repo root)
- `npm run build` — production build
- `npm run typecheck` — `tsc --noEmit`
- `npm run lint` — `oxlint` (config: `.oxlintrc.json`)
- `npm test` — `vitest run`, covers `src/**/*.test.{ts,tsx}` and `tools/**/*.test.ts`
- Single test file: `npx vitest run src/path/to/File.test.tsx`
- Single test by name: `npx vitest run src/path/to/File.test.tsx -t "test name"`

Tests run in a `node` environment (jsdom is not the default — see `vitest.config.js`), using
`@testing-library/react` for component tests.

## Architecture

The overall app structure, data sources, and the client-side tour search engine
(`src/tourSearch/`, `src/search/`, `src/trip/`) are documented in the repository root
`CLAUDE.md` — read that first. This file covers only what's specific to working inside `huts/`.

Imports that leave a top-level `src/` directory use the `@/` alias (`@/data/buildAppData.js`).

`tools/` holds standalone Node scripts (e.g. `gpxEditorPlugin.ts`, the Vite plugin backing the
dev-only GPX editor) that are outside `src/` because they run at build/dev-server time, not in
the browser bundle.

`public/data/` holds the pipeline's generated outputs (pmtiles, geojson, binary payloads) that
`src/adminPage/` and `src/tourSearch/` fetch at runtime — these are copied in by the pipeline's
`copy_public_data` doit task, not committed as source; do not hand-edit them.
