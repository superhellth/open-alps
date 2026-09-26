import type { StyleMap } from '@/ui/styleMap.js'
import { space } from '@/ui/tokens.js'

export const styles = {
  root: { p: space.inset, display: 'flex', flexDirection: 'column', gap: space.group },
  stepperButton: { width: 40, height: 40, minWidth: 0, p: 0 },
  accordion: { bgcolor: 'transparent', '&:before': { display: 'none' } },
  accordionSummary: {
    px: space.item, borderRadius: 1,
    mx: -1, // design-exempt: MUI accordion summary margin override
    minHeight: 0, '&.Mui-expanded': { minHeight: 0 },
    '&:hover': { bgcolor: 'action.hover' },
    '& .MuiAccordionSummary-content': { margin: '4px 0', '&.Mui-expanded': { margin: '4px 0' } }, // design-exempt: MUI accordion summary margin override
    '& .MuiAccordionSummary-expandIconWrapper.Mui-expanded': { transform: 'none' },
  },
  accordionDetails: { display: 'flex', flexDirection: 'column', gap: space.item, p: 0, pt: space.item },
  hutClassHeading: { display: 'flex', alignItems: 'center', gap: space.inline },
  twoColumns: { display: 'flex', gap: space.group },
  stepperRow: { display: 'flex', gap: space.item, alignItems: 'center' },
  chipRow: { display: 'flex', gap: space.item },
} satisfies StyleMap
