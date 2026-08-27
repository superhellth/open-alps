import { memo, useEffect, useMemo, useState } from 'react'
import {
  Alert, Box, Button, Card, CardActionArea, CardContent, Checkbox, CircularProgress,
  FormControlLabel, MenuItem, Pagination, Select, Slider, Table, TableBody, TableCell,
  TableHead, TableRow, TextField, Typography,
} from '@mui/material'
import type { SelectChangeEvent } from '@mui/material'
import { MapContainer, TileLayer, CircleMarker, Polyline, Tooltip } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { loadTourSearchData, findTours } from './tourSearch/index.js'
import { SOURCE_TYPE_PARKING, SOURCE_TYPE_STATION } from './tourSearch/types.js'
import type { GraphData, Query, SearchResult, TourMode, TourResult } from './tourSearch/types.js'
import AppShell from './AppShell.js'

const HUTS_URL = '/data/huts.geojson'
const PARKING_URL = '/data/parking.geojson'
const STATIONS_URL = '/data/stations.geojson'

const SOURCE_TYPE_LABEL: Record<number, string> = {
  [SOURCE_TYPE_STATION]: 'Bahnhof',
  [SOURCE_TYPE_PARKING]: 'Parkplatz',
}

const PAGE_SIZE = 25

type SortKey = 'duration' | 'ascent' | 'distance' | 'legCount'

const SORT_COMPARATORS: Record<SortKey, (a: TourResult, b: TourResult) => number> = {
  duration: (a, b) => a.totalDurationH - b.totalDurationH,
  ascent: (a, b) => a.totalAscentM - b.totalAscentM,
  distance: (a, b) => a.totalDistanceM - b.totalDistanceM,
  legCount: (a, b) => a.huts.length - b.huts.length,
}

const SORT_LABEL: Record<SortKey, string> = {
  duration: 'Gesamtdauer',
  ascent: 'Anstieg',
  distance: 'Distanz',
  legCount: 'Etappenzahl',
}

// Translates raw kill-counter keys into actionable German guidance (spec D1: killCounters must
// not be rendered raw). Shown only in the empty-results state.
const KILL_COUNTER_GUIDANCE: Record<string, (n: number) => string> = {
  maxLegTime: (n) => `${n} Etappen waren zu lang — maximale Gehzeit erhöhen`,
  minLegTime: (n) => `${n} Etappen waren zu kurz — minimale Gehzeit senken`,
  legAscentCap: (n) => `${n} Etappen hatten zu viel Anstieg — Anstiegslimit erhöhen`,
  maxEleM: (n) => `${n} Etappen lagen über der Maximalhöhe — Maximalhöhe erhöhen`,
  viaFerrata: (n) => `${n} Etappen enthielten Klettersteige — "Klettersteige erlauben" aktivieren`,
  revisit: () => '', // internal search bookkeeping, not user-actionable
}

function killCounterGuidance(killCounters: SearchResult['killCounters']): string[] {
  return Object.entries(killCounters)
    .filter(([key, n]) => n > 0 && KILL_COUNTER_GUIDANCE[key]?.(n))
    .map(([key, n]) => KILL_COUNTER_GUIDANCE[key](n))
}

// Zips chain.legs (engine-side, name-agnostic) against the point sequence [start, ...huts, exit]
// to produce one "from → to" label per leg, without the engine ever knowing about hut/start names.
function legWaypointLabels(
  chain: TourResult,
  startLabel: (startId: number) => string,
  hutNameById: Map<number, string>,
): string[] {
  const pointLabels = [
    startLabel(chain.startId),
    ...chain.huts.map((h) => hutNameById.get(h) ?? String(h)),
    startLabel(chain.exitStartId),
  ]
  const labels: string[] = []
  for (let i = 0; i < pointLabels.length - 1; i++) labels.push(`${pointLabels[i]} → ${pointLabels[i + 1]}`)
  return labels
}

