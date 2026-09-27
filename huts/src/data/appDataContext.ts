import { createContext, useContext } from 'react'
import type { AppData } from './buildAppData.js'

export type AppDataState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: AppData }

export const AppDataContext = createContext<AppDataState>({ status: 'loading' })

export function useAppData(): AppDataState {
  return useContext(AppDataContext)
}
