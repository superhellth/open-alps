import { describe, it, expect } from 'vitest'
import { activeTabIndex } from './AppShell.js'

describe('activeTabIndex', () => {
  it('maps the planner and trips routes to their tabs', () => {
    expect(activeTabIndex('')).toBe(0)
    expect(activeTabIndex('#trips')).toBe(1)
  })
  it('a share link belongs to the planner tab', () => {
    expect(activeTabIndex('#trip=abc')).toBe(0)
  })
  it('the admin view is unlinked from the customer nav: no tab is active', () => {
    expect(activeTabIndex('#admin')).toBe(false)
  })
})
