export type HutOperator = 'av' | 'sonstige'

export interface HutClass {
  operator: HutOperator
  serviced: boolean
}

export const OPERATOR_LABEL: Record<HutOperator, string> = {
  av: 'AV-Hütte',
  sonstige: 'Sonstige Hütte',
}

const OPERATOR_BADGE: Record<HutOperator, string> = {
  av: 'AV',
  sonstige: 'SO',
}

// Colours distinguishable in both light and dark map tile contexts, distinct from GraphPage's
// existing snapped/unsnapped green (#1b5e20/#43a047) and gray (#616161/#bdbdbd).
export const OPERATOR_COLOR: Record<HutOperator, string> = {
  av: '#1565c0',
  sonstige: '#6a1b9a',
}

export const PARTNER_LABEL = 'Partnerbetrieb (Bergsteigerdorf)'
export const PARTNER_COLOR = '#ef6c00'

/** Full user-facing label, e.g. "AV-Hütte (Selbstversorger)". */
export function hutClassLabel(c: HutClass): string {
  return c.serviced ? OPERATOR_LABEL[c.operator] : `${OPERATOR_LABEL[c.operator]} (Selbstversorger)`
}

/** Two-to-four character text badge, e.g. "AV", "AV·SV", "SO", "SO·SV" — text, not colour alone. */
export function hutClassBadge(c: HutClass): string {
  return c.serviced ? OPERATOR_BADGE[c.operator] : `${OPERATOR_BADGE[c.operator]}·SV`
}
