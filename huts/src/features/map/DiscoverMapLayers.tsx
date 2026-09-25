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
  hoveredTourKey: string | null
  previewStartId: number | null
  /** Called when a marker is clicked — navigation only, no filtering. */
  onNavigate: () => void
  onFocusStarts: (startIds: number[] | null) => void
  onHoverStarts: (startIds: Set<number> | null) => void
  /** Called whenever the map's bbox/zoom changes, so the list can mirror it. */
  onViewChange: (view: View) => void
  onHoverTour: (key: string | null) => void
  onPickRoute: (tour: PlannerTour) => void
}

export function DiscoverMapLayers({ mode }: { mode: DiscoverMapMode }) {
  return (
    <DiscoverLayer
      groups={mode.groups} startById={mode.startById} dimmed={mode.dimmed}
      onNavigate={mode.onNavigate} onFocusStarts={mode.onFocusStarts} onHoverStarts={mode.onHoverStarts} onViewChange={mode.onViewChange}
      allTours={mode.allTours} routeCtx={mode.routeCtx}
      hoveredTourKey={mode.hoveredTourKey} onHoverTour={mode.onHoverTour} previewStartId={mode.previewStartId} onPickRoute={mode.onPickRoute}
    />
  )
}
