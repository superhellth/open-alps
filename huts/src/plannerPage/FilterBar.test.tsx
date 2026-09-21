// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import FilterBar from './FilterBar.js'
import { DEFAULT_FORM } from './formState.js'
import { DEFAULT_DRAFT } from './plannerState.js'

afterEach(cleanup)

const base = () => ({
  form: DEFAULT_FORM, draft: DEFAULT_DRAFT, disabled: false, searching: false,
  onFormChange: vi.fn(), onDraftChange: vi.fn(),
})

describe('FilterBar', () => {
  it('is disabled with a loading note until the graph is ready', () => {
    render(<FilterBar {...base()} disabled />)
    expect(screen.getByText('Wegenetz wird geladen …')).toBeInTheDocument()
    expect(screen.getByLabelText('Klettersteige erlauben')).toBeDisabled()
  })
  it('shows a thin progress line only while searching', () => {
    const { rerender } = render(<FilterBar {...base()} />)
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    rerender(<FilterBar {...base()} searching />)
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
  })
  it('reports form changes as patches', () => {
    const props = base()
    render(<FilterBar {...props} />)
    fireEvent.click(screen.getByLabelText('Klettersteige erlauben'))
    expect(props.onFormChange).toHaveBeenCalledWith({ allowViaFerrata: false })
  })
  it('keeps start date and party size on the trip draft, not the form', () => {
    const props = base()
    render(<FilterBar {...props} />)
    fireEvent.change(screen.getByLabelText('Startdatum (erste Nacht)'), { target: { value: '2026-07-10' } })
    expect(props.onDraftChange).toHaveBeenCalledWith({ startDate: '2026-07-10' })
  })
  it('only offers the availability filter once a date is set', () => {
    const props = base()
    const { rerender } = render(<FilterBar {...props} />)
    expect(screen.queryByLabelText('nur Touren mit Verfügbarkeit')).not.toBeInTheDocument()
    rerender(<FilterBar {...props} draft={{ startDate: '2026-07-10', partySize: 2 }} />)
    expect(screen.getByLabelText('nur Touren mit Verfügbarkeit')).toBeInTheDocument()
  })
  it('warns when no hut class is selected', () => {
    render(<FilterBar {...base()} form={{ ...DEFAULT_FORM, allowedOperators: new Set() }} />)
    expect(screen.getByText('Mindestens ein Betreiber und eine Betriebsart müssen ausgewählt sein.')).toBeInTheDocument()
  })
})
