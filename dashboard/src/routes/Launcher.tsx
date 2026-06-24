// US-1: Run Launcher. Pick a target + rounds + seed, Start a run, navigate to the
// live run view. On 409 certification_halted, surface the typed halt body honestly
// instead of pretending the launch succeeded.

import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { launchRun, HttpError, type HaltError } from "../api"
import Layout from "../components/Layout"
import { Button, Card, SectionLabel } from "../components/ui"
import { C, MONO } from "../theme"

export default function Launcher() {
  const navigate = useNavigate()
  const [target, setTarget] = useState<"sparkov" | "synth">("sparkov")
  const [seed, setSeed] = useState("seed-1")
  const [rounds, setRounds] = useState(3)
  const [runBlue, setRunBlue] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [halt, setHalt] = useState<HaltError | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setHalt(null)
    try {
      const { run_id } = await launchRun({ target, rounds, seed, run_blue: runBlue })
      navigate(`/runs/${run_id}`)
    } catch (err) {
      if (err instanceof HttpError && err.status === 409) {
        setHalt(err.body as HaltError)
      } else {
        setError(err instanceof Error ? err.message : "Unknown error")
      }
      setLoading(false)
    }
  }

  const inputStyle: React.CSSProperties = {
    width: "100%",
    fontFamily: MONO,
    fontSize: 13,
    color: C.textHi,
    background: C.surface2,
    border: `1px solid ${C.border}`,
    borderRadius: 7,
    padding: "9px 11px",
  }
  const labelStyle: React.CSSProperties = { display: "block", fontSize: 12, color: C.textMut, marginBottom: 6 }

  return (
    <Layout>
      <div style={{ maxWidth: 460, margin: "0 auto" }}>
        <SectionLabel>Run Launcher · US-1</SectionLabel>
        <h1 style={{ color: C.textHi, fontSize: 22, fontWeight: 600, margin: "0 0 18px" }}>Launch a Crucible run</h1>
        <Card>
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div>
              <label style={labelStyle} htmlFor="target">
                Target
              </label>
              <select
                id="target"
                value={target}
                onChange={(e) => setTarget(e.target.value as "sparkov" | "synth")}
                style={inputStyle}
              >
                <option value="sparkov">sparkov — real victim, live bounded LLM (~$0.40/run)</option>
                <option value="synth">synth — offline synthetic victim (no LLM calls)</option>
              </select>
            </div>
            <div>
              <label style={labelStyle} htmlFor="seed">
                Seed
              </label>
              <input id="seed" type="text" value={seed} onChange={(e) => setSeed(e.target.value)} style={inputStyle} />
            </div>
            <div>
              <label style={labelStyle} htmlFor="rounds">
                Rounds (1–5)
              </label>
              <input
                id="rounds"
                type="number"
                min={1}
                max={5}
                value={rounds}
                onChange={(e) => setRounds(Number(e.target.value))}
                style={inputStyle}
              />
            </div>
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: C.text }}>
              <input type="checkbox" checked={runBlue} onChange={(e) => setRunBlue(e.target.checked)} />
              Run blue recovery arc
            </label>

            {halt && (
              <div
                role="alert"
                style={{
                  background: C.haltBg,
                  border: `1px solid ${C.haltBorder}`,
                  color: C.haltText,
                  borderRadius: 7,
                  padding: 12,
                  fontSize: 13,
                }}
              >
                Certification halted: recall is {halt.recall == null ? "undefined" : halt.recall.toFixed(2)}, threshold is{" "}
                {halt.threshold.toFixed(2)}. New runs are refused until recall recovers.
              </div>
            )}
            {error && <p style={{ color: C.danger, fontSize: 13, margin: 0 }}>{error}</p>}

            <Button type="submit" disabled={loading}>
              {loading ? "Starting…" : "Start run"}
            </Button>
          </form>
        </Card>
      </div>
    </Layout>
  )
}
