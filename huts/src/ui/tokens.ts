export const tokens = {
  paper: '#EDEFE9',
  ink: '#23272B',
  signpost: '#F5B700',
  trailRed: '#C8102E', // medium difficulty only
  alpineBlue: '#1F5FA8', // alpine difficulty only
  white: '#FFFFFF', // hover faces of boards, dots and bubbles
  hutAv: '#1565c0',
  hutOther: '#6a1b9a',
  hutPartner: '#ef6c00',
}

/** MUI spacing units (1 = 8 px). Each name states the relationship it expresses. */
export const space = {
  inline: 0.5, // icon ↔ label, parts of one chip, stats within one line
  item: 1, // controls in one row, lines within one card or list entry
  row: 1.5, // vertical padding of a list entry
  group: 2, // between groups: filter blocks, list entries without dividers
  section: 3, // between sections of a panel
  inset: 2, // panel edge padding
}

/** Font sizes in rem. */
export const fontSize = { xs: 0.75, sm: 0.875, md: 1, lg: 1.125, xl: 1.25 }
export const rem = (n: number) => `${n}rem`

export const fonts = {
  body: '"Barlow", system-ui, sans-serif',
  signpost: '"Barlow Semi Condensed", "Barlow", system-ui, sans-serif',
}
export const SIGNPOST_FONT = fonts.signpost

export const opacity = {
  dimmed: 0.45,
  hoverTint: 0.05,
  hoverTintStrong: 0.09,
  muted: 0.6,
  shadow: 0.15,
  outline: 0.23,
}

/** Signpost geometry in px, shared by `placeSignposts.ts` (collision widths) and `map.css`. */
export const marker = {
  boardH: 26,
  mastH: 24,
  boardMaxW: 220,
  boardPadNear: 8,
  boardPadFar: 16,
  boardGap: 6,
  arrowW: 10,
  /** Canvas font string; canvas cannot resolve CSS variables, so it is fully expanded. */
  boardFont: `600 ${rem(fontSize.sm)} ${fonts.signpost}`,
}

const kebab = (key: string) => key.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)

const group = <T>(prefix: string, values: Record<string, T>, format: (v: T) => string): [string, string][] =>
  Object.entries(values).map(([key, value]) => [`--${prefix}-${kebab(key)}`, format(value)])

/** CSS custom properties for `:root`: one per token, e.g. `--color-trail-red`, `--space-item`, `--font-size-sm`, `--font-body`, `--opacity-dimmed`, `--marker-board-h`. */
export const tokenCssVariables: Record<string, string> = Object.fromEntries([
  ...group('color', tokens, String),
  ...group('space', space, (u) => `${u * 8}px`),
  ...group('font-size', fontSize, rem),
  ...group('font', fonts, String),
  ...group('opacity', opacity, String),
  ...group('marker', marker, (v) => (typeof v === 'number' ? `${v}px` : v)),
])
