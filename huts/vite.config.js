import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { gpxEditorPlugin } from './tools/gpxEditorPlugin.ts'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), gpxEditorPlugin(fileURLToPath(new URL('..', import.meta.url)))],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
})
