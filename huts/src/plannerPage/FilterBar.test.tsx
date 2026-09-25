// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import FilterBar from './FilterBar.js'
import { DEFAULT_FORM } from '@/features/discover/formState.js'
import { DEFAULT_DRAFT } from '@/features/discover/plannerState.js'

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
    render(<FilterBar {...base()} form={{ ...DEFAULT_FORM, allowedHutClasses: new Set() }} />)
    expect(screen.getByText('Mindestens eine Hüttenart muss ausgewählt sein.')).toBeInTheDocument()
  })

  it('turning an operator off drops both its serviced and self-catered huts', () => {
    const props = base()
    render(<FilterBar {...props} />)
    fireEvent.click(screen.getByLabelText('Alpenverein'))
    expect(props.onFormChange).toHaveBeenCalledWith({ allowedHutClasses: new Set(['sonstige:serviced']) })
  })

  it('including self-catered huts adds the self-catered class for every currently enabled operator', () => {
    const props = base()
    render(<FilterBar {...props} />)
    fireEvent.click(screen.getByLabelText('auch Selbstversorgerhütten einschließen'))
    expect(props.onFormChange).toHaveBeenCalledWith({
      allowedHutClasses: new Set(['av:serviced', 'sonstige:serviced', 'av:self', 'sonstige:self']),
    })
  })

  it('re-enabling an operator while self-catered huts are included brings its self-catered class back too', () => {
    const props = base()
    render(<FilterBar {...props} form={{
      ...DEFAULT_FORM, allowedHutClasses: new Set(['sonstige:serviced', 'sonstige:self']),
    }} />)
    fireEvent.click(screen.getByLabelText('Alpenverein'))
    expect(props.onFormChange).toHaveBeenCalledWith({
      allowedHutClasses: new Set(['sonstige:serviced', 'sonstige:self', 'av:serviced', 'av:self']),
    })
  })

  it('always shows a collapsed date-range summary, no undated option, expanding to the calendar on click', () => {
    render(<FilterBar {...base()} />)
    expect(screen.queryByLabelText('Vorheriger Monat')).not.toBeInTheDocument()
    expect(screen.queryByText('ohne Datum')).not.toBeInTheDocument()
    expect(screen.queryByText('Datum wählen')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText(/–/))
    expect(screen.getByLabelText('Vorheriger Monat')).toBeInTheDocument()
  })

  it('the party stepper reports draft patches', () => {
    const props = base()
    render(<FilterBar {...props} />)
    fireEvent.click(screen.getByText('+', { selector: 'button' }))
    expect(props.onDraftChange).toHaveBeenCalledWith({ partySize: 2 })
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

  it('Erweitert group summarizes non-default values in its header', () => {
    render(<FilterBar {...base()} form={{ ...DEFAULT_FORM, allowViaFerrata: true }} />)
    expect(screen.getByText('Erweitert · Klettersteige an')).toBeInTheDocument()
  })

  it('the Hüttenarten help tooltip shows its explanation text on hover', async () => {
    render(<FilterBar {...base()} />)
    fireEvent.click(screen.getByText('Erweitert'))
    fireEvent.mouseOver(screen.getByLabelText('Was bedeuten die Hüttenarten?'))
    expect(await screen.findByText(/unbewirtschaftet, meist Selbstverpflegung/)).toBeInTheDocument()
  })

  it('Verfügbarkeit prüfen is unchecked by default', () => {
    render(<FilterBar {...base()} />)
    expect(screen.getByLabelText('Verfügbarkeit prüfen')).not.toBeChecked()
  })

  it('Erweitert has only Anstiegslimit and Maximalhöhe, no Wunsch-Tageszahl field', () => {
    render(<FilterBar {...base()} />)
    fireEvent.click(screen.getByText('Erweitert'))
    expect(screen.queryByLabelText(/Wunsch-Tageszahl/)).not.toBeInTheDocument()
    expect(screen.getByLabelText(/Anstiegslimit/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Maximalhöhe/)).toBeInTheDocument()
  })
})
