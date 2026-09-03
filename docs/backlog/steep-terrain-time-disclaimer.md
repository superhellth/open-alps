# Frontend disclaimer for via_ferrata / high-SAC-grade legs

**Priority:** Low

Once `docs/superpowers/specs/2026-09-03-steep-terrain-time-model-design.md` lands, edges tagged
`via_ferrata` or `sac_rank >= 5` get a dedicated (still approximate) time model instead of the
walking-speed Tobler formula. Real walking speed on such terrain varies far more between people
than on a normal trail, so a tour leg touching this terrain should surface a "technically
difficult terrain — time estimate is approximate" warning in the frontend rather than presenting
the number with the same confidence as an ordinary hiking leg.

`sac_rank`/`via_ferrata` already flow through the edge payload
(`docs/tour-suggestion-payload.md`) — no pipeline or data-contract change needed, this is
frontend-only: `TourList.tsx`/`ResultsMap.tsx` (or wherever leg details render) gating a badge/note
on `leg.sac_rank >= 5 || leg.via_ferrata`.
