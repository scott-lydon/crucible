// Small presentational primitives shared across routes. Inline styles keyed to
// the Graphite Meridian palette (theme.ts) so the dark design is faithful and
// self-contained — no global CSS beyond the font + base background.

import type { CSSProperties, ReactNode } from "react"
import type { RunSummary } from "../api"
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

// A run-selector dropdown shared by Metrics / BlueReview / Catalog. Populated by
// the caller from getRuns(); selecting a run invokes onChange with its id. The
// caller owns navigation (the routes differ: ?run_id= vs /blue/:id). Honest
// empty-state when no runs exist yet.
export function RunPicker({
  runs,
  value,
  onChange,
  label = "Run",
}: {
  runs: RunSummary[]
  value: string
  onChange: (runId: string) => void
  label?: string
}) {
  const selectStyle: CSSProperties = {
    fontFamily: MONO,
    fontSize: 13,
    color: C.textHi,
    background: C.surface2,
    border: `1px solid ${C.border}`,
    borderRadius: 7,
    padding: "9px 11px",
    minWidth: 280,
  }
  return (
    <label style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12, color: C.textMut }}>
      {label}
      {runs.length === 0 ? (
        <span style={{ fontFamily: MONO, fontSize: 13, color: C.textMut }}>no runs yet — launch one</span>
      ) : (
        <select aria-label="Select run" value={value} onChange={(e) => onChange(e.target.value)} style={selectStyle}>
          {runs.map((r) => (
            <option key={r.run_id} value={r.run_id}>
              {r.run_id.slice(0, 8)} · {r.target} · {r.status}
            </option>
          ))}
        </select>
      )}
    </label>
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
  variant?: "primary" | "ghost" | "danger"
}) {
  // Danger uses the palette's danger hue for destructive actions (Stop run); a
  // tinted surface keeps it legible on the dark theme rather than a solid fill.
  const skin = {
    primary: { fg: C.base, bg: C.primary, bd: C.primary },
    ghost: { fg: C.text, bg: C.surface, bd: C.borderStrong },
    danger: { fg: C.danger, bg: "#2A1614", bd: "#4A2420" },
  }[variant]
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      style={{
        fontFamily: MONO,
        fontSize: 13,
        fontWeight: 500,
        color: skin.fg,
        background: skin.bg,
        border: `1px solid ${skin.bd}`,
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

// Run lifecycle: the statuses past which no more work happens. ``stopped`` joins
// the terminal set so the UI hides the Stop control and renders a terminal pill.
export const TERMINAL_STATUSES = ["complete", "failed", "stopped", "timed out"] as const

export function isTerminalStatus(status: string): boolean {
  return (TERMINAL_STATUSES as readonly string[]).includes(status)
}

// Single source of truth for how a run status maps to a Pill tone, shared by
// RunView and the Runs-list so ``stopped`` reads the same everywhere: a neutral
// "warn" tone, distinct from the green ``complete`` and red ``failed``.
export function statusTone(status: string): "pass" | "fail" | "warn" | "info" {
  if (status === "complete") return "pass"
  if (status === "failed") return "fail"
  if (status === "stopped" || status === "stopping" || status === "timed out") return "warn"
  return "info"
}

// A modal confirmation dialog rendered as a centered overlay. Accessible
// (role="dialog", aria-modal); Escape and backdrop click cancel. Built from the
// theme tokens — no portal/heavy dep. The destructive action only fires when the
// operator clicks Confirm, so the caller's side effect is gated behind consent.
export function ConfirmDialog({
  title,
  body,
  confirmLabel,
  cancelLabel = "Cancel",
  confirmDisabled = false,
  onConfirm,
  onCancel,
}: {
  title: string
  body: ReactNode
  confirmLabel: string
  cancelLabel?: string
  confirmDisabled?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <div
      role="presentation"
      onClick={onCancel}
      onKeyDown={(e) => {
        if (e.key === "Escape") onCancel()
      }}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 100,
        background: "rgba(8,11,15,0.72)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 20,
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        style={{
          background: C.surface,
          border: `1px solid ${C.borderStrong}`,
          borderRadius: 11,
          padding: 22,
          maxWidth: 420,
          width: "100%",
        }}
      >
        <div style={{ color: C.textHi, fontSize: 16, fontWeight: 600, marginBottom: 10 }}>{title}</div>
        <div style={{ color: C.text, fontSize: 13.5, lineHeight: 1.55, marginBottom: 18 }}>{body}</div>
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <Button variant="ghost" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button variant="danger" onClick={onConfirm} disabled={confirmDisabled}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}
