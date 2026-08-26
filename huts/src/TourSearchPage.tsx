import { useEffect, useMemo, useState } from 'react'
import {
  Alert, Box, Button, Checkbox, CircularProgress, FormControlLabel, MenuItem, Select,
  Slider, TextField, Typography,
} from '@mui/material'
import type { SelectChangeEvent } from '@mui/material'
import { loadTourSearchData, findTours } from './tourSearch/index.js'
import { SOURCE_TYPE_PARKING, SOURCE_TYPE_STATION } from './tourSearch/types.js'
import type { GraphData, Query, SearchResult, TourMode } from './tourSearch/types.js'
import AppShell from './AppShell.js'

const HUTS_URL = '/data/huts.geojson'
const PARKING_URL = '/data/parking.geojson'
const STATIONS_URL = '/data/stations.geojson'

const SOURCE_TYPE_LABEL: Record<number, string> = {
  [SOURCE_TYPE_STATION]: 'Bahnhof',
  [SOURCE_TYPE_PARKING]: 'Parkplatz',
}

// legCountMax above this is flagged as potentially slow in the UI (spec D2: "guard the
// expensive end of the range" - no Worker, no cancel, so an unexpected blowup freezes the tab).
const LEG_COUNT_SLOW_WARNING_THRESHOLD = 8

interface FormState {
  mode: TourMode
  legCountRange: [number, number]
  sacCeiling: number | 'any'
  allowUngraded: boolean
  legTimeRange: [number, number]
  legAscentCapM: string
  maxEleM: string
  allowViaFerrata: boolean
  overlapVariety: 'wenig' | 'mittel' | 'viel'
}

const DEFAULT_FORM: FormState = {
  mode: 'car',
  legCountRange: [2, 4],
  sacCeiling: 3,
  allowUngraded: true,
  legTimeRange: [0, 8],
  legAscentCapM: '',
  maxEleM: '',
  allowViaFerrata: true,
  overlapVariety: 'mittel',
}

const OVERLAP_THRESHOLD_BY_VARIETY: Record<FormState['overlapVariety'], number> = {
  wenig: 0.3,
  mittel: 0.5,
  viel: 0.8,
}

export interface StartPoint {
  name: string | null
  sourceType: number
  lat: number
  lng: number
}

// OSM feature ids in parking.geojson/stations.geojson are prefixed ("n123") - approaches.startId
// is the bare numeric OSM node id, so this strips the prefix to join the two.
function idFromOsmFeatureId(featureId: string | number): number | null {
  const n = Number(String(featureId).replace(/^\D+/, ''))
  return Number.isFinite(n) ? n : null
}

