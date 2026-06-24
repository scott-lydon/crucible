// US-15: Internal debug route. Minimal — pick a past run id and jump to its
// live view / verdicts / report, and a mock-LLM-mode toggle whose state is
// reflected in the header banner so a mock session can never be confused with a
// real run. (Resume-at-round and a server-side mock toggle are backend follow-ups.)

import { useState } from "react"
import { Link } from "react-router-dom"
import Layout from "../components/Layout"
import { Button, Card, SectionLabel } from "../components/ui"
import { C, MONO } from "../theme"

export default function AdminDebug() {
  const [mock, setMock] = useState(false)
  const [runId, setRunId] = useState("")

  return (
    <Layout mock={mock}>
      <SectionLabel>Internal Debug · US-15</SectionLabel>
      <h1 style={{ color: C.textHi, fontSize: 22, fontWeight: 600, margin: "0 0 16px" }}>Admin / debug</h1>

      <Card style={{ marginBottom: 16 }}>
        <SectionLabel>Mock-LLM mode</SectionLabel>
        <label style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13, color: C.text }}>
          <input type="checkbox" checked={mock} onChange={(e) => setMock(e.target.checked)} />
          Toggle mock-LLM mode (indicator)
        </label>
        <p style={{ fontSize: 12, color: C.textMut, marginTop: 8, marginBottom: 0 }}>
          When on, the header shows the yellow MOCK-LLM banner so the session is unmistakably not a real run.
        </p>
      </Card>

      <Card>
        <SectionLabel>Jump to a past run</SectionLabel>
        <div style={{ display: "flex", gap: 10, marginBottom: 12 }}>
          <input
            value={runId}
            onChange={(e) => setRunId(e.target.value)}
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
        </div>
        {runId ? (
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Link to={`/runs/${runId}`}>
              <Button variant="ghost">Live run view</Button>
            </Link>
            <Link to={`/metrics?run_id=${encodeURIComponent(runId)}`}>
              <Button variant="ghost">Metrics</Button>
            </Link>
            <Link to={`/blue/${runId}`}>
              <Button variant="ghost">Blue patch</Button>
            </Link>
            <Link to={`/catalog?run_id=${encodeURIComponent(runId)}`}>
              <Button variant="ghost">Catalog</Button>
            </Link>
          </div>
        ) : (
          <p style={{ color: C.textMut, fontSize: 13, margin: 0 }}>Enter a run id to reveal jump links.</p>
        )}
      </Card>
    </Layout>
  )
}
