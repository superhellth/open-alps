import { useEffect, useMemo, useState } from 'react'
import { loadTourSearchData, findTours } from './tourSearch/index.js'
import './App.css'

const HUTS_URL = '/data/huts.geojson'
const PARKING_URL = '/data/parking.geojson'
const STATIONS_URL = '/data/stations.geojson'

const SOURCE_TYPE_STATION = 1
const SOURCE_TYPE_PARKING = 2
const SOURCE_TYPE_LABEL = { [SOURCE_TYPE_STATION]: 'Bahnhof', [SOURCE_TYPE_PARKING]: 'Parkplatz' }

const DEFAULT_QUERY = {
  mode: 'car',
  legCountMin: 2,
  legCountMax: 4,
  sacCeiling: 3,
  allowUngraded: true,
  maxLegTimeH: 8,
  minLegTimeH: 0,
  legAscentCapM: '',
  maxEleM: '',
  allowViaFerrata: true,
}

// OSM feature ids in parking.geojson/stations.geojson are prefixed ("n123") - approaches.startId
// is the bare numeric OSM node id, so this strips the prefix to join the two.
function idFromOsmFeatureId(featureId) {
  const n = Number(String(featureId).replace(/^\D+/, ''))
  return Number.isFinite(n) ? n : null
}

