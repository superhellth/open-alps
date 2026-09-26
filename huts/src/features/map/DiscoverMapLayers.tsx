import type { StartGroup } from '@/tourSearch/groupByStart.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import type { StartPoint } from '@/data/types.js'
import type { View } from '@/lib/viewport.js'
import DiscoverLayer from './DiscoverLayer.js'
import type { RouteContext } from './routes.js'

export interface DiscoverMapMode {
  kind: 'discover'
  groups: StartGroup<PlannerTour>[]
  /** Markers keep their previous counts, dimmed, while a new search runs. */
  dimmed: boolean
  startById: Map<number, StartPoint>
  allTours: PlannerTour[]
  routeCtx: RouteContext | null
  hutNameById: Map<number, string>
  hoveredTourKeys: ReadonlySet<string>
  /** Called when a marker is clicked — navigation only, no filtering. */
  onNavigate: () => void
  /** Tour keys the list and map are focused on; null when unfocused. */
  focusTours: ReadonlySet<string> | null
  onFocusTours: (keys: string[] | null) => void
  /** Called whenever the map's bbox/zoom changes, so the list can mirror it. */
  onViewChange: (view: View) => void
  onHoverTours: (keys: ReadonlySet<string>) => void
  onPickRoute: (tour: PlannerTour) => void
}

export function DiscoverMapLayers({ mode }: { mode: DiscoverMapMode }) {
  return (
    <DiscoverLayer
      groups={mode.groups} startById={mode.startById} dimmed={mode.dimmed}
      onNavigate={mode.onNavigate} focusTours={mode.focusTours} onFocusTours={mode.onFocusTours} onViewChange={mode.onViewChange}
      allTours={mode.allTours} routeCtx={mode.routeCtx}
      hutNameById={mode.hutNameById} hoveredTourKeys={mode.hoveredTourKeys} onHoverTours={mode.onHoverTours} onPickRoute={mode.onPickRoute}
    />
  )
}
