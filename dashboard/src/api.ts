export type RoundMetric = {
  round_index: number
  asr: number | null
  detection_rate: number | null
  evasion_rate: number | null
}
export type Metrics =
  | { status: "Not yet measured" }
  | { per_round: RoundMetric[]; baseline_validation_detection: number | null; gap: number | null }

export function isNotMeasured(m: Metrics): m is { status: "Not yet measured" } {
  return "status" in m && m.status === "Not yet measured"
}
export async function launchRun(body: { n_rounds: number; batch_size: number; seed: string }) {
  const r = await fetch("/api/runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
  if (!r.ok) throw new Error(`launch failed: ${r.status}`)
  return (await r.json()) as { run_id: string }
}
export async function getMetrics(runId: string): Promise<Metrics> {
  const r = await fetch(`/api/runs/${runId}/metrics`)
  return (await r.json()) as Metrics
}
