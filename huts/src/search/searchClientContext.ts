import { createContext, useContext } from 'react'
import type { SearchClient } from './searchClient.js'

export const SearchClientContext = createContext<SearchClient | null>(null)

export function useSearchClient(): SearchClient | null {
  return useContext(SearchClientContext)
}
