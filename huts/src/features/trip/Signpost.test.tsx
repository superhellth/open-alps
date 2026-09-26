// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import Signpost from './Signpost.js'

afterEach(cleanup)

describe('Signpost', () => {
  it('shows destination, signpost-style time and ascent/descent', () => {
    render(<Signpost title="Gruttenhütte" timeH={3.5} ascentM={820} descentM={240} />)
    expect(screen.getByText('Gruttenhütte')).toBeInTheDocument()
    expect(screen.getByText('3½ Std')).toBeInTheDocument()
    expect(screen.getByText(/↑ 820 m/)).toBeInTheDocument()
    expect(screen.getByText(/↓ 240 m/)).toBeInTheDocument()
  })
  it('omits the figures when none are given', () => {
    render(<Signpost title="Nur Name" />)
    expect(screen.queryByText(/Std/)).not.toBeInTheDocument()
  })
  it('marks the outline variant and renders children under the plate', () => {
    render(<Signpost title="Alt" variant="outline"><span>Hinweis</span></Signpost>)
    expect(screen.getByText('Alt').closest('[data-variant]')).toHaveAttribute('data-variant', 'outline')
    expect(screen.getByText('Hinweis')).toBeInTheDocument()
  })
  it('renders a subtitle line and accepts a node as title', () => {
    render(<Signpost title={<button>Umbenennen</button>} timeH={2} subtitle="4 Nächte · 58 km" />)
    expect(screen.getByRole('button', { name: 'Umbenennen' })).toBeInTheDocument()
    expect(screen.getByText('4 Nächte · 58 km')).toBeInTheDocument()
  })
})
