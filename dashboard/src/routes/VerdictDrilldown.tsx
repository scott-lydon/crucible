// US-3 / US-4: Verdict Detail. One card per oracle for the full panel of six
// (held-out, metamorphic, invariant, differential, property-fuzz, LLM-judge),
// each with its vote + reason. The LLM-judge card is marked "one vote" so it is
// never mistaken for the aggregate. An aggregator tally sums the panel.

import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import {
  getVerdict,
  ORACLE_KINDS,
  ORACLE_LABELS,
  type OracleKind,
  type OracleVote,
  type VerdictDetail,
} from "../api"
import Layout from "../components/Layout"
import { Card, Mono, Pill, SectionLabel } from "../components/ui"
import { C, MONO } from "../theme"

function voteTone(v: OracleVote | undefined): "pass" | "fail" | "neutral" {
  if (!v) return "neutral"
  if (v.abstained) return "neutral"
  return v.vote.toLowerCase().includes("pass") || v.vote.toLowerCase() === "sound" ? "pass" : "fail"
}

export default function VerdictDrilldown() {
  const { id, vid } = useParams<{ id: string; vid: string }>()
  const [detail, setDetail] = useState<VerdictDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id || !vid) return
    getVerdict(id, vid)
      .then(setDetail)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
  }, [id, vid])

  // Index the votes by oracle kind so we render exactly six cards, even when an
  // oracle did not vote (renders "no vote recorded" rather than dropping a card).
  const byKind = new Map<string, OracleVote>()
  for (const v of detail?.votes ?? []) byKind.set(v.oracle, v)

  const cast = detail?.votes ?? []
  const failWeight = cast
    .filter((v) => !v.abstained && voteTone(v) === "fail")
    .reduce((acc, v) => acc + v.weight, 0)
  const passCount = cast.filter((v) => voteTone(v) === "pass").length

  return (
    <Layout>
      <SectionLabel>Verdict Detail · US-3 / US-4</SectionLabel>
      <div style={{ marginBottom: 18 }}>
        <h1 style={{ color: C.textHi, fontSize: 20, fontWeight: 600, margin: "0 0 4px" }}>
          Verdict <Mono style={{ color: C.primary }}>{vid?.slice(0, 12)}</Mono>
        </h1>
        <Link to={`/runs/${id}`} style={{ color: C.primary, fontSize: 12, fontFamily: MONO }}>
          ← back to run
        </Link>
      </div>

      {error && <Card style={{ borderColor: C.danger }}><span style={{ color: C.danger }}>{error}</span></Card>}

      {!detail && !error && <p style={{ color: C.textMut }}>Loading…</p>}

      {detail && (
        <>
          <Card style={{ marginBottom: 16 }}>
            <SectionLabel>Aggregator tally</SectionLabel>
            <div style={{ display: "flex", gap: 20, alignItems: "baseline" }}>
              <div>
                <span style={{ fontFamily: MONO, fontSize: 24, color: C.textHi }}>{passCount}</span>
                <span style={{ color: C.textMut, fontSize: 12 }}> / {cast.length} oracles passed</span>
              </div>
              <div>
                <span style={{ color: C.textMut, fontSize: 12 }}>summed fail weight </span>
                <Mono style={{ color: failWeight > 0 ? C.danger : C.success, fontSize: 16 }}>{failWeight.toFixed(3)}</Mono>
              </div>
            </div>
          </Card>

          <SectionLabel>Six oracles</SectionLabel>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 14 }}>
            {ORACLE_KINDS.map((kind: OracleKind) => {
              const v = byKind.get(kind)
              const isJudge = kind === "llm_judge"
              return (
                <Card key={kind} style={{ borderColor: isJudge ? C.primaryDim : C.border }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
                    <span style={{ color: C.textHi, fontWeight: 600, fontSize: 14 }}>{ORACLE_LABELS[kind]}</span>
                    {isJudge && <Pill tone="warn">one vote</Pill>}
                    {v ? (
                      <Pill tone={voteTone(v)}>{v.abstained ? "abstain" : v.vote}</Pill>
                    ) : (
                      <Pill tone="neutral">no vote recorded</Pill>
                    )}
                  </div>
                  {v && (
                    <div style={{ fontSize: 12, color: C.textMut, marginBottom: 6 }}>
                      weight <Mono>{v.weight}</Mono>
                    </div>
                  )}
                  <p style={{ fontSize: 13, color: C.text, margin: 0, fontFamily: MONO, lineHeight: 1.5 }}>
                    {v?.reason ?? "This oracle did not contribute a vote on this verdict."}
                  </p>
                </Card>
              )
            })}
          </div>
        </>
      )}
    </Layout>
  )
}
