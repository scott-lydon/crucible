// Small presentational primitives shared across routes. Inline styles keyed to
// the Graphite Meridian palette (theme.ts) so the dark design is faithful and
// self-contained — no global CSS beyond the font + base background.

import type { CSSProperties, ReactNode } from "react"
import { C, MONO } from "../theme"

export function Card({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <div
      style={{
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: 9,
        padding: 18,
        ...style,
      }}
    >
      {children}
    </div>
  )
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        fontFamily: MONO,
        fontSize: 11,
        letterSpacing: ".08em",
        color: C.textMut,
        textTransform: "uppercase",
        marginBottom: 12,
      }}
    >
      {children}
    </div>
  )
}

export function Mono({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return <span style={{ fontFamily: MONO, ...style }}>{children}</span>
}

export function Pill({
  children,
  tone = "neutral",
}: {
  children: ReactNode
  tone?: "neutral" | "pass" | "fail" | "warn" | "info"
}) {
  const map = {
    neutral: { bg: C.surface3, fg: C.textMut, bd: C.border },
    pass: { bg: "#16241C", fg: C.success, bd: "#2A4636" },
    fail: { bg: "#2A1614", fg: C.danger, bd: "#4A2420" },
    warn: { bg: C.mockBg, fg: C.mockText, bd: C.mockBorder },
    info: { bg: "#10262C", fg: C.primary, bd: C.primaryDim },
  }[tone]
  return (
    <span
      style={{
        fontFamily: MONO,
        fontSize: 11,
        color: map.fg,
        background: map.bg,
        border: `1px solid ${map.bd}`,
        borderRadius: 5,
        padding: "2px 8px",
        display: "inline-block",
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </span>
  )
}

// A metric tile. Renders the literal "Not yet measured" (never a 0.0) when the
// value is null/undefined — the US-10 honesty invariant.
export function Tile({
  label,
  value,
  sub,
  href,
}: {
  label: string
  value: number | string | null | undefined
  sub?: ReactNode
  href?: string
}) {
  const measured = value !== null && value !== undefined && value !== ""
  return (
    <Card style={{ minWidth: 0 }}>
      <div style={{ fontSize: 12, color: C.textMut, marginBottom: 8 }}>{label}</div>
      {measured ? (
        <div style={{ fontFamily: MONO, fontSize: 26, color: C.textHi, fontWeight: 600 }}>{value}</div>
      ) : (
        <div>
          <div style={{ fontFamily: MONO, fontSize: 15, color: C.textMut }}>Not yet measured</div>
          {href && (
            <a href={href} style={{ fontSize: 12, color: C.primary, textDecoration: "none" }}>
              Launch a run →
            </a>
          )}
        </div>
      )}
      {sub && measured && <div style={{ fontSize: 11, color: C.textMut, marginTop: 8 }}>{sub}</div>}
    </Card>
  )
}

export function Button({
  children,
  onClick,
  disabled,
  type = "button",
  variant = "primary",
}: {
  children: ReactNode
  onClick?: () => void
  disabled?: boolean
  type?: "button" | "submit"
  variant?: "primary" | "ghost"
}) {
  const primary = variant === "primary"
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      style={{
        fontFamily: MONO,
        fontSize: 13,
        fontWeight: 500,
        color: primary ? C.base : C.text,
        background: primary ? C.primary : C.surface,
        border: `1px solid ${primary ? C.primary : C.borderStrong}`,
        borderRadius: 7,
        padding: "9px 16px",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.5 : 1,
      }}
    >
      {children}
    </button>
  )
}
