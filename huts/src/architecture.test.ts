import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const SRC = path.dirname(fileURLToPath(import.meta.url))

const LAYER: Record<string, number> = {
  lib: 0, ui: 0, format: 0, availability: 0, tourSearch: 0,
  trip: 1,
  data: 2, search: 2,
  features: 3, adminPage: 3, gpxEditor: 3, plannerPage: 3,
  app: 4,
}

interface Edge { from: string; to: string; spec: string }

function sourceFiles(): string[] {
  return (readdirSync(SRC, { recursive: true }) as string[])
    .map((f) => f.split(path.sep).join('/'))
    .filter((f) => /\.tsx?$/.test(f))
    .filter((f) => !/\.test\.tsx?$/.test(f) && f !== 'vite-env.d.ts')
    .filter((f) => !f.split('/').some((seg) => seg === 'testing' || seg === 'node_modules'))
}

function specifiers(text: string): string[] {
  const out: string[] = []
  const patterns = [/\bimport\s+'([^']+)'/g, /\bfrom\s+'([^']+)'/g, /\bimport\(\s*'([^']+)'\s*\)/g, /new URL\(\s*'([^']+)'\s*,\s*import\.meta\.url/g]
  for (const re of patterns) for (const m of text.matchAll(re)) out.push(m[1])
  return out.filter((s) => s.startsWith('@/') || s.startsWith('.'))
}

function resolve(file: string, spec: string): string {
  return spec.startsWith('@/') ? spec.slice(2) : path.posix.join(path.posix.dirname(file), spec)
}

function topOf(p: string): string {
  return p.split('/')[0]
}

const edges: Edge[] = sourceFiles().flatMap((from) =>
  specifiers(readFileSync(path.join(SRC, from), 'utf8')).map((spec) => ({ from, to: resolve(from, spec), spec })),
)

describe('architecture', () => {
  it('places every source file in a known layer', () => {
    const unknown = sourceFiles().filter((f) => !(topOf(f) in LAYER) || !f.includes('/'))
    expect(unknown, `files outside a known layer:\n${unknown.join('\n')}`).toEqual([])
  })

  it('imports only from the same or a lower layer', () => {
    const bad = edges
      .filter((e) => topOf(e.to) in LAYER && topOf(e.from) in LAYER)
      .filter((e) => LAYER[topOf(e.to)] > LAYER[topOf(e.from)])
      .map((e) => `${e.from} -> ${e.spec}`)
    expect(bad, `upward imports:\n${bad.join('\n')}`).toEqual([])
  })

  it('keeps tourSearch free of trip imports', () => {
    const bad = edges.filter((e) => topOf(e.from) === 'tourSearch' && topOf(e.to) === 'trip').map((e) => `${e.from} -> ${e.spec}`)
    expect(bad, `tourSearch imports trip:\n${bad.join('\n')}`).toEqual([])
  })

  it('imports plannerPage only from plannerPage and app', () => {
    const bad = edges
      .filter((e) => topOf(e.to) === 'plannerPage' && !['plannerPage', 'app'].includes(topOf(e.from)))
      .map((e) => `${e.from} -> ${e.spec}`)
    expect(bad, `plannerPage imported from below:\n${bad.join('\n')}`).toEqual([])
  })
})
