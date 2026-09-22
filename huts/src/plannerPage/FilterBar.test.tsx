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
    expect(props.onFormChange).toHaveBeenCalledWith({ allowViaFerrata: true })
  })
  it('warns when no hut class is selected', () => {
    render(<FilterBar {...base()} form={{ ...DEFAULT_FORM, allowedOperators: new Set() }} />)
    expect(screen.getByText('Mindestens ein Betreiber und eine Betriebsart müssen ausgewählt sein.')).toBeInTheDocument()
  })

  it('shows a date range when a date is picked, a day-count stepper otherwise', () => {
    const props = base()
    render(<FilterBar {...props} />)
    expect(screen.getByText('3 Tage')).toBeInTheDocument()
    expect(screen.queryByLabelText('Von')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('Datum wählen'))
    expect(props.onDraftChange).toHaveBeenCalledWith(expect.objectContaining({ startDate: expect.any(String), endDate: expect.any(String) }))
  })

  it('the flexibel chip only affects the undated stepper', () => {
    const props = base()
    render(<FilterBar {...props} />)
    fireEvent.click(screen.getByText('flexibel ±1 Tag'))
    expect(props.onDraftChange).toHaveBeenCalledWith({ flexible: true })
  })

  it('the day and party steppers report draft patches', () => {
    const props = base()
    render(<FilterBar {...props} />)
    fireEvent.click(screen.getAllByText('+', { selector: 'button' })[0])
    expect(props.onDraftChange).toHaveBeenCalledWith({ dayCount: 4 })
  })

  it('the leg-time control is three single-select chips defaulting to 7h', () => {
    const props = base()
    render(<FilterBar {...props} />)
    expect(screen.getByRole('button', { name: 'bis 7 h', pressed: true })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'bis 9 h' }))
    expect(props.onFormChange).toHaveBeenCalledWith({ legTimeCeilingH: 9 })
  })

  it('difficulty options carry a description', () => {
    render(<FilterBar {...base()} />)
    fireEvent.mouseDown(screen.getByLabelText('Schwierigkeit'))
    expect(screen.getByText('breite Wege, kaum Absturzgefahr')).toBeInTheDocument()
  })

  it('Wege & Hütten group summarizes non-default values in its header', () => {
    render(<FilterBar {...base()} form={{ ...DEFAULT_FORM, allowViaFerrata: true }} />)
    expect(screen.getByText('Wege & Hütten · Klettersteige an')).toBeInTheDocument()
  })

  it('the Selbstversorger help popover shows its explanation text', () => {
    render(<FilterBar {...base()} />)
    fireEvent.click(screen.getByLabelText('Was ist eine Selbstversorgerhütte?'))
    expect(screen.getByText('Unbewirtschaftet, meist Selbstverpflegung, ggf. Schlüssel beim Verein holen.')).toBeInTheDocument()
  })

  it('Verfügbarkeit prüfen only shows when a date is set, and reveals the full-tours chip', () => {
    const { rerender } = render(<FilterBar {...base()} />)
    expect(screen.queryByLabelText('Verfügbarkeit prüfen')).not.toBeInTheDocument()
    rerender(<FilterBar {...base()} draft={{ ...DEFAULT_DRAFT, startDate: '2026-07-10', endDate: '2026-07-12' }} form={{ ...DEFAULT_FORM, onlyAvailable: true }} />)
    expect(screen.getByText('auch volle Touren zeigen')).toBeInTheDocument()
  })

  it('Erweitert has only Anstiegslimit and Maximalhöhe, no Wunsch-Tageszahl field', () => {
    render(<FilterBar {...base()} />)
    fireEvent.click(screen.getByText('Erweitert'))
    expect(screen.queryByLabelText(/Wunsch-Tageszahl/)).not.toBeInTheDocument()
    expect(screen.getByLabelText(/Anstiegslimit/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Maximalhöhe/)).toBeInTheDocument()
  })
})
