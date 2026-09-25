// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { renderHook, act, cleanup } from '@testing-library/react'
import { useMapView } from './useMapView.js'

afterEach(cleanup)

describe('useMapView', () => {
  it('restores the centre and zoom remembered before a trip', () => {
    const { result } = renderHook(() => useMapView())
    act(() => result.current.setMapView({ bbox: [10, 46, 12, 48], zoom: 9 }))
    act(() => result.current.rememberViewBeforeTrip())
    act(() => result.current.restoreViewAfterTrip())
    expect(result.current.restoreView).toEqual({ lat: 47, lng: 11, zoom: 9 })
  })

  it('fitToPoints sets [[south, west], [north, east]]', () => {
    const { result } = renderHook(() => useMapView())
    act(() => result.current.fitToPoints([{ lat: 47, lng: 11 }, { lat: 48, lng: 13 }]))
    expect(result.current.fitBounds).toEqual([[47, 11], [48, 13]])
  })
})
