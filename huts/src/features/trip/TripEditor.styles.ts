import type { StyleMap } from '@/ui/styleMap.js'

export const styles = {
  candidateButton: { justifyContent: 'space-between', textTransform: 'none' },
  swapCandidates: { mt: 0.5, display: 'flex', flexDirection: 'column', gap: 0.5 },
  endpointCandidates: { display: 'flex', flexDirection: 'column', gap: 0.5, width: '100%' },
} satisfies StyleMap
