export const tokens = {
  paper: '#EDEFE9',
  ink: '#23272B',
  signpost: '#F5B700',
  trailRed: '#C8102E', // medium difficulty only
  alpineBlue: '#1F5FA8', // alpine difficulty only
}

export const SIGNPOST_FONT = '"Barlow Semi Condensed", "Barlow", system-ui, sans-serif'

const kebab = (key: string) => key.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)

/** CSS custom properties for `:root`, generated from `tokens`: `--color-paper`, `--color-ink`, `--color-signpost`, `--color-trail-red`, `--color-alpine-blue`. */
export const tokenCssVariables: Record<string, string> = Object.fromEntries(
  Object.entries(tokens).map(([key, value]) => [`--color-${kebab(key)}`, value]),
)
