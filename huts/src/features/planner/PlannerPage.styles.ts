import type { SxProps, Theme } from '@mui/material/styles'
import { alpha } from '@mui/material/styles'
import type { StyleMap } from '@/ui/styleMap.js'

export const styles = {
  root: { display: 'flex', flexDirection: 'column', height: '100vh' },
  body: { display: 'flex', flex: 1, minHeight: 0 },
  sidebar: { width: 420, flexShrink: 0, overflowY: 'auto', borderRight: '2px solid', borderColor: 'secondary.main' },
  discoverTabs: { position: 'sticky', top: 0, zIndex: 2, bgcolor: 'background.paper' },
  resultsBar: (raised: boolean): SxProps<Theme> => ({
    position: 'sticky', bottom: 0, zIndex: 1, display: 'flex', justifyContent: 'center', py: 1,
    bgcolor: 'background.paper',
    ...(raised && { borderTop: '1px solid', borderColor: 'divider', boxShadow: `0 -4px 8px -4px ${alpha('#000', 0.15)}` }),
  }),
  mapPane: { flex: 1, minWidth: 0, position: 'relative' },
} satisfies StyleMap