function toNumberOrDefault(value, fallback) {
  if (value === '' || value == null) return fallback
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

function buildQuery(form) {
  return {
    mode: form.mode,
    legCountMin: toNumberOrDefault(form.legCountMin, DEFAULT_QUERY.legCountMin),
    legCountMax: toNumberOrDefault(form.legCountMax, DEFAULT_QUERY.legCountMax),
    sacCeiling: form.sacCeiling === 'any' ? null : Number(form.sacCeiling),
    allowUngraded: form.allowUngraded,
    maxLegTimeH: toNumberOrDefault(form.maxLegTimeH, DEFAULT_QUERY.maxLegTimeH),
    minLegTimeH: toNumberOrDefault(form.minLegTimeH, DEFAULT_QUERY.minLegTimeH),
    legAscentCapM: toNumberOrDefault(form.legAscentCapM, Infinity),
    maxEleM: form.maxEleM === '' ? null : toNumberOrDefault(form.maxEleM, null),
    allowViaFerrata: form.allowViaFerrata,
  }
}

function TourSearchPage() {
  const [graphData, setGraphData] = useState(null)
  const [hutNameById, setHutNameById] = useState(new Map())
  const [startById, setStartById] = useState(new Map())
  const [error, setError] = useState(null)
  const [form, setForm] = useState(DEFAULT_QUERY)
  const [result, setResult] = useState(null)

  useEffect(() => {
    Promise.all([
      loadTourSearchData(),
      fetch(HUTS_URL).then((r) => r.json()),
      fetch(PARKING_URL).then((r) => r.json()),
      fetch(STATIONS_URL).then((r) => r.json()),
    ])
      .then(([tourSearchData, hutsFc, parkingFc, stationsFc]) => {
        setGraphData(tourSearchData)
        setHutNameById(new Map(hutsFc.features.map((f) => [f.properties.id, f.properties.name])))

        const starts = new Map()
        for (const f of stationsFc.features) {
          const id = idFromOsmFeatureId(f.id)
          if (id != null) starts.set(id, { name: f.properties.name, sourceType: SOURCE_TYPE_STATION })
        }
        for (const f of parkingFc.features) {
          const id = idFromOsmFeatureId(f.id)
          if (id != null) starts.set(id, { name: f.properties.name, sourceType: SOURCE_TYPE_PARKING })
        }
        setStartById(starts)
      })
      .catch((e) => setError(e.message))
  }, [])

  const startLabel = useMemo(
    () => (startId) => {
      const start = startById.get(startId)
      if (!start) return `Startpunkt ${startId}`
      const kind = SOURCE_TYPE_LABEL[start.sourceType] ?? 'Startpunkt'
      return start.name ? `${start.name} (${kind})` : kind
    },
    [startById]
  )

  function handleChange(field, value) {
    setForm((f) => ({ ...f, [field]: value }))
  }

  function handleSubmit(e) {
    e.preventDefault()
    if (!graphData) return
    setResult(findTours(buildQuery(form), graphData))
  }

  return (
    <div className="app">
      <header>
        <h1>Tourensuche</h1>
        <a href="#" className="nav-link">
          Karte
        </a>
        <a href="#graph" className="nav-link">
          Trail-Graph
        </a>
        <span>
          {error ? `Fehler: ${error}` : graphData ? 'Daten geladen' : 'Lade Daten…'}
        </span>
      </header>

      <div className="tour-search-body">
        <form className="tour-search-form" onSubmit={handleSubmit}>
          <label>
            Modus
            <select value={form.mode} onChange={(e) => handleChange('mode', e.target.value)}>
              <option value="car">Auto (Rundtour zum Ausgangspunkt)</option>
              <option value="transit">ÖPNV (offene Strecke)</option>
            </select>
          </label>

          <label>
            Etappen (min–max)
            <div className="range-pair">
              <input
                type="number"
                min="1"
                value={form.legCountMin}
                onChange={(e) => handleChange('legCountMin', e.target.value)}
              />
              <input
                type="number"
                min="1"
                value={form.legCountMax}
                onChange={(e) => handleChange('legCountMax', e.target.value)}
              />
            </div>
          </label>

          <label>
            Schwierigkeit (max. SAC-Skala)
            <select
              value={form.sacCeiling ?? 'any'}
              onChange={(e) => handleChange('sacCeiling', e.target.value)}
            >
              <option value="2">T2 Bergwandern</option>
              <option value="3">T3 anspruchsvolles Bergwandern</option>
              <option value="any">beliebig</option>
            </select>
          </label>

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={form.allowUngraded}
              onChange={(e) => handleChange('allowUngraded', e.target.checked)}
            />
            auch ungeratete Wege erlauben
          </label>

          <label>
            Gehzeit pro Etappe, Stunden (min–max)
            <div className="range-pair">
              <input
                type="number"
                min="0"
                step="0.5"
                value={form.minLegTimeH}
                onChange={(e) => handleChange('minLegTimeH', e.target.value)}
              />
              <input
                type="number"
                min="0"
                step="0.5"
                value={form.maxLegTimeH}
                onChange={(e) => handleChange('maxLegTimeH', e.target.value)}
              />
            </div>
          </label>

          <label>
            Anstiegslimit pro Etappe (m, leer = unbegrenzt)
            <input
              type="number"
              min="0"
              value={form.legAscentCapM}
              onChange={(e) => handleChange('legAscentCapM', e.target.value)}
            />
          </label>

          <label>
            Maximalhöhe (m, leer = unbegrenzt)
            <input
              type="number"
              value={form.maxEleM}
              onChange={(e) => handleChange('maxEleM', e.target.value)}
            />
          </label>

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={form.allowViaFerrata}
              onChange={(e) => handleChange('allowViaFerrata', e.target.checked)}
            />
            Klettersteige erlauben
          </label>

          <button type="submit" disabled={!graphData}>
            Touren suchen
          </button>
        </form>

        <div className="tour-search-results">
          {result && (
            <>
              <p className="tour-search-summary">
                {result.chains.length} Tour{result.chains.length === 1 ? '' : 'en'} gefunden
                {' · verworfen: '}
                {Object.entries(result.killCounters)
                  .filter(([, n]) => n > 0)
                  .map(([k, n]) => `${k}: ${n}`)
                  .join(', ') || 'keine'}
              </p>
              {result.chains.length === 0 && (
                <p>Keine Touren gefunden. Filter lockern und erneut versuchen.</p>
              )}
              <ul className="tour-search-chain-list">
                {result.chains.map((chain, i) => (
                  <li key={i} className="tour-search-chain">
                    <div className="tour-search-chain-route">
                      {startLabel(chain.startId)}
                      {chain.huts.map((h) => ` → ${hutNameById.get(graphData.hutEdges.hutIds[h]) ?? h}`).join('')}
                      {' → '}
                      {startLabel(chain.exitStartId)}
                    </div>
                    <div className="tour-search-chain-stats">
                      {chain.totalDurationH.toFixed(1)} h · ↑{Math.round(chain.totalAscentM)}m ↓
                      {Math.round(chain.totalDescentM)}m · {(chain.totalDistanceM / 1000).toFixed(1)} km
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default TourSearchPage
