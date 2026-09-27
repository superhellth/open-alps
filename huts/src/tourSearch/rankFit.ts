export type NightState = 'free' | 'full' | 'unknown'

/** The slice of a tour ranking needs; huts.length is the night count, legs includes approach and exit. */
export interface FitTour {
  huts: number[]
  legs: { durationH: number }[]
}

export interface RankTargets {
  legCountTarget: number
  legCountRange: [number, number]
  legTimeRangeH: [number, number]
}

export const RANK_WEIGHTS = { legCount: 1, legTime: 1, variance: 0.5, availability: 2 }

const NIGHT_PENALTY: Record<NightState, number> = { free: 0, unknown: 0.5, full: 1 }

/** Lower is a better fit. Filters stay hard limits elsewhere; this only orders what passed them. */
export function fitScore<T extends FitTour>(
  tour: T, targets: RankTargets, nightState?: (tour: T, night: number) => NightState,
): number {
  const [countMin, countMax] = targets.legCountRange
  const [timeMin, timeMax] = targets.legTimeRangeH
  const midTime = (timeMin + timeMax) / 2
  const timeScale = Math.max(0.5, (timeMax - timeMin) / 2)
  const durations = tour.legs.map((l) => l.durationH)
  const mean = durations.reduce((s, d) => s + d, 0) / durations.length

  const legCountTerm = Math.abs(tour.legs.length - targets.legCountTarget) / Math.max(1, countMax - countMin)
  const legTimeTerm = durations.reduce((s, d) => s + Math.abs(d - midTime), 0) / durations.length / timeScale
  const variance = durations.reduce((s, d) => s + (d - mean) ** 2, 0) / durations.length
  const varianceTerm = Math.sqrt(variance) / timeScale

  let score = RANK_WEIGHTS.legCount * legCountTerm + RANK_WEIGHTS.legTime * legTimeTerm + RANK_WEIGHTS.variance * varianceTerm
  if (nightState && tour.huts.length > 0) {
    let penalty = 0
    for (let night = 0; night < tour.huts.length; night++) penalty += NIGHT_PENALTY[nightState(tour, night)]
    score += RANK_WEIGHTS.availability * (penalty / tour.huts.length)
  }
  return score
}

export function rankFit<T extends FitTour>(
  tours: T[], targets: RankTargets, nightState?: (tour: T, night: number) => NightState,
): T[] {
  return tours
    .map((tour, index) => ({ tour, index, score: fitScore(tour, targets, nightState) }))
    .sort((a, b) => a.score - b.score || a.index - b.index)
    .map((entry) => entry.tour)
}
