// US-2: Live Run View. SSE-wired — the ASR chart appends a point on every
// `attack` event, the detection chart on every `verdict` event, and the trace
// pane streams the red agent's rationale from `trace` events (rendered
// gracefully when rationale is null). The headline of slice-15 is that the ASR
// chart updates live as attack events arrive.

import { useEffect, useRef, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import {
  getLlmCall,
  getLlmCalls,
  getVerdicts,
  subscribeRun,
  type AttackEvent,
  type CompleteEvent,
  type LlmCallDetail,
  type LlmCallSummary,
  type TraceEvent,
  type VerdictEvent,
  type VerdictSummary,
} from "../api"
import Layout from "../components/Layout"
import { Button, Card, Mono, Pill, SectionLabel } from "../components/ui"
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
  const [llmCalls, setLlmCalls] = useState<LlmCallSummary[]>([])
  const [inspect, setInspect] = useState<LlmCallDetail | null>(null)
  const [inspectErr, setInspectErr] = useState<string | null>(null)
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

  // The recorded LLM calls list (US-2/US-3 Inspect). One-shot fetch, refreshed
  // when the run completes; honest empty-state when nothing was recorded.
  useEffect(() => {
    if (!id) return
    getLlmCalls(id).then(setLlmCalls).catch(() => setLlmCalls([]))
  }, [id, status])

  function openInspect(callId: string) {
    setInspect(null)
    setInspectErr(null)
    getLlmCall(callId)
      .then(setInspect)
      .catch((e) => setInspectErr(e instanceof Error ? e.message : "Failed to load call"))
  }

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

      <Card style={{ marginTop: 16 }}>
        <SectionLabel>LLM calls — Inspect ({llmCalls.length})</SectionLabel>
        {llmCalls.length === 0 ? (
          <p style={{ color: C.textMut, fontSize: 13 }}>No LLM calls recorded for this run yet.</p>
        ) : (
          <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ color: C.textMut, textAlign: "left", fontSize: 11 }}>
                <th style={{ padding: "6px 8px" }}>Pillar</th>
                <th style={{ padding: "6px 8px" }}>Model</th>
                <th style={{ padding: "6px 8px" }}>Tokens (in/out)</th>
                <th style={{ padding: "6px 8px" }}>Dollars</th>
                <th style={{ padding: "6px 8px" }} />
              </tr>
            </thead>
            <tbody>
              {llmCalls.slice(0, 100).map((c) => (
                <tr key={c.id} style={{ borderTop: `1px solid ${C.border}` }}>
                  <td style={{ padding: "8px", fontFamily: MONO, color: C.text }}>{c.pillar}</td>
                  <td style={{ padding: "8px", fontFamily: MONO, color: C.textMut }}>{c.model}</td>
                  <td style={{ padding: "8px", fontFamily: MONO, color: C.textMut }}>
                    {c.input_tokens}/{c.output_tokens}
                  </td>
                  <td style={{ padding: "8px", fontFamily: MONO, color: C.text }}>
                    {c.dollars == null ? "—" : `$${c.dollars.toFixed(4)}`}
                  </td>
                  <td style={{ padding: "8px" }}>
                    <Button variant="ghost" onClick={() => openInspect(c.id)}>
                      Inspect
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {inspectErr && <p style={{ color: C.danger, fontSize: 12, marginTop: 10 }}>{inspectErr}</p>}
      </Card>

      {inspect && (
        <Card style={{ marginTop: 16, borderColor: C.primaryDim }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
            <SectionLabel>
              Inspect · {inspect.pillar} · <Mono>{inspect.model}</Mono>
            </SectionLabel>
            <Button variant="ghost" onClick={() => setInspect(null)}>
              Close
            </Button>
          </div>
          <div style={{ fontSize: 12, color: C.textMut, marginBottom: 12 }}>
            {inspect.input_tokens} in / {inspect.output_tokens} out ·{" "}
            {inspect.dollars == null ? "cost not recorded" : `$${inspect.dollars.toFixed(4)}`} ·{" "}
            <Mono>{inspect.created_at}</Mono>
          </div>
          {([
            ["System", inspect.system],
            ["Prompt", inspect.prompt],
            ["Raw response", inspect.raw_response],
            ["Parsed output", inspect.parsed_output],
          ] as const).map(([label, body]) => (
            <div key={label} style={{ marginBottom: 12 }}>
              <SectionLabel>{label}</SectionLabel>
              <pre
                style={{
                  fontFamily: MONO,
                  fontSize: 12,
                  color: body ? C.text : C.textMut,
                  background: C.surface2,
                  border: `1px solid ${C.border}`,
                  borderRadius: 7,
                  padding: 12,
                  overflowX: "auto",
                  whiteSpace: "pre-wrap",
                  margin: 0,
                }}
              >
                {body ?? "(not recorded)"}
              </pre>
            </div>
          ))}
        </Card>
      )}
    </Layout>
  )
}
