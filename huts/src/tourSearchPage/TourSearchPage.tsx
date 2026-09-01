import { useEffect, useMemo, useState } from 'react'
import {
  Accordion, AccordionDetails, AccordionSummary, Box, Button, Checkbox, CircularProgress, FormControlLabel, MenuItem, Select, TextField, Typography,
} from '@mui/material'
import type { SelectChangeEvent } from '@mui/material'
import { loadTourSearchData, findTours } from '../tourSearch/index.js'
import { SOURCE_TYPE_PARKING, SOURCE_TYPE_PARTNER, SOURCE_TYPE_STATION } from '../tourSearch/types.js'
import type { GraphData, SearchResult, TourMode } from '../tourSearch/types.js'
import { fetchAvailabilityByOffset } from '../availability/fetchAvailability.js'
import type { FreeByOffset } from '../availability/types.js'
import AppShell from '../AppShell.js'
import type { StartPoint } from './types.js'
import type { HutClass, HutOperator } from '../hutClass.js'
import { OPERATOR_LABEL } from '../hutClass.js'
import { DEFAULT_FORM, buildQuery, isFilterSelectionValid, type FormState } from './formState.js'
import { PAGE_SIZE, SOURCE_TYPE_LABEL, idFromOsmFeatureId, SORT_COMPARATORS, type SortKey } from './helpers.js'
import LegCountSlider from './LegCountSlider.js'
import LegTimeSlider from './LegTimeSlider.js'
import ResultsMap from './ResultsMap.js'
import TourList from './TourList.js'

const HUTS_URL = '/data/huts.geojson'
const PARKING_URL = '/data/parking.geojson'
const STATIONS_URL = '/data/stations.geojson'
const PARTNER_URL = '/data/partner_betriebe.geojson'

