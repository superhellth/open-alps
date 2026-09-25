// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useFirstVisitPrompt } from './useFirstVisitPrompt.js'

function memoryStorage(initial: Record<string, string> = {}) {
  const data = { ...initial }
  return { getItem: (k: string) => data[k] ?? null, setItem: (k: string, v: string) => { data[k] = v }, data }
}

describe('useFirstVisitPrompt', () => {
  it('is visible on the first visit and remembers the dismissal', () => {
    const storage = memoryStorage()
    const { result } = renderHook(() => useFirstVisitPrompt(storage))
    expect(result.current.visible).toBe(true)
    act(() => result.current.dismiss())
    expect(result.current.visible).toBe(false)
    expect(storage.data['open-alps.prompt-seen']).toBe('1')
    expect(renderHook(() => useFirstVisitPrompt(storage)).result.current.visible).toBe(false)
  })
  it('still works when storage is unavailable', () => {
    const { result } = renderHook(() => useFirstVisitPrompt(null))
    expect(result.current.visible).toBe(true)
    act(() => result.current.dismiss())
    expect(result.current.visible).toBe(false)
  })
  it('survives throwing storage', () => {
    const throwing = { getItem: () => { throw new Error('x') }, setItem: () => { throw new Error('x') } }
    const { result } = renderHook(() => useFirstVisitPrompt(throwing))
    act(() => result.current.dismiss())
    expect(result.current.visible).toBe(false)
  })
})
