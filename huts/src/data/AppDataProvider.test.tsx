// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { AppDataProvider, useAppData } from './AppDataProvider.js'
import type { AppData } from './buildAppData.js'

afterEach(cleanup)

function Probe() {
  const state = useAppData()
  return <div>{state.status === 'ready' ? `ready:${state.data.hutNameById.size}` : state.status === 'error' ? `error:${state.message}` : 'loading'}</div>
}

describe('AppDataProvider', () => {
  it('shows loading, then the loaded data', async () => {
    render(<AppDataProvider load={() => Promise.resolve({ hutNameById: new Map([[0, 'A']]) } as unknown as AppData)}><Probe /></AppDataProvider>)
    expect(screen.getByText('loading')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('ready:1')).toBeInTheDocument())
  })
  it('surfaces a load failure', async () => {
    render(<AppDataProvider load={() => Promise.reject(new Error('kaputt'))}><Probe /></AppDataProvider>)
    await waitFor(() => expect(screen.getByText('error:kaputt')).toBeInTheDocument())
  })
})
