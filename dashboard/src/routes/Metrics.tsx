// US-10 / US-14: Honest Dashboard. Five headline tiles + the black-box vs
// white-box catch-rate pair + the gap tile. Metrics are per-run in the API, so
// the operator pastes/loads a run id (or arrives via ?run_id=). EVERY tile with
// no contributing data renders the literal "Not yet measured" with a Launcher
// link — never a fabricated 0.0.

import { useEffect, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { getCorpus, getMetrics, getRuns, isNotMeasured, type Metrics, type RunSummary } from "../api"
import Layout from "../components/Layout"
import { Button, Card, Mono, RunPicker, SectionLabel, Tile } from "../components/ui"
import { C, MONO } from "../theme"

function pct(v: number | null | undefined): string | null {
  return v == null ? null : `${(v * 100).toFixed(0)}%`
}

export default function MetricsView() {
  const [params, setParams] = useSearchParams()
  const runId = params.get("run_id") ?? ""
  const [pending, setPending] = useState(runId)
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [corpusCount, setCorpusCount] = useState<number | null>(null)
  const [loaded, setLoaded] = useState(false)

  // Load the recent-runs index for the picker and DEFAULT to the newest run when
  // the URL carries none — so the operator lands on the latest run's metrics.
  useEffect(() => {
    getRuns()
      .then((rs) => {
        setRuns(rs)
        if (!runId && rs.length > 0) setParams({ run_id: rs[0].run_id }, { replace: true })
      })
      .catch(() => setRuns([]))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Keep the free-text box in sync when the run changes via the picker.
  useEffect(() => {
    setPending(runId)
  }, [runId])

  useEffect(() => {
    if (!runId) return
    setLoaded(false)
    getMetrics(runId)
      .then(setMetrics)
      .catch(() => setMetrics({ status: "Not yet measured" }))
      .finally(() => setLoaded(true))
    getCorpus(runId)
      .then((c) => setCorpusCount(c.count))
      .catch(() => setCorpusCount(null))
  }, [runId])

  const measured = metrics && !isNotMeasured(metrics)
  const wb = metrics?.white_box ?? null

  // Tile derivations from the documented metrics shape. Anything the API does not
  // (yet) expose stays null => "Not yet measured", never a fake value.
  const lastRound = measured ? metrics.per_round[metrics.per_round.length - 1] : undefined
  const undetected = lastRound?.detection_rate == null ? null : pct(1 - lastRound.detection_rate)
  const gap = measured && metrics.gap != null ? metrics.gap.toFixed(2) : null
  const corpusRecall = measured ? pct(lastRound?.detection_rate ?? null) : null
  // Real cost tile from the /metrics payload. Null (no caught hacks / no recorded
  // calls) renders "Not yet measured", never a fabricated 0.0.
  const dollarsPerHack =
    measured && metrics.dollars_per_caught_hack != null ? `$${metrics.dollars_per_caught_hack.toFixed(2)}` : null
  // Honestly unmeasured: the API returns human_minutes_per_1k_outputs = null
  // (no human-review signal exists), so the tile stays "Not yet measured".
  const minutesPerK: string | null = null

  return (
    <Layout>
      <SectionLabel>Honest Dashboard · US-10</SectionLabel>
      <h1 style={{ color: C.textHi, fontSize: 22, fontWeight: 600, margin: "0 0 6px" }}>Metrics</h1>
      <p style={{ color: C.textMut, fontSize: 13, marginTop: 0 }}>
        Headline numbers are measured from a real run. Empty tiles read “Not yet measured”, never 0.0.
      </p>

      <Card style={{ marginBottom: 20 }}>
        <div style={{ marginBottom: 14 }}>
          <RunPicker runs={runs} value={runId} onChange={(id) => setParams({ run_id: id })} />
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            setParams(pending ? { run_id: pending } : {})
          }}
          style={{ display: "flex", gap: 10, alignItems: "center" }}
        >
          <input
            value={pending}
            onChange={(e) => setPending(e.target.value)}
            placeholder="or paste a run id"
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
          <Button type="submit">Load metrics</Button>
        </form>
      </Card>

      {!runId && <p style={{ color: C.textMut }}>Select or enter a run id to load its measured metrics.</p>}

      {runId && (
        <>
          <SectionLabel>Five headline tiles</SectionLabel>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
              gap: 14,
              marginBottom: 24,
            }}
          >
            <Tile label="Undetected-hack rate" value={loaded ? undetected : null} href="/" />
            <Tile label="Validation-vs-held-out gap" value={loaded ? gap : null} href="/" />
            <Tile label="Recall on seeded corpus" value={loaded ? corpusRecall : null} href="/" />
            <Tile label="Dollars per caught hack" value={dollarsPerHack} href="/" />
            <Tile label="Human-minutes / 1k outputs" value={minutesPerK} href="/" />
          </div>

          <SectionLabel>Black-box vs white-box catch rate · US-14</SectionLabel>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
              gap: 14,
            }}
          >
            <Tile label="Black-box catch rate" value={loaded ? pct(wb?.black_box_catch_rate) : null} href="/" />
            <Tile label="White-box catch rate" value={loaded ? pct(wb?.white_box_catch_rate) : null} href="/" />
            <Tile
              label="White-box gap (b−w)"
              value={loaded && wb?.white_box_gap != null ? wb.white_box_gap.toFixed(2) : null}
              href="/"
            />
          </div>

          {corpusCount != null && (
            <p style={{ color: C.textMut, fontSize: 12, marginTop: 18 }}>
              Seeded corpus for this run: <Mono>{corpusCount}</Mono> successful evasions.
            </p>
          )}
        </>
      )}
    </Layout>
  )
}