function haversineKm(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
  const R = 6371
  const dLat = ((b.lat - a.lat) * Math.PI) / 180
  const dLng = ((b.lng - a.lng) * Math.PI) / 180
  const sinLat = Math.sin(dLat / 2)
  const sinLng = Math.sin(dLng / 2)
  const h = sinLat * sinLat + Math.cos((a.lat * Math.PI) / 180) * Math.cos((b.lat * Math.PI) / 180) * sinLng * sinLng
  return 2 * R * Math.asin(Math.sqrt(h))
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

function SelectedTourMap({
  chain, hutCoordsById, startById,
}: {
  chain: TourResult
  hutCoordsById: Map<number, { lat: number; lng: number }>
  startById: Map<number, StartPoint>
}) {
  const startPoint = startById.get(chain.startId)
  const endPoint = startById.get(chain.exitStartId)
  const hutPoints = chain.huts.map((h) => hutCoordsById.get(h)).filter((p): p is { lat: number; lng: number } => !!p)
  const positions: [number, number][] = [
    ...(startPoint ? [[startPoint.lat, startPoint.lng] as [number, number]] : []),
    ...hutPoints.map((p): [number, number] => [p.lat, p.lng]),
    ...(endPoint ? [[endPoint.lat, endPoint.lng] as [number, number]] : []),
  ]
  if (positions.length < 2) return null

  const center = positions[Math.floor(positions.length / 2)]

  return (
    <Box>
      <MapContainer center={center} zoom={11} style={{ height: 260, width: '100%' }}>
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        />
        <Polyline positions={positions} pathOptions={{ color: '#e65100', weight: 3, dashArray: '6 8' }} />
        {startPoint && (
          <CircleMarker center={[startPoint.lat, startPoint.lng]} radius={6} pathOptions={{ color: '#1b5e20', fillColor: '#43a047', fillOpacity: 1 }} />
        )}
        {endPoint && (
          <CircleMarker center={[endPoint.lat, endPoint.lng]} radius={6} pathOptions={{ color: '#1b5e20', fillColor: '#43a047', fillOpacity: 1 }} />
        )}
      </MapContainer>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
        Schematische Verbindung, nicht der reale Wegverlauf.
      </Typography>
    </Box>
  )
}

// Memoized because the ~1200 hut CircleMarker/Tooltip elements are otherwise reconciled on
// every keystroke/slider-drag in the sibling form (hutNameById/hutCoordsById never change after
// the initial load, so this never actually needs to re-render).
const OverviewMap = memo(function OverviewMap({
  hutNameById, hutCoordsById,
}: {
  hutNameById: Map<number, string>
  hutCoordsById: Map<number, { lat: number; lng: number }>
}) {
  return (
    <MapContainer center={[47.3, 12.0]} zoom={7} style={{ flex: 1, height: '100%', width: '100%' }}>
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> | Hüttendaten: Alpenverein / ArcGIS'
      />
      {[...hutCoordsById.entries()].map(([id, { lat, lng }]) => (
        <CircleMarker
          key={id}
          center={[lat, lng]}
          radius={4}
          pathOptions={{ color: '#1b5e20', fillColor: '#43a047', fillOpacity: 0.9, weight: 1 }}
        >
          <Tooltip direction="top" offset={[0, -6]}>
            {hutNameById.get(id) ?? id}
          </Tooltip>
        </CircleMarker>
      ))}
    </MapContainer>
  )
})

// Memoized so the (up to PAGE_SIZE) result cards, tables and expanded-tour map are only
// reconciled when the search results/sort/paging actually change — not on every keystroke in the
// sibling filter form (every prop here is either a primitive, a setState function — stable by
// React's guarantee — or a value already memoized upstream, so an unrelated form-field edit
// leaves every prop reference-equal and this whole subtree bails out).
const ResultsPanel = memo(function ResultsPanel({
  result, displayedChains, pageChains, page, pageCount, setPage,
  sortKey, setSortKey, regionCenterId, setRegionCenterId, regionMenuItems,
  regionRadiusKm, setRegionRadiusKm, hutNameById, hutCoordsById, startById, startLabel,
}: {
  result: SearchResult
  displayedChains: TourResult[]
  pageChains: TourResult[]
  page: number
  pageCount: number
  setPage: (p: number) => void
  sortKey: SortKey
  setSortKey: (k: SortKey) => void
  regionCenterId: number | 'all'
  setRegionCenterId: (id: number | 'all') => void
  regionMenuItems: React.ReactNode
  regionRadiusKm: string
  setRegionRadiusKm: (v: string) => void
  hutNameById: Map<number, string>
  hutCoordsById: Map<number, { lat: number; lng: number }>
  startById: Map<number, StartPoint>
  startLabel: (startId: number) => string
}) {
  const [expandedChain, setExpandedChain] = useState<number | null>(null)

  return (
    <>
      <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center' }}>
        <Typography color="text.secondary">
          {displayedChains.length} Tour{displayedChains.length === 1 ? '' : 'en'} gefunden
        </Typography>
        <Select size="small" value={sortKey} onChange={(e: SelectChangeEvent) => setSortKey(e.target.value as SortKey)}>
          {(Object.keys(SORT_LABEL) as SortKey[]).map((key) => (
            <MenuItem key={key} value={key}>
              Sortieren: {SORT_LABEL[key]}
            </MenuItem>
          ))}
        </Select>
        <Select
          size="small"
          value={String(regionCenterId)}
          onChange={(e: SelectChangeEvent) => setRegionCenterId(e.target.value === 'all' ? 'all' : Number(e.target.value))}
        >
          <MenuItem value="all">Alle Regionen</MenuItem>
          {regionMenuItems}
        </Select>
        {regionCenterId !== 'all' && (
          <TextField
            size="small"
            type="number"
            label="Radius (km)"
            value={regionRadiusKm}
            onChange={(e) => setRegionRadiusKm(e.target.value)}
            sx={{ width: 120 }}
          />
        )}
      </Box>

      {displayedChains.length === 0 && (
        <Box>
          <Typography>Keine Touren gefunden. Filter lockern und erneut versuchen.</Typography>
          {killCounterGuidance(result.killCounters).map((msg, i) => (
            <Alert key={i} severity="info" sx={{ mt: 1 }}>
              {msg}
            </Alert>
          ))}
        </Box>
      )}

      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {pageChains.map((chain, i) => {
          const chainIndex = (page - 1) * PAGE_SIZE + i
          const isExpanded = expandedChain === chainIndex
          return (
            <Card key={chainIndex} variant="outlined">
              <CardActionArea onClick={() => setExpandedChain(isExpanded ? null : chainIndex)}>
                <CardContent>
                  <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                    {startLabel(chain.startId)} → … → {startLabel(chain.exitStartId)}
                  </Typography>
                  <Typography color="text.secondary" variant="body2">
                    {chain.totalDurationH.toFixed(1)} h · ↑{Math.round(chain.totalAscentM)}m ↓
                    {Math.round(chain.totalDescentM)}m · {(chain.totalDistanceM / 1000).toFixed(1)} km ·{' '}
                    {chain.huts.length} Etappen
                  </Typography>
                </CardContent>
              </CardActionArea>
              {isExpanded && (
                <CardContent sx={{ pt: 0 }}>
                  <Typography variant="body2" sx={{ mb: 1 }}>
                    {startLabel(chain.startId)}
                    {chain.huts.map((h) => ` → ${hutNameById.get(h) ?? h}`).join('')}
                    {' → '}
                    {startLabel(chain.exitStartId)}
                  </Typography>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Etappe</TableCell>
                        <TableCell align="right">Dauer</TableCell>
                        <TableCell align="right">↑</TableCell>
                        <TableCell align="right">↓</TableCell>
                        <TableCell align="right">Distanz</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {legWaypointLabels(chain, startLabel, hutNameById).map((label, legIndex) => {
                        const leg = chain.legs[legIndex]
                        return (
                          <TableRow key={legIndex}>
                            <TableCell>{label}</TableCell>
                            <TableCell align="right">{leg.durationH.toFixed(1)} h</TableCell>
                            <TableCell align="right">{Math.round(leg.ascentM)}m</TableCell>
                            <TableCell align="right">{Math.round(leg.descentM)}m</TableCell>
                            <TableCell align="right">{(leg.distanceM / 1000).toFixed(1)} km</TableCell>
                          </TableRow>
                        )
                      })}
                    </TableBody>
                  </Table>
                  <Box sx={{ mt: 1 }}>
                    <SelectedTourMap chain={chain} hutCoordsById={hutCoordsById} startById={startById} />
                  </Box>
                </CardContent>
              )}
            </Card>
          )
        })}
      </Box>

      {pageCount > 1 && (
        <Pagination count={pageCount} page={page} onChange={(_e, p) => setPage(p)} sx={{ alignSelf: 'center' }} />
      )}
    </>
  )
})

// Owns its own drag-in-progress value so the Slider's continuous onChange events (fired on every
// pointer move) only re-render this small subtree, not the whole page's form + result panes —
// the parent form state is only touched once, via onChangeCommitted, on release.
function LegCountSlider({
  value, onCommit,
}: {
  value: [number, number]
  onCommit: (v: [number, number]) => void
}) {
  const [draft, setDraft] = useState(value)
  useEffect(() => setDraft(value), [value])
  const tooHigh = draft[1] > LEG_COUNT_SLOW_WARNING_THRESHOLD

  return (
    <Box>
      <Typography variant="subtitle2">
        Etappen: {draft[0]}–{draft[1]}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {draft[1]} Etappen = {draft[1] - 1} Hütten = {draft[1] - 1} Übernachtungen
      </Typography>
      <Slider
        value={draft}
        onChange={(_e, v) => setDraft(v as [number, number])}
        onChangeCommitted={(_e, v) => onCommit(v as [number, number])}
        min={1}
        max={14}
        step={1}
        marks
        valueLabelDisplay="auto"
      />
      {tooHigh && (
        <Alert severity="warning" sx={{ mt: 1 }}>
          Hohe Etappenzahl kann die Suche spürbar verlangsamen.
        </Alert>
      )}
    </Box>
  )
}

function TourSearchPage() {
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [hutNameById, setHutNameById] = useState<Map<number, string>>(new Map())
  const [hutCoordsById, setHutCoordsById] = useState<Map<number, { lat: number; lng: number }>>(new Map())
  const [startById, setStartById] = useState<Map<number, StartPoint>>(new Map())
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState<FormState>(DEFAULT_FORM)
  const [result, setResult] = useState<SearchResult | null>(null)
  const [searching, setSearching] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('duration')
  const [page, setPage] = useState(1)
  const [regionCenterId, setRegionCenterId] = useState<number | 'all'>('all')
  const [regionRadiusKm, setRegionRadiusKm] = useState('50')

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
        setHutCoordsById(
          new Map(
            hutsFc.features.map((f) => {
              const [lng, lat] = (f.geometry as GeoJSON.Point).coordinates
              return [(f.properties as { id: number }).id, { lat, lng }]
            }),
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

  // startById can hold ~30k station+parking points — building this MenuItem list is only cheap
  // once, not on every keystroke in the sibling form (which is what a plain inline .map() here
  // would do, since it reruns on every TourSearchPage render).
  const regionMenuItems = useMemo(
    () =>
      [...startById.entries()].map(([id, start]) => (
        <MenuItem key={id} value={id}>
          Nahe: {start.name ?? SOURCE_TYPE_LABEL[start.sourceType]}
        </MenuItem>
      )),
    [startById],
  )

  const displayedChains = useMemo(() => {
    if (!result) return []
    let chains = [...result.chains]
    if (regionCenterId !== 'all') {
      const center = startById.get(regionCenterId)
      const radiusKm = toNumberOrDefault(regionRadiusKm, Infinity)
      if (center) {
        chains = chains.filter((c) => {
          const start = startById.get(c.startId)
          const end = startById.get(c.exitStartId)
          return (
            (start && haversineKm(center, start) <= radiusKm) ||
            (end && haversineKm(center, end) <= radiusKm)
          )
        })
      }
    }
    chains.sort(SORT_COMPARATORS[sortKey])
    return chains
  }, [result, sortKey, regionCenterId, regionRadiusKm, startById])

  const pageCount = Math.max(1, Math.ceil(displayedChains.length / PAGE_SIZE))
  const pageChains = useMemo(
    () => displayedChains.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [displayedChains, page],
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
      setPage(1)
      setSearching(false)
    }, 0)
  }

  function handleReset() {
    setForm(DEFAULT_FORM)
    setResult(null)
  }

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

          <LegCountSlider
            value={form.legCountRange}
            onCommit={(legCountRange) => setForm((f) => ({ ...f, legCountRange }))}
          />

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

        <Box
          sx={
            result
              ? { flex: 1, overflowY: 'auto', p: 2, display: 'flex', flexDirection: 'column', gap: 2 }
              : { flex: 1, display: 'flex' }
          }
        >
          {!result && <OverviewMap hutNameById={hutNameById} hutCoordsById={hutCoordsById} />}
          {result && (
            <ResultsPanel
              result={result}
              displayedChains={displayedChains}
              pageChains={pageChains}
              page={page}
              pageCount={pageCount}
              setPage={setPage}
              sortKey={sortKey}
              setSortKey={setSortKey}
              regionCenterId={regionCenterId}
              setRegionCenterId={setRegionCenterId}
              regionMenuItems={regionMenuItems}
              regionRadiusKm={regionRadiusKm}
              setRegionRadiusKm={setRegionRadiusKm}
              hutNameById={hutNameById}
              hutCoordsById={hutCoordsById}
              startById={startById}
              startLabel={startLabel}
            />
          )}
        </Box>
      </Box>
    </AppShell>
  )
}

export default TourSearchPage