function TourSearchPage() {
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [hutNameById, setHutNameById] = useState<Map<number, string>>(new Map())
  const [hutCoordsById, setHutCoordsById] = useState<Map<number, { lat: number; lng: number }>>(new Map())
  const [startById, setStartById] = useState<Map<number, StartPoint>>(new Map())
  const [hutsByIndex, setHutsByIndex] = useState<(HutClass | null)[]>([])
  const [hutOhrsByIndex, setHutOhrsByIndex] = useState<Map<number, { ohrsHutId: string | null; tenantCode: number | null }>>(new Map())
  const [freeByOffset, setFreeByOffset] = useState<FreeByOffset | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState<FormState>(DEFAULT_FORM)
  const [result, setResult] = useState<SearchResult | null>(null)
  const [searching, setSearching] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('duration')
  const [page, setPage] = useState(1)
  const [expandedChain, setExpandedChain] = useState<number | null>(null)

  useEffect(() => {
    Promise.all([
      loadTourSearchData(),
      fetch(HUTS_URL).then((r) => r.json()) as Promise<GeoJSON.FeatureCollection>,
      fetch(PARKING_URL).then((r) => r.json()) as Promise<GeoJSON.FeatureCollection>,
      fetch(STATIONS_URL).then((r) => r.json()) as Promise<GeoJSON.FeatureCollection>,
      fetch(PARTNER_URL)
        .then((r) => r.json() as Promise<GeoJSON.FeatureCollection>)
        .catch(() => ({ type: 'FeatureCollection', features: [] }) as GeoJSON.FeatureCollection),
    ])
      .then(([tourSearchData, hutsFc, parkingFc, stationsFc, partnerFc]) => {
        setGraphData(tourSearchData)

        const hutFeatureByGuid = new Map(
          hutsFc.features.map((f) => [(f.properties as { id: string }).id, f]),
        )
        const hutsByIdx = tourSearchData.hutEdges.hutIds.map((guid) => hutFeatureByGuid.get(guid) ?? null)

        setHutNameById(
          new Map(
            hutsByIdx
              .map((f, i) => (f ? ([i, (f.properties as { name: string }).name] as const) : null))
              .filter((entry): entry is readonly [number, string] => entry != null),
          ),
        )
        setHutCoordsById(
          new Map(
            hutsByIdx
              .map((f, i) => {
                if (!f) return null
                const [lng, lat] = (f.geometry as GeoJSON.Point).coordinates
                return [i, { lat, lng }] as const
              })
              .filter((entry): entry is readonly [number, { lat: number; lng: number }] => entry != null),
          ),
        )
        setHutsByIndex(
          hutsByIdx.map((f) => {
            if (!f) return null
            const props = f.properties as { hutType?: string; serviced?: boolean }
            if (props.hutType !== 'av' && props.hutType !== 'sonstige') return null
            return { operator: props.hutType, serviced: props.serviced ?? true }
          }),
        )
        setHutOhrsByIndex(
          new Map(
            hutsByIdx
              .map((f, i) => {
                if (!f) return null
                const props = f.properties as { ohrsHutId?: string | null; tenantCode?: number | null }
                return [i, { ohrsHutId: props.ohrsHutId ?? null, tenantCode: props.tenantCode ?? null }] as const
              })
              .filter((entry): entry is readonly [number, { ohrsHutId: string | null; tenantCode: number | null }] => entry != null),
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
        // Partner points carry no top-level f.id (ArcGIS OBJECTID lives in properties.id) - do NOT
        // use idFromOsmFeatureId here, it would reduce Number("") to 0 and collapse every point.
        for (const f of partnerFc.features) {
          const id = (f.properties as { id?: number })?.id
          const [lng, lat] = (f.geometry as GeoJSON.Point).coordinates
          if (id != null) {
            starts.set(id, { name: (f.properties as { name?: string })?.name ?? null, sourceType: SOURCE_TYPE_PARTNER, lat, lng })
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
      if (!start.name) return kind
      return start.sourceType === SOURCE_TYPE_STATION ? start.name : `${start.name} (${kind})`
    },
    [startById],
  )

  const displayedChains = useMemo(() => {
    if (!result) return []
    const chains = [...result.chains]
    chains.sort(SORT_COMPARATORS[sortKey])
    return chains
  }, [result, sortKey])

  const ohrsIdByHutIndex = useMemo(
    () => new Map([...hutOhrsByIndex].map(([i, v]) => [i, v.ohrsHutId] as const)),
    [hutOhrsByIndex],
  )

  const hutClassByIndex = useMemo(
    () => new Map(hutsByIndex.map((c, i) => [i, c]).filter((entry): entry is [number, HutClass] => entry[1] != null)),
    [hutsByIndex],
  )
  const excludedHutIndices = useMemo(() => {
    const allowed = graphData ? buildQuery(form, hutsByIndex).allowedHutIndices : undefined
    if (!allowed) return new Set<number>()
    const excluded = new Set<number>()
    hutClassByIndex.forEach((_c, i) => {
      if (!allowed.has(i)) excluded.add(i)
    })
    return excluded
  }, [form, hutsByIndex, hutClassByIndex, graphData])

  const pageCount = Math.max(1, Math.ceil(displayedChains.length / PAGE_SIZE))
  const pageChains = useMemo(
    () => displayedChains.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [displayedChains, page],
  )

  const selectedChain = expandedChain !== null ? (displayedChains[expandedChain] ?? null) : null

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!graphData) return
    setSearching(true)
    setResult(null)
    setExpandedChain(null)

    let fetchedAvailability: FreeByOffset | null = null
    if (form.startDate) {
      fetchedAvailability = await fetchAvailabilityByOffset(new Date(form.startDate), form.numOfPeople, form.legCountRange[1] - 1)
    }
    setFreeByOffset(fetchedAvailability)

    // Defer the heavy synchronous findTours call a tick so React can paint the spinner first
    // (spec D: no Web Worker in this spec's scope).
    setTimeout(() => {
      const query = buildQuery(
        form, hutsByIndex,
        fetchedAvailability ? { ohrsIdByHutIndex, freeByOffset: fetchedAvailability } : undefined,
      )
      setResult(findTours(query, graphData))
      setPage(1)
      setSearching(false)
    }, 0)
  }

  function handleReset() {
    setForm(DEFAULT_FORM)
    setResult(null)
    setExpandedChain(null)
    setFreeByOffset(null)
  }

  return (
    <AppShell
      title="Tourensuche"
      status={error ? `Fehler: ${error}` : graphData ? 'Daten geladen' : 'Lade Daten…'}
    >
      <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
        <Box
          component="form"
          onSubmit={handleSubmit}
          sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'flex-start', p: 2, borderBottom: '1px solid #e0e0e0' }}
        >
          <Box sx={{ width: 220 }}>
            <Typography variant="subtitle2">Modus</Typography>
            <Select
              fullWidth
              size="small"
              value={form.mode}
              onChange={(e: SelectChangeEvent) => setForm((f) => ({ ...f, mode: e.target.value as TourMode }))}
            >
              <MenuItem value="car">Auto (Rundtour zum Ausgangspunkt)</MenuItem>
              <MenuItem value="transit">ÖPNV (offene Strecke)</MenuItem>
              <MenuItem value="village">Start im Bergsteigerdorf (offene Strecke)</MenuItem>
            </Select>
          </Box>

          <Box sx={{ width: 220 }}>
            <LegCountSlider
              value={form.legCountRange}
              onCommit={(legCountRange) => setForm((f) => ({ ...f, legCountRange }))}
            />
          </Box>

          <Box sx={{ width: 220 }}>
            <LegTimeSlider
              value={form.legTimeRange}
              onCommit={(legTimeRange) => setForm((f) => ({ ...f, legTimeRange }))}
            />
          </Box>

          <Box sx={{ width: 240 }}>
            <Typography variant="subtitle2">Schwierigkeit</Typography>
            <Select
              fullWidth
              size="small"
              value={form.sacCeiling}
              onChange={(e: SelectChangeEvent<number | 'any'>) =>
                setForm((f) => ({ ...f, sacCeiling: e.target.value === 'any' ? 'any' : Number(e.target.value) }))
              }
              sx={{ mb: 1 }}
            >
              <MenuItem value={1}>T1 Wandern</MenuItem>
              <MenuItem value={2}>T2 Bergwandern</MenuItem>
              <MenuItem value={3}>T3 anspruchsvolles Bergwandern</MenuItem>
              <MenuItem value="any">beliebig</MenuItem>
            </Select>
            <FormControlLabel
              control={<Checkbox checked={form.allowUngraded} onChange={(e) => setForm((f) => ({ ...f, allowUngraded: e.target.checked }))} />}
              label="auch ungeratete Wege erlauben"
            />
            <FormControlLabel
              sx={{ display: 'block' }}
              control={<Checkbox checked={form.allowViaFerrata} onChange={(e) => setForm((f) => ({ ...f, allowViaFerrata: e.target.checked }))} />}
              label="Klettersteige erlauben"
            />
          </Box>

          <Box sx={{ width: 260 }}>
            <Typography variant="subtitle2">Hüttenarten</Typography>
            {(Object.keys(OPERATOR_LABEL) as HutOperator[]).map((op) => (
              <FormControlLabel
                key={op}
                sx={{ display: 'block' }}
                control={
                  <Checkbox
                    checked={form.allowedOperators.has(op)}
                    onChange={(e) =>
                      setForm((f) => {
                        const next = new Set(f.allowedOperators)
                        if (e.target.checked) next.add(op)
                        else next.delete(op)
                        return { ...f, allowedOperators: next }
                      })
                    }
                  />
                }
                label={OPERATOR_LABEL[op]}
              />
            ))}
            <FormControlLabel
              sx={{ display: 'block' }}
              control={<Checkbox checked={form.allowServiced} onChange={(e) => setForm((f) => ({ ...f, allowServiced: e.target.checked }))} />}
              label="Bewirtschaftete Hütten"
            />
            <FormControlLabel
              sx={{ display: 'block' }}
              control={<Checkbox checked={form.allowSelfService} onChange={(e) => setForm((f) => ({ ...f, allowSelfService: e.target.checked }))} />}
              label="Selbstversorgerhütten (unbewirtschaftet, ggf. Schlüssel nötig)"
            />
            {!isFilterSelectionValid(form) && (
              <Typography variant="caption" color="error">
                Mindestens ein Betreiber und eine Betriebsart müssen ausgewählt sein.
              </Typography>
            )}
          </Box>

          <Box sx={{ width: 280 }}>
            <Accordion disableGutters elevation={0} sx={{ border: '1px solid #e0e0e0', '&:before': { display: 'none' } }}>
              <AccordionSummary sx={{ minHeight: 0, '& .MuiAccordionSummary-content': { my: 1 } }}>
                <Typography variant="subtitle2">Erweiterte Optionen</Typography>
              </AccordionSummary>
              <AccordionDetails sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
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
              </AccordionDetails>
            </Accordion>
          </Box>

          <Box sx={{ width: 220 }}>
            <Typography variant="subtitle2">Startdatum (optional)</Typography>
            <TextField
              fullWidth
              size="small"
              type="date"
              label="Startdatum"
              slotProps={{ inputLabel: { shrink: true } }}
              value={form.startDate}
              onChange={(e) => setForm((f) => ({ ...f, startDate: e.target.value }))}
            />
            {form.startDate && (
              <>
                <TextField
                  fullWidth
                  size="small"
                  type="number"
                  label="Personenzahl"
                  sx={{ mt: 1 }}
                  slotProps={{ htmlInput: { min: 1, max: 9 } }}
                  value={form.numOfPeople}
                  onChange={(e) => setForm((f) => ({ ...f, numOfPeople: Number(e.target.value) || 1 }))}
                />
                <FormControlLabel
                  sx={{ display: 'block' }}
                  control={<Checkbox checked={form.onlyAvailable} onChange={(e) => setForm((f) => ({ ...f, onlyAvailable: e.target.checked }))} />}
                  label="nur Touren mit Verfügbarkeit"
                />
              </>
            )}
          </Box>

          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', ml: 'auto' }}>
            <Button type="submit" variant="contained" disabled={!graphData || searching || !isFilterSelectionValid(form)} startIcon={searching ? <CircularProgress size={16} color="inherit" /> : undefined}>
              Touren suchen
            </Button>
            <Button type="button" variant="outlined" onClick={handleReset}>
              Zurücksetzen
            </Button>
          </Box>
        </Box>

        <Box sx={{ display: 'flex', flex: 1, minHeight: 0 }}>
          {result && (
            <TourList
              result={result}
              displayedChains={displayedChains}
              pageChains={pageChains}
              page={page}
              pageCount={pageCount}
              setPage={setPage}
              sortKey={sortKey}
              setSortKey={setSortKey}
              hutNameById={hutNameById}
              hutClassByIndex={hutClassByIndex}
              startLabel={startLabel}
              expandedChain={expandedChain}
              setExpandedChain={setExpandedChain}
              mode={form.mode}
              freeByOffset={freeByOffset}
              ohrsIdByHutIndex={ohrsIdByHutIndex}
              hutOhrsByIndex={hutOhrsByIndex}
              startDate={form.startDate ? new Date(form.startDate) : null}
              numOfPeople={form.numOfPeople}
            />
          )}
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <ResultsMap
              selectedChain={selectedChain}
              hutNameById={hutNameById}
              hutCoordsById={hutCoordsById}
              startById={startById}
              hutClassByIndex={hutClassByIndex}
              excludedHutIndices={excludedHutIndices}
            />
          </Box>
        </Box>
      </Box>
    </AppShell>
  )
}

export default TourSearchPage
