// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import '@testing-library/jest-dom/vitest'
import Sidebar, { type SidebarTour } from './Sidebar.js'

afterEach(cleanup)

const leg = (n: number, over: Partial<SidebarTour['legs'][number]> = {}) => ({
  leg: n, snapKnown: true, startUnsnapped: false, endUnsnapped: false, longSegment: false, dirty: false, ...over,
})

const tours: SidebarTour[] = [
  { name: 'Kaisertour', discontinuous: true, legs: [
    leg(1),
    leg(2, { startUnsnapped: true, longSegment: true }),
    leg(3, { endUnsnapped: true, dirty: true }),
  ] },
  { name: 'Other', discontinuous: false, legs: [leg(1, { snapKnown: false })] },
]

describe('Sidebar', () => {
  it('renders status badges per leg', () => {
    render(<Sidebar tours={tours} active={null} onSelect={() => {}} />)
    expect(screen.getAllByText('ok')).toHaveLength(1)
    expect(screen.getByText('start unsnapped')).toBeInTheDocument()
    expect(screen.getByText('end unsnapped')).toBeInTheDocument()
    expect(screen.getByText('long segment')).toBeInTheDocument()
    expect(screen.getByText('discontinuous')).toBeInTheDocument()
    expect(screen.getByLabelText('unsaved edits')).toBeInTheDocument()
  })

  it('shows no snap badge when snap status is unknown', () => {
    render(<Sidebar tours={[tours[1]!]} active={null} onSelect={() => {}} />)
    expect(screen.queryByText('ok')).toBeNull()
  })

  it('calls onSelect with tour name and leg number', async () => {
    const onSelect = vi.fn()
    render(<Sidebar tours={tours} active={null} onSelect={onSelect} />)
    await userEvent.click(screen.getByRole('button', { name: /Leg 2/ }))
    expect(onSelect).toHaveBeenCalledWith('Kaisertour', 2)
  })

  it('collapses a tour when its header is clicked', async () => {
    render(<Sidebar tours={tours} active={null} onSelect={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: /Kaisertour/ }))
    expect(screen.queryByRole('button', { name: /Leg 2/ })).toBeNull()
  })
})