function toNumberOrDefault(value: string, fallback: number): number {
  if (value === '') return fallback
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

function buildQuery(form: FormState): Query {
  return {
    mode: form.mode,
    legCountMin: form.legCountRange[0],
    legCountMax: form.legCountRange[1],
    sacCeiling: form.sacCeiling === 'any' ? null : form.sacCeiling,
    allowUngraded: form.allowUngraded,
    minLegTimeH: form.legTimeRange[0],
    maxLegTimeH: form.legTimeRange[1],
    legAscentCapM: toNumberOrDefault(form.legAscentCapM, Infinity),
    maxEleM: form.maxEleM === '' ? null : toNumberOrDefault(form.maxEleM, Infinity),
    allowViaFerrata: form.allowViaFerrata,
  }
}

function TourSearchPage() {
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [hutNameById, setHutNameById] = useState<Map<number, string>>(new Map())
  const [startById, setStartById] = useState<Map<number, StartPoint>>(new Map())
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState<FormState>(DEFAULT_FORM)
  const [result, setResult] = useState<SearchResult | null>(null)
  const [searching, setSearching] = useState(false)

  useEffect(() => {
    Promise.all([
      loadTourSearchData(),
      fetch(HUTS_URL).then((r) => r.json()) as Promise<GeoJSON.FeatureCollection>,
      fetch(PARKING_URL).then((r) => r.json()) as Promise<GeoJSON.FeatureCollection>,
      fetch(STATIONS_URL).then((r) => r.json()) as Promise<GeoJSON.FeatureCollection>,
    ])
      .then(([tourSearchData, hutsFc, parkingFc, stationsFc]) => {
        setGraphData(tourSearchData)
        setHutNameById(
          new Map(
            hutsFc.features.map((f) => [
              (f.properties as { id: number }).id,
              (f.properties as { name: string }).name,
            ]),
          ),
        )

        const starts = new Map<number, StartPoint>()
        for (const f of stationsFc.features) {
          const id = idFromOsmFeatureId(f.id as string | number)
          const [lng, lat] = (f.geometry as GeoJSON.Point).coordinates
          if (id != null) {
            starts.set(id, { name: (f.properties as { name?: string })?.name ?? null, sourceType: SOURCE_TYPE_STATION, lat, lng })
          }
        }
        for (const f of parkingFc.features) {
          const id = idFromOsmFeatureId(f.id as string | number)
          const [lng, lat] = (f.geometry as GeoJSON.Point).coordinates
          if (id != null) {
            starts.set(id, { name: (f.properties as { name?: string })?.name ?? null, sourceType: SOURCE_TYPE_PARKING, lat, lng })
          }
        }
        setStartById(starts)
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  const startLabel = useMemo(
    () => (startId: number) => {
      const start = startById.get(startId)
      if (!start) return `Startpunkt ${startId}`
      const kind = SOURCE_TYPE_LABEL[start.sourceType] ?? 'Startpunkt'
      return start.name ? `${start.name} (${kind})` : kind
    },
    [startById],
  )

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!graphData) return
    setSearching(true)
    setResult(null)
    // Defer the heavy synchronous findTours call a tick so React can paint the spinner first
    // (spec D: no Web Worker in this spec's scope).
    setTimeout(() => {
      const query = buildQuery(form)
      const overlapThreshold = OVERLAP_THRESHOLD_BY_VARIETY[form.overlapVariety]
      setResult(findTours(query, graphData, { overlapThreshold }))
      setSearching(false)
    }, 0)
  }

  function handleReset() {
    setForm(DEFAULT_FORM)
    setResult(null)
  }

  const legCountTooHigh = form.legCountRange[1] > LEG_COUNT_SLOW_WARNING_THRESHOLD

  return (
    <AppShell
      title="Tourensuche"
      status={error ? `Fehler: ${error}` : graphData ? 'Daten geladen' : 'Lade Daten…'}
    >
      <Box sx={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <Box
          component="form"
          onSubmit={handleSubmit}
          sx={{ display: 'flex', flexDirection: 'column', gap: 2, width: 320, flexShrink: 0, p: 2, overflowY: 'auto', borderRight: '1px solid #e0e0e0' }}
        >
          <Box>
            <Typography variant="subtitle2">Modus</Typography>
            <Select
              fullWidth
              size="small"
              value={form.mode}
              onChange={(e: SelectChangeEvent) => setForm((f) => ({ ...f, mode: e.target.value as TourMode }))}
            >
              <MenuItem value="car">Auto (Rundtour zum Ausgangspunkt)</MenuItem>
              <MenuItem value="transit">ÖPNV (offene Strecke)</MenuItem>
            </Select>
          </Box>

          <Box>
            <Typography variant="subtitle2">
              Etappen: {form.legCountRange[0]}–{form.legCountRange[1]}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {form.legCountRange[1]} Etappen = {form.legCountRange[1] - 1} Hütten ={' '}
              {form.legCountRange[1] - 1} Übernachtungen
            </Typography>
            <Slider
              value={form.legCountRange}
              onChange={(_e, value) => setForm((f) => ({ ...f, legCountRange: value as [number, number] }))}
              min={1}
              max={14}
              step={1}
              marks
              valueLabelDisplay="auto"
            />
            {legCountTooHigh && (
              <Alert severity="warning" sx={{ mt: 1 }}>
                Hohe Etappenzahl kann die Suche spürbar verlangsamen.
              </Alert>
            )}
          </Box>

          <Box>
            <Typography variant="subtitle2">Schwierigkeit (max. SAC-Skala)</Typography>
            <Select
              fullWidth
              size="small"
              value={form.sacCeiling}
              onChange={(e: SelectChangeEvent<number | 'any'>) =>
                setForm((f) => ({ ...f, sacCeiling: e.target.value === 'any' ? 'any' : Number(e.target.value) }))
              }
            >
              <MenuItem value={1}>T1 Wandern</MenuItem>
              <MenuItem value={2}>T2 Bergwandern</MenuItem>
              <MenuItem value={3}>T3 anspruchsvolles Bergwandern</MenuItem>
              <MenuItem value="any">beliebig</MenuItem>
            </Select>
          </Box>

          <FormControlLabel
            control={<Checkbox checked={form.allowUngraded} onChange={(e) => setForm((f) => ({ ...f, allowUngraded: e.target.checked }))} />}
            label="auch ungeratete Wege erlauben"
          />

          <Box>
            <Typography variant="subtitle2">Gehzeit pro Etappe (Stunden)</Typography>
            <Box sx={{ display: 'flex', gap: 1 }}>
              <TextField
                size="small"
                type="number"
                label="min"
                slotProps={{ htmlInput: { min: 0, step: 0.5 } }}
                value={form.legTimeRange[0]}
                onChange={(e) => setForm((f) => ({ ...f, legTimeRange: [Number(e.target.value), f.legTimeRange[1]] }))}
              />
              <TextField
                size="small"
                type="number"
                label="max"
                slotProps={{ htmlInput: { min: 0, step: 0.5 } }}
                value={form.legTimeRange[1]}
                onChange={(e) => setForm((f) => ({ ...f, legTimeRange: [f.legTimeRange[0], Number(e.target.value)] }))}
              />
            </Box>
          </Box>

          <TextField
            size="small"
            type="number"
            label="Anstiegslimit pro Etappe (m, leer = unbegrenzt)"
            slotProps={{ htmlInput: { min: 0 } }}
            value={form.legAscentCapM}
            onChange={(e) => setForm((f) => ({ ...f, legAscentCapM: e.target.value }))}
          />

          <TextField
            size="small"
            type="number"
            label="Maximalhöhe (m, leer = unbegrenzt)"
            value={form.maxEleM}
            onChange={(e) => setForm((f) => ({ ...f, maxEleM: e.target.value }))}
          />

          <FormControlLabel
            control={<Checkbox checked={form.allowViaFerrata} onChange={(e) => setForm((f) => ({ ...f, allowViaFerrata: e.target.checked }))} />}
            label="Klettersteige erlauben"
          />

          <Box>
            <Typography variant="subtitle2">Variantenvielfalt</Typography>
            <Select
              fullWidth
              size="small"
              value={form.overlapVariety}
              onChange={(e: SelectChangeEvent) => setForm((f) => ({ ...f, overlapVariety: e.target.value as FormState['overlapVariety'] }))}
            >
              <MenuItem value="wenig">wenig (ähnliche Touren zusammenfassen)</MenuItem>
              <MenuItem value="mittel">mittel</MenuItem>
              <MenuItem value="viel">viel (auch ähnliche Touren zeigen)</MenuItem>
            </Select>
          </Box>

          <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
            <Button type="submit" variant="contained" disabled={!graphData || searching} startIcon={searching ? <CircularProgress size={16} color="inherit" /> : undefined}>
              Touren suchen
            </Button>
            <Button type="button" variant="outlined" onClick={handleReset}>
              Zurücksetzen
            </Button>
          </Box>
        </Box>

        <Box sx={{ flex: 1, overflowY: 'auto', p: 2 }}>
          {result && <pre>{JSON.stringify(result, (k, v) => (typeof v === 'bigint' ? v.toString() : v), 2)}</pre>}
        </Box>
      </Box>
    </AppShell>
  )
}

export default TourSearchPage
