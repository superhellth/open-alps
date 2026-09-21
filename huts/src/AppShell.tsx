import type { ReactNode } from 'react'
import { AppBar, Box, Tab, Tabs, Toolbar, Typography } from '@mui/material'

const TABS = [
  { hash: '', label: 'Planen' },
  { hash: '#trips', label: 'Meine Touren' },
] as const

interface AppShellProps {
  title: string
  status?: ReactNode
  children: ReactNode
}

/** A share link belongs to the planner tab; the admin view is unlinked from the nav, so no tab is active. */
export function activeTabIndex(hash: string): number | false {
  if (hash.startsWith('#trip=')) return 0
  const index = TABS.findIndex((t) => t.hash === hash)
  return index === -1 ? false : index
}

function AppShell({ title, status, children }: AppShellProps) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <AppBar position="static">
        <Toolbar sx={{ gap: 2, flexWrap: 'wrap' }}>
          <Typography variant="h6" component="h1" sx={{ fontSize: '1.1rem' }}>
            {title}
          </Typography>
          <Tabs
            value={activeTabIndex(window.location.hash)}
            textColor="inherit"
            indicatorColor="secondary"
            sx={{ minHeight: 0 }}
          >
            {TABS.map((tab) => (
              <Tab
                key={tab.hash}
                label={tab.label}
                href={tab.hash || '#'}
                component="a"
                sx={{ minHeight: 0, color: 'inherit' }}
              />
            ))}
          </Tabs>
          <Box sx={{ marginLeft: 'auto', fontSize: '0.85rem', opacity: 0.85 }}>{status}</Box>
        </Toolbar>
      </AppBar>
      <Box sx={{ flex: 1, minHeight: 0, display: 'flex' }}>{children}</Box>
    </Box>
  )
}

export default AppShell
