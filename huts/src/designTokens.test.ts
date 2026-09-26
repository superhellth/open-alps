import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const SRC = path.dirname(fileURLToPath(import.meta.url))

/** Files not yet migrated; each migration task removes its files. Empty at the end. */
const PENDING: string[] = [
  'data/hutClass.ts',
  'features/discover/FilterBar.styles.ts',
  'features/discover/FilterBar.tsx',
  'features/discover/RangeCalendar.styles.ts',
  'features/discover/RangeCalendar.tsx',
  'features/discover/ResultsList.styles.ts',
  'features/discover/ResultsList.tsx',
  'features/map/DiscoverLayer.tsx',
  'features/map/HeightProfile.tsx',
  'features/map/TripMapLayers.styles.ts',
  'features/map/map.css',
  'features/map/placeSignposts.ts',
  'features/saved/SavedTripsList.styles.ts',
  'features/saved/SavedTripsList.tsx',
  'features/trip/AvailabilityMark.tsx',
  'features/trip/Signpost.styles.ts',
  'features/trip/Signpost.tsx',
  'features/trip/StageList.styles.ts',
  'features/trip/StageList.tsx',
  'features/trip/StartDateStrip.tsx',
  'features/trip/TripDateSummary.tsx',
  'features/trip/TripEditor.styles.ts',
  'features/trip/TripEditor.tsx',
  'features/trip/TripPanel.styles.ts',
  'features/trip/TripPanel.tsx',
]

const EXCLUDED_FILES = new Set(['ui/tokens.ts', 'ui/theme.ts', 'vite-env.d.ts'])
const EXCLUDED_DIRS = new Set(['adminPage', 'gpxEditor', 'testing', 'node_modules'])

function sourceFiles(): string[] {
  return (readdirSync(SRC, { recursive: true }) as string[])
    .map((f) => f.split(path.sep).join('/'))
    .filter((f) => /\.(tsx?|css)$/.test(f))
    .filter((f) => !/\.test\.tsx?$/.test(f) && !EXCLUDED_FILES.has(f))
    .filter((f) => !f.split('/').some((seg) => EXCLUDED_DIRS.has(seg)))
}

interface Line { no: number; code: string; comment: string }

// Splits each line into code and comment parts: line comments, block comments and multi-line blocks.
export function splitLines(text: string, css: boolean): Line[] {
  const out: Line[] = []
  let inBlock = false
  text.split('\n').forEach((raw, i) => {
    let code = ''
    let comment = ''
    let rest = raw
    while (rest.length > 0) {
      if (inBlock) {
        const end = rest.indexOf('*/')
        if (end < 0) { comment += rest; rest = '' } else { comment += rest.slice(0, end); rest = rest.slice(end + 2); inBlock = false }
        continue
      }
      const block = rest.indexOf('/*')
      const lineComment = css ? -1 : rest.search(/(^|\s)\/\//)
      if (lineComment >= 0 && (block < 0 || lineComment < block)) {
        code += rest.slice(0, lineComment)
        comment += rest.slice(lineComment)
        rest = ''
      } else if (block >= 0) {
        code += rest.slice(0, block)
        rest = rest.slice(block + 2)
        inBlock = true
      } else { code += rest; rest = '' }
    }
    out.push({ no: i + 1, code, comment })
  })
  return out
}

const NONZERO_NUM = String.raw`-?(?:[1-9]\d*(?:\.\d+)?|0?\.\d*[1-9]\d*)`
const CSS_LITERAL = /(?<![\d.])(?:[1-9]\d*(?:\.\d+)?|0?\.\d*[1-9]\d*)(?:px|rem)\b/

interface Rule { name: string; test: (code: string, css: boolean) => boolean }

const RULES: Rule[] = [
  {
    name: 'spacing-literal',
    test: (code, css) => {
      if (css) return /(?:^|[\s;{])(?:padding[\w-]*|gap|row-gap|column-gap)\s*:\s*[^;}]*/.test(code) && CSS_LITERAL.test(code.replace(/^.*?(?:padding[\w-]*|gap|row-gap|column-gap)\s*:/, ''))
      const key = String.raw`\b(?:p|px|py|pt|pb|pl|pr|gap|rowGap|columnGap|padding\w*)\s*:\s*`
      return new RegExp(`${key}(?:${NONZERO_NUM}\\b|['"\`][^'"\`]*(?:${CSS_LITERAL.source})[^'"\`]*['"\`])`).test(code)
    },
  },
  {
    name: 'margin',
    test: (code, css) => {
      const re = css ? /(?:^|[\s;{])margin[\w-]*\s*:\s*([^;}]+)/ : /\b(?:m|mx|my|mt|mb|ml|mr|margin\w*)\s*:\s*([^,}]+)/
      const m = re.exec(code)
      return m !== null && !['0', "'0'", '"0"'].includes(m[1].trim())
    },
  },
  {
    name: 'font-size-literal',
    test: (code, css) =>
      css
        ? /font-size\s*:\s*[^;}]*\d/.test(code) || /(?:^|[\s;{])font\s*:[^;}]*\d(?:\.\d+)?(?:rem|px|em)\b/.test(code)
        : /\bfontSize\s*:\s*['"`]?-?\d/.test(code),
  },
  {
    name: 'color-literal',
    test: (code, css) =>
      /#[0-9a-fA-F]{3,8}\b/.test(code) || /\brgba?\(/.test(code) || (css ? /:\s*(?:white|black)\b/.test(code) : /['"`]\s*(?:white|black)\s*['"`]/.test(code)),
  },
  { name: 'opacity-literal', test: (code) => /\balpha\([^,()]+(?:\([^)]*\))?,\s*-?\.?\d/.test(code) },
  { name: 'font-family-literal', test: (code) => /Barlow/.test(code) },
]

