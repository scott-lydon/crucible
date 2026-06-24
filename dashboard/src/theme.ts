// Graphite Meridian palette — the canonical tokens from frontend/_palette_notes.md.
// Single source of truth for color in the dashboard. We pin these exact hexes
// because the Claude Design specified them with audited AAA/AA contrast; we do
// NOT invent hexes the design did not give.

export const C = {
  base: "#0E141B",
  surface: "#161E27",
  surface2: "#1D2630",
  surface3: "#25303C",
  border: "#2C3744",
  borderStrong: "#3A4654",

  textHi: "#E8EDF3",
  text: "#B8C2CE",
  textMut: "#7C8896",

  primary: "#4FAAC0",
  primaryDim: "#316E7E",

  success: "#57C08A",
  danger: "#E5736B",
  warning: "#D9A441",

  haltBg: "#5E1A1A",
  haltBorder: "#7A2323",
  haltText: "#FFC9C4",

  mockBg: "#3A3413",
  mockBorder: "#5A4F1E",
  mockText: "#E8C84A",
} as const

export const SANS = "'IBM Plex Sans',-apple-system,BlinkMacSystemFont,sans-serif"
export const MONO = "'IBM Plex Mono',ui-monospace,SFMono-Regular,monospace"
