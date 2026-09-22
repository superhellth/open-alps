import type { ReactNode } from 'react'
import { AppBar, Box, Toolbar, Typography } from '@mui/material'
import { SIGNPOST_FONT, tokens } from './theme.js'

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

// Two destinations, shaped like a trail signpost's fingerposts rather than a MUI Tabs bar —
// that widget is already spoken for by the Filter/Ergebnisse switch inside the planner, so
// reusing it here would make the two read as one navigation.
function SignpostNav() {
  const active = activeTabIndex(window.location.hash)
  return (
    <Box component="nav" sx={{ display: 'flex' }}>
      {TABS.map((tab, i) => (
        <Box
          key={tab.hash}
          component="a"
          href={tab.hash || '#'}
          sx={{
            fontFamily: SIGNPOST_FONT,
            fontWeight: 600,
            fontSize: '0.95rem',
            textDecoration: 'none',
            color: i === active ? tokens.paper : tokens.ink,
            backgroundColor: i === active ? tokens.ink : 'transparent',
            border: `2px solid ${tokens.ink}`,
            borderLeftWidth: i === 0 ? 2 : 0,
            padding: '6px 22px 6px 16px',
            clipPath: 'polygon(0 0, calc(100% - 9px) 0, 100% 50%, calc(100% - 9px) 100%, 0 100%)',
            marginRight: '-9px',
            transition: 'color 120ms ease, background-color 120ms ease',
            '&:hover': i === active ? undefined : { backgroundColor: 'rgba(35, 39, 43, 0.08)' },
          }}
        >
          {tab.label}
        </Box>
      ))}
    </Box>
  )
}

function AppShell({ title, status, children }: AppShellProps) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <AppBar position="static">
        <Toolbar sx={{ gap: 4, minHeight: 64 }}>
          <Typography
            variant="h6"
            component="h1"
            sx={{ fontSize: '1.35rem', letterSpacing: '0.01em', flexShrink: 0 }}
          >
            {title}
          </Typography>
          <SignpostNav />
          <Box sx={{ marginLeft: 'auto', fontSize: '0.8rem', opacity: 0.7, flexShrink: 0 }}>{status}</Box>
        </Toolbar>
      </AppBar>
      <Box sx={{ flex: 1, minHeight: 0, display: 'flex' }}>{children}</Box>
    </Box>
  )
}

export default AppShell
