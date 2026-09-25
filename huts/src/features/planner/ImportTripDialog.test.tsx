// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import ImportTripDialog from './ImportTripDialog.js'
import { newTrip } from '@/trip/trip.js'

afterEach(cleanup)

const trip = newTrip({
  name: 'Geteilte Tour', startDate: '2026-07-10', partySize: 2, start: { startId: 1, sourceType: 1 }, huts: ['{A}', '{B}'],
  exit: { startId: 1, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
}, new Date(), 'id')

describe('ImportTripDialog', () => {
  it('is closed without a trip', () => {
    render(<ImportTripDialog trip={null} onImport={() => {}} onDiscard={() => {}} />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
  it('offers to import a shared trip, naming it, and never imports on its own', () => {
    const onImport = vi.fn()
    const onDiscard = vi.fn()
    render(<ImportTripDialog trip={trip} onImport={onImport} onDiscard={onDiscard} />)
    expect(screen.getByText('Geteilte Tour')).toBeInTheDocument()
    expect(onImport).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'In meine Touren übernehmen' }))
    expect(onImport).toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Verwerfen' }))
    expect(onDiscard).toHaveBeenCalled()
  })
})