const EXEMPT = /design-exempt:(.*?)(?:\*\/|$)/

interface Failure { file: string; no: number; rule: string; text: string }

export function scan(file: string, text: string): Failure[] {
  const css = file.endsWith('.css')
  const failures: Failure[] = []
  for (const { no, code, comment } of splitLines(text, css)) {
    const exempt = EXEMPT.exec(comment)
    if (exempt) {
      if (exempt[1].trim() === '') failures.push({ file, no, rule: 'empty-exempt-reason', text: comment.trim() })
      continue
    }
    for (const rule of RULES) if (rule.test(code, css)) failures.push({ file, no, rule: rule.name, text: code.trim() })
  }
  return failures
}

const format = (f: Failure) => `${f.file}:${f.no}  ${f.rule}  ${f.text}`

describe('design tokens', () => {
  const files = sourceFiles()
  const failuresByFile = new Map(files.map((f) => [f, scan(f, readFileSync(path.join(SRC, f), 'utf8'))]))

  it('uses tokens instead of spacing, font size, color, opacity and font-family literals', () => {
    const bad = files.filter((f) => !PENDING.includes(f)).flatMap((f) => failuresByFile.get(f) ?? [])
    expect(bad.map(format), 'literals bypassing ui/tokens.ts (or add `// design-exempt: <reason>`)').toEqual([])
  })

  it('PENDING lists only files that still have violations', () => {
    const stale = PENDING.filter((f) => (failuresByFile.get(f) ?? []).length === 0)
    expect(stale, 'remove migrated files from PENDING').toEqual([])
  })
})

describe('design token scanner', () => {
  const ts = (line: string) => scan('x.tsx', line).map((f) => f.rule)
  const css = (line: string) => scan('x.css', line).map((f) => f.rule)

  it('flags spacing literals, allows zero and tokens', () => {
    expect(ts('sx={{ p: 2, gap: 0.5 }}')).toEqual(['spacing-literal'])
    expect(ts("padding: '0 4px'")).toEqual(['spacing-literal'])
    expect(ts('sx={{ p: 0, gap: space.item }}')).toEqual([])
    expect(ts('map.flyToBounds(b, { padding: [40, 40] })')).toEqual([])
    expect(css('padding: 3px 14px;')).toEqual(['spacing-literal'])
    expect(css('padding: 0; gap: var(--space-item);')).toEqual([])
  })
  it('flags margins other than 0', () => {
    expect(ts('sx={{ mt: 0.5 }}')).toEqual(['margin'])
    expect(ts("'& .x': { margin: '4px 0' }")).toEqual(['margin'])
    expect(ts('sx={{ m: 0 }}')).toEqual([])
    expect(css('margin: 0;')).toEqual([])
    expect(css('margin: 4px 0;')).toEqual(['margin'])
  })
  it('flags font size literals', () => {
    expect(ts("fontSize: '0.85rem'")).toEqual(['font-size-literal'])
    expect(ts('sx={{ fontSize: 14 }}')).toEqual(['font-size-literal'])
    expect(ts('fontSize: rem(fontSize.sm)')).toEqual([])
    expect(ts('<text fontSize="9">')).toEqual([])
    expect(css('font: 600 0.8rem/1 x;')).toEqual(['font-size-literal'])
    expect(css('font: 600 var(--font-size-sm)/1 var(--font-signpost);')).toEqual([])
  })
  it('flags color, opacity and font-family literals', () => {
    expect(ts("background: '#fff'")).toEqual(['color-literal'])
    expect(css('background: #fff;')).toEqual(['color-literal'])
    expect(css('background: var(--color-white);')).toEqual([])
    expect(ts("alpha('#000', 0.15)")).toEqual(['color-literal', 'opacity-literal'])
    expect(ts('alpha(tokens.ink, opacity.shadow)')).toEqual([])
    expect(ts("const f = '\"Barlow\"'")).toEqual(['font-family-literal'])
  })
  it('ignores comments but honours design-exempt markers', () => {
    expect(ts('// was #1b5e20 and p: 2')).toEqual([])
    expect(css('/* p: 2; padding: 8px */')).toEqual([])
    expect(ts('sx={{ mt: 1 }} // design-exempt: pushes the nav right')).toEqual([])
    expect(css('padding: 3px; /* design-exempt: arrow tip */')).toEqual([])
    expect(ts('sx={{ mt: 1 }} // design-exempt:')).toEqual(['empty-exempt-reason'])
  })
  it('skips multi-line block comments', () => {
    expect(scan('x.ts', '/**\n * padding: 8px #fff\n */\nconst a = 1').length).toBe(0)
  })
})
