// US-7: Blue Patch Review. The blue arc engineers new detector features in a
// sandbox and retrains; this page shows the engineered features + the
// before→after recovery on the holdout, plus the proposer's rationale and the
// iteration trail. The route is /blue/:patchId where patchId is the run id whose
// blue round we render.

import { useEffect, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { getBlue, getRuns, HttpError, type BlueRound, type RunSummary } from "../api"
import Layout from "../components/Layout"
import { Card, Mono, Pill, RunPicker, SectionLabel } from "../components/ui"
import { C, MONO } from "../theme"

function pct(v: number | null | undefined): string {
  return v == null ? "—" : `${(v * 100).toFixed(1)}%`
}

export default function BlueReview() {
  const { patchId } = useParams<{ patchId: string }>()
  const navigate = useNavigate()
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [blue, setBlue] = useState<BlueRound | null>(null)
  const [missing, setMissing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Load the recent-runs index for the picker and DEFAULT to the newest run when
  // the URL carries none (route reached as bare /blue, no :patchId).
  useEffect(() => {
    getRuns()
      .then((rs) => {
        setRuns(rs)
        if (!patchId && rs.length > 0) navigate(`/blue/${rs[0].run_id}`, { replace: true })
      })
      .catch(() => setRuns([]))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!patchId) return
    setBlue(null)
    setMissing(false)
    setError(null)
    getBlue(patchId)
      .then(setBlue)
      .catch((e) => {
        if (e instanceof HttpError && e.status === 404) setMissing(true)
        else setError(e instanceof Error ? e.message : "Failed to load")
      })
  }, [patchId])

  return (
    <Layout>
      <SectionLabel>Blue Patch Review · US-7</SectionLabel>
      <h1 style={{ color: C.textHi, fontSize: 20, fontWeight: 600, margin: "0 0 16px" }}>
        Blue patch <Mono style={{ color: C.primary }}>{patchId}</Mono>
      </h1>

      <Card style={{ marginBottom: 16 }}>
        <RunPicker runs={runs} value={patchId ?? ""} onChange={(id) => navigate(`/blue/${id}`)} />
      </Card>

      {missing && <p style={{ color: C.textMut }}>No blue recovery round ran for this run.</p>}
      {error && <Card style={{ borderColor: C.danger }}><span style={{ color: C.danger }}>{error}</span></Card>}
      {!blue && !missing && !error && <p style={{ color: C.textMut }}>Loading…</p>}

      {blue && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14, marginBottom: 16 }}>
            <Card>
              <div style={{ fontSize: 12, color: C.textMut, marginBottom: 8 }}>Detection before</div>
              <div style={{ fontFamily: MONO, fontSize: 24, color: C.textHi }}>{pct(blue.detection_before)}</div>
            </Card>
            <Card>
              <div style={{ fontSize: 12, color: C.textMut, marginBottom: 8 }}>Detection after</div>
              <div style={{ fontFamily: MONO, fontSize: 24, color: C.success }}>{pct(blue.detection_after)}</div>
            </Card>
            <Card>
              <div style={{ fontSize: 12, color: C.textMut, marginBottom: 8 }}>Recovered?</div>
              <Pill tone={blue.recovered ? "pass" : "fail"}>{blue.recovered ? "recovered" : "not recovered"}</Pill>
              {blue.n_holdout != null && (
                <div style={{ fontSize: 11, color: C.textMut, marginTop: 8 }}>n_holdout = {blue.n_holdout}</div>
              )}
            </Card>
          </div>

          <Card style={{ marginBottom: 16 }}>
            <SectionLabel>Engineered features</SectionLabel>
            {blue.features_added && blue.features_added.length > 0 ? (
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {blue.features_added.map((f) => (
                  <Pill key={f} tone="info">{f}</Pill>
                ))}
              </div>
            ) : (
              <p style={{ color: C.textMut, fontSize: 13, margin: 0 }}>No features recorded.</p>
            )}
            {blue.new_model_ref && (
              <div style={{ fontSize: 11, color: C.textMut, marginTop: 10 }}>
                new model ref <Mono>{blue.new_model_ref}</Mono>
              </div>
            )}
          </Card>

          <Card style={{ marginBottom: 16 }}>
            <SectionLabel>Proposer rationale</SectionLabel>
            <p style={{ fontFamily: MONO, fontSize: 13, color: blue.proposer_rationale ? C.text : C.textMut, lineHeight: 1.5, margin: 0 }}>
              {blue.proposer_rationale ?? "(no rationale recorded)"}
            </p>
          </Card>

          {blue.iteration_trail != null && (
            <Card>
              <SectionLabel>Iteration trail</SectionLabel>
              <pre
                style={{
                  fontFamily: MONO,
                  fontSize: 12,
                  color: C.text,
                  background: C.surface2,
                  border: `1px solid ${C.border}`,
                  borderRadius: 7,
                  padding: 12,
                  overflowX: "auto",
                  margin: 0,
                }}
              >
                {JSON.stringify(blue.iteration_trail, null, 2)}
              </pre>
            </Card>
          )}
        </>
      )}
    </Layout>
  )
}
