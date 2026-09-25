import type { StyleMap } from '@/ui/styleMap.js'

export const styles = {
  root: { p: 2, display: 'flex', flexDirection: 'column', gap: 1.5 },
  stepperButton: { width: 40, height: 40, minWidth: 0, p: 0 },
  accordion: { bgcolor: 'transparent', '&:before': { display: 'none' } },
  accordionSummary: {
    px: 1, mx: -1, borderRadius: 1, minHeight: 0, '&.Mui-expanded': { minHeight: 0 },
    '&:hover': { bgcolor: 'action.hover' },
    '& .MuiAccordionSummary-content': { margin: '4px 0', '&.Mui-expanded': { margin: '4px 0' } },
    '& .MuiAccordionSummary-expandIconWrapper.Mui-expanded': { transform: 'none' },
  },
  accordionDetails: { display: 'flex', flexDirection: 'column', gap: 1, p: 0, pt: 1 },
  hutClassHeading: { display: 'flex', alignItems: 'center', gap: 0.5, mt: 1 },
} satisfies StyleMap
