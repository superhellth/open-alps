export interface TileConfig {
  url: string
  attribution: string
  subdomains: string
  maxZoom: number
}

export const OPEN_TOPO_MAP: TileConfig = {
  url: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
  attribution: 'Kartendaten: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>-Mitwirkende, SRTM | Kartendarstellung: &copy; <a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA) | Hüttendaten: Alpenverein / ArcGIS',
  subdomains: 'abc',
  maxZoom: 17,
}

export const OSM_TILES: TileConfig = {
  url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> | Hüttendaten: Alpenverein / ArcGIS',
  subdomains: 'abc',
  maxZoom: 19,
}

/** The tile source in use. Set to OSM_TILES if the usage-policy check recorded in the spec's
 *  measured findings rules OpenTopoMap out. */
export const ACTIVE_TILES: TileConfig = OPEN_TOPO_MAP
