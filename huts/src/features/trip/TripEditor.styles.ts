import type { StyleMap } from '@/ui/styleMap.js'
import { space } from '@/ui/tokens.js'

export const styles = {
  candidateButton: { justifyContent: 'space-between', textTransform: 'none' },
  rowMenu: { display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: space.inline },
  swapCandidates: { display: 'flex', flexDirection: 'column', gap: space.inline, alignSelf: 'stretch' },
  endpointCandidates: { display: 'flex', flexDirection: 'column', gap: space.inline, width: '100%' },
  endpointRow: { display: 'flex', gap: space.item, alignItems: 'center' },
  extendColumn: { display: 'flex', flexDirection: 'column', gap: space.item },
  extendButtons: { display: 'flex', gap: space.item },
  extendCandidates: { display: 'flex', flexDirection: 'column', gap: space.inline },
} satisfies StyleMap
