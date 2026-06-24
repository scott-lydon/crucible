// US-6: Strategy Catalog. Institutional memory across runs — one row per
// distinct (tactic, target_type) the red agent ever landed, with the run it was
// first discovered in, how many times it has been reused, and the average
// dollars-to-succeed. Sourced from the real persisted catalog (GET /catalog),
// NOT reconstructed from any single run's corpus. Honest empty-state.

import { useEffect, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { getCatalog, type CatalogRow } from "../api"
import Layout from "../components/Layout"
import { Button, Card, Mono, Pill, SectionLabel } from "../components/ui"
import { C, MONO } from "../theme"

function dollars(v: number | null): string {
  return v == null ? "—" : `$${v.toFixed(2)}`
}

export default function Catalog() {
  const [params, setParams] = useSearchParams()
  const [pending, setPending] = useState(params.get("target_type") ?? "")
  const [targetType, setTargetType] = useState(params.get("target_type") ?? "")
  const [rows, setRows] = useState<CatalogRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setRows(null)
    setError(null)
    getCatalog(targetType || undefined)
      .then((c) => setRows(c.rows))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load catalog"))
  }, [targetType])

  return (
    <Layout>
      <SectionLabel>Strategy Catalog · US-6</SectionLabel>
      <h1 style={{ color: C.textHi, fontSize: 22, fontWeight: 600, margin: "0 0 6px" }}>Evasion strategy catalog</h1>
      <p style={{ color: C.textMut, fontSize: 13, marginTop: 0 }}>
        Cross-run institutional memory: every tactic the red agent has ever landed, with its reuse count and average
        dollars-to-succeed.
      </p>

      <Card style={{ marginBottom: 20 }}>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            setTargetType(pending)
            setParams(pending ? { target_type: pending } : {})
          }}
          style={{ display: "flex", gap: 10 }}
        >
          <input
            value={pending}
            onChange={(e) => setPending(e.target.value)}
            placeholder="filter by target_type (optional)"
            style={{
              flex: 1,
              fontFamily: MONO,
              fontSize: 13,
              color: C.textHi,
              background: C.surface2,
              border: `1px solid ${C.border}`,
              borderRadius: 7,
              padding: "9px 11px",
            }}
          />
          <Button type="submit">Apply filter</Button>
        </form>
      </Card>

      {error && (
        <Card style={{ borderColor: C.danger }}>
          <span style={{ color: C.danger }}>{error}</span>
        </Card>
      )}
      {!error && rows == null && <p style={{ color: C.textMut }}>Loading catalog…</p>}
      {!error && rows && rows.length === 0 && (
        <p style={{ color: C.textMut }}>No strategies in the catalog yet. Run a red+blue arc to populate it.</p>
      )}

      {rows && rows.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 14 }}>
          {rows.map((r) => (
            <Card key={`${r.tactic}:${r.target_type}`}>
              <div style={{ fontFamily: MONO, fontSize: 13, color: C.textHi, marginBottom: 8 }}>{r.tactic}</div>
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 10 }}>
                <Pill tone="info">{r.reuse_count}× reused</Pill>
                <Mono style={{ fontSize: 11, color: C.textMut }}>{r.target_type}</Mono>
              </div>
              <div style={{ fontSize: 12, color: C.textMut }}>
                avg cost to succeed <Mono style={{ color: r.avg_dollars_to_succeed == null ? C.textMut : C.text }}>{dollars(r.avg_dollars_to_succeed)}</Mono>
              </div>
              <div style={{ fontSize: 11, color: C.textMut, marginTop: 6 }}>
                first discovered in run <Mono>{r.first_discovered_run.slice(0, 8)}</Mono>
              </div>
            </Card>
          ))}
        </div>
      )}
    </Layout>
  )
}
