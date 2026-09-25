export type HutOperator = 'av' | 'sonstige'

export interface HutClass {
  operator: HutOperator
  serviced: boolean
}

export const OPERATOR_LABEL: Record<HutOperator, string> = {
  av: 'Alpenverein',
  sonstige: 'Sonstige',
}

const OPERATOR_BADGE: Record<HutOperator, string> = {
  av: 'AV',
  sonstige: 'SO',
}

// Colours distinguishable in both light and dark map tile contexts, distinct from AdminPage's
// existing snapped/unsnapped green (#1b5e20/#43a047) and gray (#616161/#bdbdbd).
export const OPERATOR_COLOR: Record<HutOperator, string> = {
  av: '#1565c0',
  sonstige: '#6a1b9a',
}

export const PARTNER_LABEL = 'Partnerbetrieb (Bergsteigerdorf)'
export const PARTNER_COLOR = '#ef6c00'

/** Full user-facing label, e.g. "Alpenverein (Selbstversorger)". */
export function hutClassLabel(c: HutClass): string {
  return c.serviced ? OPERATOR_LABEL[c.operator] : `${OPERATOR_LABEL[c.operator]} (Selbstversorger)`
}

export type HutClassKey = `${HutOperator}:${'serviced' | 'self'}`

export function hutClassKey(c: HutClass): HutClassKey {
  return `${c.operator}:${c.serviced ? 'serviced' : 'self'}`
}

/** All four (operator, service-status) combinations, in a fixed row-major order for grid layout. */
export const ALL_HUT_CLASSES: HutClass[] = [
  { operator: 'av', serviced: true }, { operator: 'av', serviced: false },
  { operator: 'sonstige', serviced: true }, { operator: 'sonstige', serviced: false },
]

/** Two-to-four character text badge, e.g. "AV", "AV·SV", "SO", "SO·SV" — text, not colour alone. */
export function hutClassBadge(c: HutClass): string {
  return c.serviced ? OPERATOR_BADGE[c.operator] : `${OPERATOR_BADGE[c.operator]}·SV`
}

export type HutFill = 'filled' | 'outline'

export function hutFill(c: HutClass): HutFill {
  return c.serviced ? 'filled' : 'outline'
}
