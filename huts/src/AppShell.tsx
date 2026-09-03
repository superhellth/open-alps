import type { ReactNode } from 'react'
import { AppBar, Box, Tab, Tabs, Toolbar, Typography } from '@mui/material'

const TABS = [
  { hash: '', label: 'Tourensuche' },
  { hash: '#admin', label: 'Admin' },
] as const

interface AppShellProps {
  title: string
  status?: ReactNode
  children: ReactNode
}

function activeTabIndex(): number {
  const hash = window.location.hash
  const index = TABS.findIndex((t) => t.hash === hash)
  return index === -1 ? 0 : index
}

function AppShell({ title, status, children }: AppShellProps) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <AppBar position="static" color="primary">
        <Toolbar sx={{ gap: 2, flexWrap: 'wrap' }}>
          <Typography variant="h6" component="h1" sx={{ fontSize: '1.1rem' }}>
            {title}
          </Typography>
          <Tabs
            value={activeTabIndex()}
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
