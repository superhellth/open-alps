import type { SxProps, Theme } from '@mui/material/styles'
import { alpha } from '@mui/material/styles'
import type { StyleMap } from '@/ui/styleMap.js'
import { opacity, space, tokens } from '@/ui/tokens.js'

export const styles = {
  root: { display: 'flex', flexDirection: 'column', height: '100vh' },
  body: { display: 'flex', flex: 1, minHeight: 0 },
  sidebar: { width: 420, flexShrink: 0, overflowY: 'auto', borderRight: '2px solid', borderColor: 'secondary.main' },
  discoverTabs: { position: 'sticky', top: 0, zIndex: 2, bgcolor: 'background.paper' },
  resultsBar: (raised: boolean): SxProps<Theme> => ({
    position: 'sticky', bottom: 0, zIndex: 1, display: 'flex', justifyContent: 'center', py: space.item,
    bgcolor: 'background.paper',
    ...(raised && { borderTop: '1px solid', borderColor: 'divider', boxShadow: `0 -4px 8px -4px ${alpha(tokens.ink, opacity.shadow)}` }),
  }),
  resultsBadge: { pr: space.item },
  shareFallback: { p: space.inset },
  mapPane: { flex: 1, minWidth: 0, position: 'relative' },
} satisfies StyleMap
