import { useEffect, useMemo, useState } from 'react'
import {
  Box, Button, Checkbox, CircularProgress, FormControlLabel, MenuItem, Select, TextField, Typography,
} from '@mui/material'
import type { SelectChangeEvent } from '@mui/material'
import { loadTourSearchData, findTours } from '../tourSearch/index.js'
import { SOURCE_TYPE_PARKING, SOURCE_TYPE_STATION } from '../tourSearch/types.js'
import type { GraphData, SearchResult, TourMode } from '../tourSearch/types.js'
import AppShell from '../AppShell.js'
import type { StartPoint } from './types.js'
import { DEFAULT_FORM, OVERLAP_THRESHOLD_BY_VARIETY, buildQuery, type FormState } from './formState.js'
import { PAGE_SIZE, SOURCE_TYPE_LABEL, haversineKm, idFromOsmFeatureId, toNumberOrDefault, SORT_COMPARATORS, type SortKey } from './helpers.js'
import LegCountSlider from './LegCountSlider.js'
import OverviewMap from './OverviewMap.js'
import ResultsPanel from './ResultsPanel.js'

const HUTS_URL = '/data/huts.geojson'
const PARKING_URL = '/data/parking.geojson'
const STATIONS_URL = '/data/stations.geojson'

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
