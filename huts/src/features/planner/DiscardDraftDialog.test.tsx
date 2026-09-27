// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import DiscardDraftDialog from './DiscardDraftDialog.js'

afterEach(cleanup)

describe('DiscardDraftDialog', () => {
  it('calls onDiscard when confirmed, onCancel when cancelled', () => {
    const onDiscard = vi.fn()
    const onCancel = vi.fn()
    render(<DiscardDraftDialog open onDiscard={onDiscard} onCancel={onCancel} />)
    fireEvent.click(screen.getByText('Verwerfen'))
    expect(onDiscard).toHaveBeenCalled()
    fireEvent.click(screen.getByText('Abbrechen'))
    expect(onCancel).toHaveBeenCalled()
  })

  it('renders nothing interactable when closed', () => {
    render(<DiscardDraftDialog open={false} onDiscard={() => {}} onCancel={() => {}} />)
    expect(screen.queryByText('Ungespeicherte Tour verwerfen?')).not.toBeInTheDocument()
  })
})
