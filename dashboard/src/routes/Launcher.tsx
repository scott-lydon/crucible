// US-1 input side: the operator selects a bundled target adapter (from the REAL
// GET /targets registry — no hardcoded list), reviews/edits the SEALED SPEC the
// oracles will enforce (pre-filled from GET /targets/:name/spec), sees the
// target's model-artifact reference (read-only — uploading a custom model/code
// is post-capstone), sets params, and Starts. On 201 navigate to the live run;
// on 409 surface the halt body; on 422 show the spec-validation error inline
// (no navigate). No faked data — every value comes from the real endpoints.

import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import {
  launchRun,
  getTargets,
  getTargetSpec,
  HttpError,
  type HaltError,
  type SpecValidationError,
  type TargetSummary,
} from "../api"
import Layout from "../components/Layout"
import { Button, Card, SectionLabel } from "../components/ui"
import { C, MONO } from "../theme"

export default function Launcher() {
  const navigate = useNavigate()
  const [targets, setTargets] = useState<TargetSummary[]>([])
  const [target, setTarget] = useState<string>("")
  const [spec, setSpec] = useState("")
  const [specLoading, setSpecLoading] = useState(false)
  const [seed, setSeed] = useState("seed-1")
  const [rounds, setRounds] = useState(3)
  const [runBlue, setRunBlue] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [specError, setSpecError] = useState<string | null>(null)
  const [halt, setHalt] = useState<HaltError | null>(null)

  // Load the real target registry once; default-select the first target.
  useEffect(() => {
    let live = true
    getTargets()
      .then((ts) => {
        if (!live) return
        setTargets(ts)
        if (ts.length > 0) setTarget((t) => t || ts[0].name)
      })
      .catch((e) => live && setError(e instanceof Error ? e.message : "Failed to load targets"))
    return () => {
      live = false
    }
  }, [])

  // Pre-fill the sealed-spec textarea from the selected target's default spec.
  useEffect(() => {
    if (!target) return
    let live = true
    setSpecLoading(true)
    setSpecError(null)
    getTargetSpec(target)
      .then((text) => live && setSpec(text))
      .catch((e) => live && setError(e instanceof Error ? e.message : "Failed to load spec"))
      .finally(() => live && setSpecLoading(false))
    return () => {
      live = false
    }
  }, [target])

  const selected = targets.find((t) => t.name === target) ?? null

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setSpecError(null)
    setHalt(null)
    try {
      const { run_id } = await launchRun({ target, rounds, seed, run_blue: runBlue, spec })
      navigate(`/runs/${run_id}`)
    } catch (err) {
      if (err instanceof HttpError && err.status === 409) {
        setHalt(err.body as HaltError)
      } else if (err instanceof HttpError && err.status === 422) {
        const body = err.body as SpecValidationError | null
        setSpecError(body?.message ?? "The sealed spec failed validation.")
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
  const hintStyle: React.CSSProperties = { fontSize: 11, color: C.textMut, marginTop: 6 }

  return (
    <Layout>
      <div style={{ maxWidth: 920, margin: "0 auto" }}>
        <SectionLabel>Run Launcher · US-1</SectionLabel>
        <h1 style={{ color: C.textHi, fontSize: 22, fontWeight: 600, margin: "0 0 18px" }}>Launch a Crucible run</h1>
        <Card>
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div>
              <label style={labelStyle} htmlFor="target">
                Target adapter
              </label>
              <select
                id="target"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                style={inputStyle}
                disabled={targets.length === 0}
              >
                {targets.length === 0 && <option value="">Loading targets…</option>}
                {targets.map((t) => (
                  <option key={t.name} value={t.name}>
                    {t.name} — {t.kind}
                  </option>
                ))}
              </select>
            </div>

            {selected && (
              <div>
                <label style={labelStyle} htmlFor="model-ref">
                  Model artifact
                </label>
                <input id="model-ref" type="text" value={selected.model_artifact_ref} readOnly style={{ ...inputStyle, opacity: 0.8 }} />
                <p style={hintStyle}>
                  Read-only. The detector, label function, and adversary are the selected example's. Uploading a custom
                  model or code is post-capstone (out of scope).
                </p>
              </div>
            )}

            <div>
              <label style={labelStyle} htmlFor="spec">
                Sealed spec (YAML)
              </label>
              <textarea
                id="spec"
                value={spec}
                onChange={(e) => setSpec(e.target.value)}
                rows={14}
                spellCheck={false}
                style={{ ...inputStyle, resize: "vertical", lineHeight: 1.5 }}
                placeholder={specLoading ? "Loading default spec…" : ""}
              />
              <p style={hintStyle}>
                This is the sealed spec the oracles will enforce. Edit or paste your own obligations; on Start it is sealed
                and the run is driven off this spec. Leave blank to fall back to the target's default.
              </p>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
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
            </div>
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: C.text }}>
              <input type="checkbox" checked={runBlue} onChange={(e) => setRunBlue(e.target.checked)} />
              Run blue recovery arc
            </label>

            {specError && (
              <div
                role="alert"
                style={{
                  background: C.surface2,
                  border: `1px solid ${C.danger}`,
                  color: C.danger,
                  borderRadius: 7,
                  padding: 12,
                  fontSize: 13,
                  fontFamily: MONO,
                }}
              >
                Sealed spec invalid: {specError}
              </div>
            )}

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

            <Button type="submit" disabled={loading || targets.length === 0}>
              {loading ? "Starting…" : "Start run"}
            </Button>
          </form>
        </Card>
      </div>
    </Layout>
  )
}
