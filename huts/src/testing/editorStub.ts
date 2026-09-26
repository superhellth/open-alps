import { vi } from 'vitest'
import type { TripEditor } from '@/features/trip/TripEditor.js'

/** A `TripEditor` with inert actions, for component tests. */
export function makeEditorStub(over: Partial<TripEditor> = {}): TripEditor {
  return {
    editing: null, editable: true, car: false, candidates: [], pickCandidate: vi.fn(), activeLabel: null,
    trimAllowed: () => ({ ok: true }), trim: vi.fn(), startSwap: vi.fn(), startExtend: vi.fn(), startEndpoint: vi.fn(), cancel: vi.fn(),
    ...over,
  }
}
