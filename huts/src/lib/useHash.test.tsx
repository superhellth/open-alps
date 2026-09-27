// @vitest-environment jsdom
import { act } from 'react'
import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { useHash } from './useHash.js'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  window.location.hash = ''
})

function Probe() {
  return <span>hash:{useHash()}</span>
}

describe('useHash', () => {
  it('re-renders with the new hash on hashchange', () => {
    render(<Probe />)
    expect(screen.getByText('hash:')).toBeInTheDocument()
    act(() => {
      window.location.hash = '#a'
      window.dispatchEvent(new HashChangeEvent('hashchange'))
    })
    expect(screen.getByText('hash:#a')).toBeInTheDocument()
  })

  it('removes its listener on unmount', () => {
    const remove = vi.spyOn(window, 'removeEventListener')
    const { unmount } = render(<Probe />)
    unmount()
    expect(remove).toHaveBeenCalledWith('hashchange', expect.any(Function))
  })
})
