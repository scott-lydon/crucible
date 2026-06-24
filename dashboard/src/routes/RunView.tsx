// US-2: Live Run View. SSE-wired — the ASR chart appends a point on every
// `attack` event, the detection chart on every `verdict` event, and the trace
// pane streams the red agent's rationale from `trace` events (rendered
// gracefully when rationale is null). The headline of slice-15 is that the ASR
// chart updates live as attack events arrive.

import { useEffect, useRef, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import {
  getVerdicts,
  subscribeRun,
  type AttackEvent,
  type CompleteEvent,
  type TraceEvent,
  type VerdictEvent,
  type VerdictSummary,
} from "../api"
import Layout from "../components/Layout"
import { Card, Mono, Pill, SectionLabel } from "../components/ui"
import { C, MONO } from "../theme"

type AsrPoint = { n: number; asr: number | null }
type DetPoint = { n: number; detection: number | null }
type TraceLine = { attack_id: string; rationale: string | null }

const axis = { stroke: C.border, tick: { fill: C.textMut, fontSize: 11, fontFamily: MONO } }

export default function RunView() {
  const { id } = useParams<{ id: string }>()
  const [asr, setAsr] = useState<AsrPoint[]>([])
  const [det, setDet] = useState<DetPoint[]>([])
  const [traces, setTraces] = useState<TraceLine[]>([])
  const [status, setStatus] = useState<string>("running")
  const [verdicts, setVerdicts] = useState<VerdictSummary[]>([])
  const nAttack = useRef(0)
  const nVerdict = useRef(0)

  useEffect(() => {
    if (!id) return
    const dispose = subscribeRun(id, {
      onAttack: (e: AttackEvent) => {
        nAttack.current += 1
        setAsr((prev) => [...prev, { n: nAttack.current, asr: e.asr_so_far }])
      },
      onTrace: (e: TraceEvent) => {
        setTraces((prev) => [{ attack_id: e.attack_id, rationale: e.rationale }, ...prev].slice(0, 50))
      },
      onVerdict: (e: VerdictEvent) => {
        nVerdict.current += 1
        setDet((prev) => [...prev, { n: nVerdict.current, detection: e.detection_rate_so_far }])
      },
      onComplete: (e: CompleteEvent) => setStatus(e.timed_out ? "timed out" : e.status),
    })
    return dispose
  }, [id])

  // Verdict table is a one-shot fetch (the persisted summary), refreshed when the
  // run completes so the operator can drill in (US-3).
  useEffect(() => {
    if (!id) return
    getVerdicts(id).then(setVerdicts).catch(() => setVerdicts([]))
  }, [id, status])

  return (
    <Layout>
      <SectionLabel>Live Run View · US-2</SectionLabel>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 20 }}>
        <h1 style={{ color: C.textHi, fontSize: 20, fontWeight: 600, margin: 0 }}>
          Run <Mono style={{ color: C.primary }}>{id}</Mono>
        </h1>
        <Pill tone={status === "complete" ? "pass" : status === "failed" ? "fail" : "info"}>{status}</Pill>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
        <Card>
          <SectionLabel>Attack-success rate (live)</SectionLabel>
          <div data-testid="asr-chart" style={{ height: 240 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={asr}>
                <CartesianGrid stroke={C.border} strokeDasharray="3 3" />
                <XAxis dataKey="n" stroke={axis.stroke} tick={axis.tick} />
                <YAxis domain={[0, 1]} stroke={axis.stroke} tick={axis.tick} />
                <Tooltip contentStyle={{ background: C.surface2, border: `1px solid ${C.border}`, fontFamily: MONO }} />
                <Line type="monotone" dataKey="asr" stroke={C.warning} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div style={{ fontSize: 11, color: C.textMut, marginTop: 6 }}>
            {asr.length} attack event{asr.length === 1 ? "" : "s"} streamed
          </div>
        </Card>
        <Card>
          <SectionLabel>Detection rate (live)</SectionLabel>
          <div data-testid="detection-chart" style={{ height: 240 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={det}>
                <CartesianGrid stroke={C.border} strokeDasharray="3 3" />
                <XAxis dataKey="n" stroke={axis.stroke} tick={axis.tick} />
                <YAxis domain={[0, 1]} stroke={axis.stroke} tick={axis.tick} />
                <Tooltip contentStyle={{ background: C.surface2, border: `1px solid ${C.border}`, fontFamily: MONO }} />
                <Line type="monotone" dataKey="detection" stroke={C.primary} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div style={{ fontSize: 11, color: C.textMut, marginTop: 6 }}>
            {det.length} verdict event{det.length === 1 ? "" : "s"} streamed
          </div>
        </Card>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <SectionLabel>Reasoning trace (streaming)</SectionLabel>
        {traces.length === 0 ? (
          <p style={{ color: C.textMut, fontSize: 13 }}>Awaiting trace events…</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 280, overflowY: "auto" }}>
            {traces.map((t, i) => (
              <div key={`${t.attack_id}-${i}`} style={{ borderLeft: `2px solid ${C.primaryDim}`, paddingLeft: 12 }}>
                <Mono style={{ fontSize: 11, color: C.textMut }}>{t.attack_id.slice(0, 8)}</Mono>
                <div style={{ fontFamily: MONO, fontSize: 12.5, color: t.rationale ? C.text : C.textMut }}>
                  {t.rationale ?? "(no rationale recorded for this attack)"}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <SectionLabel>Verdicts ({verdicts.length})</SectionLabel>
        {verdicts.length === 0 ? (
          <p style={{ color: C.textMut, fontSize: 13 }}>No verdicts recorded yet.</p>
        ) : (
          <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ color: C.textMut, textAlign: "left", fontSize: 11 }}>
                <th style={{ padding: "6px 8px" }}>Verdict</th>
                <th style={{ padding: "6px 8px" }}>Result</th>
                <th style={{ padding: "6px 8px" }}>Fail weight</th>
              </tr>
            </thead>
            <tbody>
              {verdicts.slice(0, 50).map((v) => (
                <tr key={v.verdict_id} style={{ borderTop: `1px solid ${C.border}` }}>
                  <td style={{ padding: "8px" }}>
                    <Link to={`/runs/${id}/verdicts/${v.verdict_id}`} style={{ color: C.primary, fontFamily: MONO }}>
                      {v.verdict_id.slice(0, 8)}
                    </Link>
                  </td>
                  <td style={{ padding: "8px" }}>
                    <Pill tone={v.aggregate_pass ? "pass" : "fail"}>{v.aggregate_pass ? "caught" : "MISSED"}</Pill>
                  </td>
                  <td style={{ padding: "8px", fontFamily: MONO, color: C.text }}>{v.fail_weight.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </Layout>
  )
}
