// Recent-runs index. A table of the latest runs from GET /runs (newest first):
// run id (short, links to the live run view), target, status pill, created_at,
// and rounds — plus quick links per row to that run's Metrics / Blue / Catalog.
// This is the Launcher's companion: an operator no longer has to memorize a run
// id to find their way back to a run. Honest empty-state when nothing has run.

import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { getRuns, stopRun, type RunSummary } from "../api"
import Layout from "../components/Layout"
import { Card, ConfirmDialog, isTerminalStatus, Mono, Pill, SectionLabel, statusTone } from "../components/ui"
import { C } from "../theme"

export default function Runs() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  // The run whose Stop the operator is confirming, and the set of ids currently
  // being stopped (button disabled). One modal, reused for whichever row.
  const [confirmId, setConfirmId] = useState<string | null>(null)
  const [stopping, setStopping] = useState<Record<string, boolean>>({})

  useEffect(() => {
    getRuns()
      .then(setRuns)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load runs"))
  }, [])

  // Confirmed per-row Stop: optimistically reflect the returned status in the row.
  function handleStop(runId: string) {
    setConfirmId(null)
    setStopping((s) => ({ ...s, [runId]: true }))
    stopRun(runId)
      .then((res) => setRuns((rs) => rs?.map((r) => (r.run_id === runId ? { ...r, status: res.status } : r)) ?? rs))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to stop run"))
      .finally(() => setStopping((s) => ({ ...s, [runId]: false })))
  }

  return (
    <Layout>
      <SectionLabel>Recent runs</SectionLabel>
      <h1 style={{ color: C.textHi, fontSize: 22, fontWeight: 600, margin: "0 0 6px" }}>Runs</h1>
      <p style={{ color: C.textMut, fontSize: 13, marginTop: 0 }}>
        The most recent Crucible runs, newest first. Open one to watch its live view, or jump straight to its metrics,
        blue review, or catalog.
      </p>

      {error && (
        <Card style={{ borderColor: C.danger }}>
          <span style={{ color: C.danger }}>{error}</span>
        </Card>
      )}
      {!error && runs == null && <p style={{ color: C.textMut }}>Loading runs…</p>}
      {!error && runs && runs.length === 0 && (
        <p style={{ color: C.textMut }}>
          No runs yet. <Link to="/" style={{ color: C.primary, textDecoration: "none" }}>Launch a run →</Link>
        </p>
      )}

      {runs && runs.length > 0 && (
        <Card>
          <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ color: C.textMut, textAlign: "left", fontSize: 11 }}>
                <th style={{ padding: "6px 8px" }}>Run</th>
                <th style={{ padding: "6px 8px" }}>Target</th>
                <th style={{ padding: "6px 8px" }}>Status</th>
                <th style={{ padding: "6px 8px" }}>Created</th>
                <th style={{ padding: "6px 8px" }}>Rounds</th>
                <th style={{ padding: "6px 8px" }}>Links</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.run_id} style={{ borderTop: `1px solid ${C.border}` }}>
                  <td style={{ padding: "8px" }}>
                    <Link to={`/runs/${r.run_id}`} style={{ color: C.primary, fontFamily: "inherit" }}>
                      <Mono>{r.run_id.slice(0, 8)}</Mono>
                    </Link>
                  </td>
                  <td style={{ padding: "8px", fontFamily: "inherit" }}>
                    <Mono style={{ color: C.text }}>{r.target}</Mono>
                  </td>
                  <td style={{ padding: "8px" }}>
                    <Pill tone={statusTone(r.status)}>{r.status}</Pill>
                  </td>
                  <td style={{ padding: "8px" }}>
                    <Mono style={{ color: C.textMut, fontSize: 12 }}>{r.created_at}</Mono>
                  </td>
                  <td style={{ padding: "8px" }}>
                    <Mono style={{ color: C.text }}>{r.rounds}</Mono>
                  </td>
                  <td style={{ padding: "8px", display: "flex", gap: 10 }}>
                    <Link to={`/metrics?run_id=${r.run_id}`} style={{ color: C.primary, fontSize: 12, textDecoration: "none" }}>
                      Metrics
                    </Link>
                    <Link to={`/blue/${r.run_id}`} style={{ color: C.primary, fontSize: 12, textDecoration: "none" }}>
                      Blue
                    </Link>
                    <Link to={`/catalog?run_id=${r.run_id}`} style={{ color: C.primary, fontSize: 12, textDecoration: "none" }}>
                      Catalog
                    </Link>
                    {!isTerminalStatus(r.status) && (
                      <button
                        type="button"
                        onClick={() => setConfirmId(r.run_id)}
                        disabled={stopping[r.run_id] || r.status === "stopping"}
                        style={{
                          background: "transparent",
                          border: "none",
                          padding: 0,
                          color: C.danger,
                          fontSize: 12,
                          fontFamily: "inherit",
                          cursor: stopping[r.run_id] ? "not-allowed" : "pointer",
                          opacity: stopping[r.run_id] || r.status === "stopping" ? 0.5 : 1,
                        }}
                      >
                        {stopping[r.run_id] || r.status === "stopping" ? "Stopping…" : "Stop"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {confirmId && (
        <ConfirmDialog
          title="Stop this run?"
          body={
            <>
              The campaign will halt at the next checkpoint. Work already completed is preserved.
              <br />
              <Mono style={{ fontSize: 12, color: C.textMut }}>{confirmId.slice(0, 8)}</Mono>
            </>
          }
          confirmLabel="Stop run"
          confirmDisabled={!!stopping[confirmId]}
          onConfirm={() => handleStop(confirmId)}
          onCancel={() => setConfirmId(null)}
        />
      )}
    </Layout>
  )
}
