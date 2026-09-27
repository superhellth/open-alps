// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import SidebarHeader from './SidebarHeader.js'

afterEach(cleanup)

describe('SidebarHeader', () => {
  it('shows the saved count in the Meine Touren label', () => {
    render(<SidebarHeader view="discover" savedCount={3} onWordmark={() => {}} onPlanen={() => {}} onMeineTouren={() => {}} />)
    expect(screen.getByText('Meine Touren (3)')).toBeInTheDocument()
  })

  it('marks Planen active for discover and trip, Meine Touren active for saved', () => {
    const { rerender } = render(<SidebarHeader view="discover" savedCount={0} onWordmark={() => {}} onPlanen={() => {}} onMeineTouren={() => {}} />)
    expect(screen.getByText('Planen').getAttribute('aria-current')).toBe('page')
    rerender(<SidebarHeader view="trip" savedCount={0} onWordmark={() => {}} onPlanen={() => {}} onMeineTouren={() => {}} />)
    expect(screen.getByText('Planen').getAttribute('aria-current')).toBe('page')
    rerender(<SidebarHeader view="saved" savedCount={0} onWordmark={() => {}} onPlanen={() => {}} onMeineTouren={() => {}} />)
    expect(screen.getByText('Meine Touren (0)').getAttribute('aria-current')).toBe('page')
  })

  it('calls the right handler for each control', () => {
    const onWordmark = vi.fn(); const onPlanen = vi.fn(); const onMeineTouren = vi.fn()
    render(<SidebarHeader view="discover" savedCount={0} onWordmark={onWordmark} onPlanen={onPlanen} onMeineTouren={onMeineTouren} />)
    fireEvent.click(screen.getByText('Wegweiser'))
    expect(onWordmark).toHaveBeenCalled()
    fireEvent.click(screen.getByText('Planen'))
    expect(onPlanen).toHaveBeenCalled()
    fireEvent.click(screen.getByText('Meine Touren (0)'))
    expect(onMeineTouren).toHaveBeenCalled()
  })
})
