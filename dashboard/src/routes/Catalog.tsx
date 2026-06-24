// US-6: Strategy Catalog. The red catalog is a per-run accumulator of landed
// evasion tactics (which feature moved, in which direction, by which source).
// The backend does not expose a dedicated /catalog endpoint yet, so this page
// reconstructs the catalog from a run's corpus (each corpus row carries the
// tactic the red agent used). Pick a run to populate it; honest empty-state.

import { useEffect, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { getCorpus, type CorpusRow } from "../api"
import Layout from "../components/Layout"
import { Button, Card, Mono, Pill, SectionLabel } from "../components/ui"
import { C, MONO } from "../theme"

type Tactic = { tactic: string; count: number; targets: Set<string> }

export default function Catalog() {
  const [params, setParams] = useSearchParams()
  const [pending, setPending] = useState(params.get("run_id") ?? "")
  const [runId, setRunId] = useState(params.get("run_id") ?? "")
  const [rows, setRows] = useState<CorpusRow[] | null>(null)

  useEffect(() => {
    if (!runId) return
    setRows(null)
    getCorpus(runId)
      .then((c) => setRows(c.rows))
      .catch(() => setRows([]))
  }, [runId])

  const tactics = new Map<string, Tactic>()
  for (const r of rows ?? []) {
    const t = tactics.get(r.tactic) ?? { tactic: r.tactic, count: 0, targets: new Set<string>() }
    t.count += 1
    t.targets.add(r.target_type)
    tactics.set(r.tactic, t)
  }
  const sorted = [...tactics.values()].sort((a, b) => b.count - a.count)

  return (
    <Layout>
      <SectionLabel>Strategy Catalog · US-6</SectionLabel>
      <h1 style={{ color: C.textHi, fontSize: 22, fontWeight: 600, margin: "0 0 6px" }}>Evasion strategy catalog</h1>
      <p style={{ color: C.textMut, fontSize: 13, marginTop: 0 }}>
        The tactics the red agent landed against the target, derived from the run’s seeded-hack corpus.
      </p>

      <Card style={{ marginBottom: 20 }}>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            setRunId(pending)
            setParams(pending ? { run_id: pending } : {})
          }}
          style={{ display: "flex", gap: 10 }}
        >
          <input
            value={pending}
            onChange={(e) => setPending(e.target.value)}
            placeholder="run id"
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
          <Button type="submit">Load catalog</Button>
        </form>
      </Card>

      {!runId && <p style={{ color: C.textMut }}>Enter a run id to load its strategy catalog.</p>}
      {runId && rows && rows.length === 0 && <p style={{ color: C.textMut }}>No landed strategies for this run yet.</p>}

      {sorted.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 14 }}>
          {sorted.map((t) => (
            <Card key={t.tactic}>
              <div style={{ fontFamily: MONO, fontSize: 13, color: C.textHi, marginBottom: 8 }}>{t.tactic}</div>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <Pill tone="info">{t.count}× landed</Pill>
                {[...t.targets].map((tg) => (
                  <Mono key={tg} style={{ fontSize: 11, color: C.textMut }}>
                    {tg}
                  </Mono>
                ))}
              </div>
            </Card>
          ))}
        </div>
      )}
    </Layout>
  )
}
