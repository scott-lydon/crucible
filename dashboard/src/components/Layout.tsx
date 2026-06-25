// App shell: sticky header + the global halt banner (US-13, on EVERY route) +
// the mock-LLM banner (US-15) + primary nav. Matches the Crucible Design System
// header: graphite-navy bar, mono wordmark, restrained steel-cyan brand mark.

import { useEffect, useState, type ReactNode } from "react"
import { Link, useLocation } from "react-router-dom"
import { getHalt, type HaltStatus } from "../api"
import { C, MONO, SANS } from "../theme"

// `exact` nav items light up only on an exact pathname match. `/runs` needs this
// so it doesn't stay active on a `/runs/:id` live-run view (a different page).
const NAV: { to: string; label: string; exact?: boolean }[] = [
  { to: "/", label: "Launcher" },
  { to: "/runs", label: "Runs", exact: true },
  { to: "/metrics", label: "Metrics" },
  { to: "/catalog", label: "Catalog" },
  { to: "/health", label: "Health" },
  { to: "/admin/debug", label: "Debug" },
]

// Read once on mount + when the route changes, so the banner is honest on every
// navigation. The banner suppresses itself if /halt is unreachable (no fake red).
function useHalt(): HaltStatus | null {
  const [halt, setHalt] = useState<HaltStatus | null>(null)
  const loc = useLocation()
  useEffect(() => {
    let live = true
    getHalt()
      .then((h) => live && setHalt(h))
      .catch(() => live && setHalt(null))
    return () => {
      live = false
    }
  }, [loc.pathname])
  return halt
}

export function HaltBanner({ halt }: { halt: HaltStatus | null }) {
  if (!halt || !halt.halted) return null
  const recall = halt.recall == null ? "undefined" : halt.recall.toFixed(2)
  return (
    <div
      role="alert"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        background: C.haltBg,
        color: C.haltText,
        padding: "9px 20px",
        fontSize: 13,
        fontWeight: 500,
        borderBottom: `1px solid ${C.haltBorder}`,
      }}
    >
      <span style={{ width: 8, height: 8, borderRadius: "50%", background: C.haltText, flex: "none" }} />
      <span>
        Certification halted: recall is {recall}, threshold is {halt.threshold.toFixed(2)}.
      </span>
      <Link to="/metrics" style={{ color: C.haltText, marginLeft: "auto", textDecoration: "underline" }}>
        View metrics
      </Link>
    </div>
  )
}

function MockBanner({ on }: { on: boolean }) {
  if (!on) return null
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        background: C.mockBg,
        color: C.mockText,
        padding: "7px 20px",
        fontSize: 12.5,
        fontWeight: 500,
        borderBottom: `1px solid ${C.mockBorder}`,
        fontFamily: MONO,
      }}
    >
      <span style={{ width: 7, height: 7, borderRadius: "50%", background: C.mockText, flex: "none" }} />
      MOCK-LLM MODE — canned responses, not a real run.
    </div>
  )
}

export default function Layout({ children, mock = false }: { children: ReactNode; mock?: boolean }) {
  const halt = useHalt()
  const loc = useLocation()
  return (
    <div style={{ minHeight: "100vh", background: C.base, color: C.text, fontFamily: SANS, fontSize: 14, lineHeight: 1.55 }}>
      <header style={{ position: "sticky", top: 0, zIndex: 40, background: C.base, borderBottom: `1px solid ${C.border}` }}>
        <HaltBanner halt={halt} />
        <MockBanner on={mock} />
        <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "12px 20px" }}>
          <Link to="/" style={{ display: "flex", alignItems: "center", gap: 10, textDecoration: "none" }}>
            <span
              style={{
                width: 22,
                height: 22,
                borderRadius: 5,
                background: C.primary,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: C.base,
                fontWeight: 700,
                fontSize: 13,
                fontFamily: MONO,
              }}
            >
              C
            </span>
            <span style={{ color: C.textHi, fontWeight: 600 }}>Crucible</span>
            <span style={{ fontFamily: MONO, fontSize: 12, color: C.textMut, borderLeft: `1px solid ${C.border}`, paddingLeft: 10 }}>
              operator
            </span>
          </Link>
          <nav style={{ display: "flex", gap: 4, marginLeft: 20 }}>
            {NAV.map((n) => {
              const active =
                n.to === "/" || n.exact ? loc.pathname === n.to : loc.pathname.startsWith(n.to)
              return (
                <Link
                  key={n.to}
                  to={n.to}
                  style={{
                    fontFamily: MONO,
                    fontSize: 12.5,
                    color: active ? C.primary : C.textMut,
                    background: active ? C.surface : "transparent",
                    border: `1px solid ${active ? C.border : "transparent"}`,
                    borderRadius: 6,
                    padding: "6px 11px",
                    textDecoration: "none",
                  }}
                >
                  {n.label}
                </Link>
              )
            })}
          </nav>
        </div>
      </header>
      <main style={{ padding: "24px 20px", maxWidth: 1180, margin: "0 auto" }}>{children}</main>
    </div>
  )
}
