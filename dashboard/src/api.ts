// Real API client for the Crucible operator dashboard.
// Talks to the FastAPI backend through the Vite proxy at /api (see vite.config.ts).
// In tests this module's fetch/EventSource are mocked; nothing here requires a
// live backend at import time.

export const API_BASE = (import.meta.env?.VITE_API_BASE ?? "/api").replace(/\/$/, "")

function url(path: string): string {
  return `${API_BASE}${path}`
}

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(url(path))
  if (!r.ok) throw new HttpError(r.status, await safeBody(r))
  return (await r.json()) as T
}

async function safeBody(r: Response): Promise<unknown> {
  try {
    return await r.json()
  } catch {
    return null
  }
}

export class HttpError extends Error {
  status: number
  body: unknown
  constructor(status: number, body: unknown) {
    super(`HTTP ${status}`)
    this.name = "HttpError"
    this.status = status
    this.body = body
  }
}

// ---------------------------------------------------------------------------
// Launch (US-1)
// ---------------------------------------------------------------------------

export type LaunchBody = {
  target: "sparkov" | "synth"
  rounds: number
  batch_size?: number | null
  seed: string
  run_blue: boolean
}

export type HaltError = { error: "certification_halted"; recall: number | null; threshold: number }

export async function launchRun(body: LaunchBody): Promise<{ run_id: string }> {
  const r = await fetch(url("/runs"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (r.status === 409) {
    const detail = (await safeBody(r)) as { detail?: HaltError } | null
    throw new HttpError(409, detail?.detail ?? detail)
  }
  if (!r.ok) throw new HttpError(r.status, await safeBody(r))
  return (await r.json()) as { run_id: string }
}

// ---------------------------------------------------------------------------
// Run status + metrics (US-2, US-10)
// ---------------------------------------------------------------------------

export type RunStatus = {
  run_id: string
  status: string
  seed: string
  n_rounds: number
  verdict_count: number
}

export function getRun(runId: string): Promise<RunStatus> {
  return getJson<RunStatus>(`/runs/${runId}`)
}

export type RoundMetric = {
  round_index: number
  asr: number | null
  detection_rate: number | null
  evasion_rate: number | null
}

export type WhiteBox = {
  black_box_catch_rate: number | null
  white_box_catch_rate: number | null
  white_box_gap: number | null
}

export type Metrics =
  | { status: "Not yet measured"; white_box?: WhiteBox | null }
  | {
      per_round: RoundMetric[]
      baseline_validation_detection: number | null
      gap: number | null
      white_box: WhiteBox | null
    }

export function isNotMeasured(m: Metrics): m is { status: "Not yet measured"; white_box?: WhiteBox | null } {
  return "status" in m && m.status === "Not yet measured"
}

export function getMetrics(runId: string): Promise<Metrics> {
  return getJson<Metrics>(`/runs/${runId}/metrics`)
}

// ---------------------------------------------------------------------------
// Verdicts (US-3, US-4)
// ---------------------------------------------------------------------------

export type VerdictSummary = {
  verdict_id: string
  round_id: string
  aggregate_pass: boolean
  fail_weight: number
}

export async function getVerdicts(runId: string): Promise<VerdictSummary[]> {
  try {
    const data = await getJson<{ verdicts: VerdictSummary[] }>(`/runs/${runId}/verdicts`)
    return data.verdicts
  } catch (e) {
    if (e instanceof HttpError && e.status === 404) return []
    throw e
  }
}

export type OracleVote = {
  oracle: string
  vote: string
  weight: number
  reason: string
  evidence: Record<string, unknown> | null
  abstained: boolean
  is_llm: boolean
}

export type VerdictDetail = {
  verdict_id: string
  run_id: string
  votes: OracleVote[]
}

export function getVerdict(runId: string, verdictId: string): Promise<VerdictDetail> {
  return getJson<VerdictDetail>(`/runs/${runId}/verdicts/${verdictId}`)
}

// The six oracles Crucible always runs. The verdict detail renders one card per
// oracle even when a vote is missing from the payload, so the panel of six is
// always present and honest about which oracles actually voted.
export const ORACLE_KINDS = [
  "held_out",
  "metamorphic",
  "invariant",
  "differential",
  "property_fuzz",
  "llm_judge",
] as const
export type OracleKind = (typeof ORACLE_KINDS)[number]

export const ORACLE_LABELS: Record<OracleKind, string> = {
  held_out: "Held-out generator",
  metamorphic: "Metamorphic",
  invariant: "Invariant",
  differential: "Differential",
  property_fuzz: "Property fuzz",
  llm_judge: "LLM judge",
}

// ---------------------------------------------------------------------------
// Blue patch review (US-7)
// ---------------------------------------------------------------------------

export type BlueRound = {
  run_id: string
  features_added: string[] | null
  detection_before: number | null
  detection_after: number | null
  recovered: boolean
  n_holdout: number | null
  proposer_rationale: string | null
  new_model_ref: string | null
  iteration_trail: unknown
}

export function getBlue(runId: string): Promise<BlueRound> {
  return getJson<BlueRound>(`/runs/${runId}/blue`)
}

// ---------------------------------------------------------------------------
// Corpus (US-11)
// ---------------------------------------------------------------------------

export type CorpusRow = {
  attack_id: string
  target_type: string
  tactic: string
  prompt?: string
  audit_trace: Record<string, unknown>
  dollars?: number | null
  captured_at: string
}

export function getCorpus(runId?: string): Promise<{ count: number; rows: CorpusRow[] }> {
  const q = runId ? `?run_id=${encodeURIComponent(runId)}` : ""
  return getJson<{ count: number; rows: CorpusRow[] }>(`/corpus${q}`)
}

export function corpusExportUrl(runId?: string): string {
  const q = runId ? `?run_id=${encodeURIComponent(runId)}` : ""
  return url(`/corpus/export${q}`)
}

// ---------------------------------------------------------------------------
// SR 11-7 report (US-12)
// ---------------------------------------------------------------------------

export async function getReport(runId: string): Promise<string> {
  const r = await fetch(url(`/reports/${runId}`))
  if (!r.ok) throw new HttpError(r.status, null)
  return r.text()
}

// ---------------------------------------------------------------------------
// Health + seal card (US-8, US-9)
// ---------------------------------------------------------------------------

export type HealthLeaf = {
  state?: string
  last_self_test?: string | null
  error?: string | null
  [k: string]: unknown
}

export type Health = Record<string, unknown>

export function getHealth(): Promise<Health> {
  return getJson<Health>(`/health`)
}

// ---------------------------------------------------------------------------
// Halt status (US-13) — read on every route for the global banner.
// ---------------------------------------------------------------------------

export type HaltStatus = { halted: boolean; recall: number | null; threshold: number }

export function getHalt(): Promise<HaltStatus> {
  return getJson<HaltStatus>(`/halt`)
}

// ---------------------------------------------------------------------------
// SSE live stream (US-2)
// ---------------------------------------------------------------------------

export type AttackEvent = {
  attack_id: string
  round_id: string
  evaded: boolean
  true_label_preserved: boolean
  pre_score: number | null
  post_score: number | null
  asr_so_far: number | null
}
export type TraceEvent = { attack_id: string; rationale: string | null; evidence: Record<string, unknown> }
export type VerdictEvent = {
  verdict_id: string
  round_id: string
  aggregate_pass: boolean
  fail_weight: number
  detection_rate_so_far: number | null
}
export type CompleteEvent = {
  run_id: string
  status: string
  attacks: number
  verdicts: number
  timed_out: boolean
}

export type RunStreamHandlers = {
  onAttack?: (e: AttackEvent) => void
  onTrace?: (e: TraceEvent) => void
  onVerdict?: (e: VerdictEvent) => void
  onComplete?: (e: CompleteEvent) => void
  onError?: (e: Event) => void
}

// Subscribe to a run's SSE stream. Returns a disposer that closes the source.
// EventSource is provided by jsdom-free tests via a small mock; the real one is
// the browser's native EventSource against the documented /runs/:id/stream.
export function subscribeRun(runId: string, handlers: RunStreamHandlers): () => void {
  const es = new EventSource(url(`/runs/${runId}/stream`))
  const parse = <T>(cb?: (e: T) => void) => (ev: MessageEvent) => {
    if (!cb) return
    try {
      cb(JSON.parse(ev.data) as T)
    } catch {
      /* ignore malformed frame */
    }
  }
  es.addEventListener("attack", parse<AttackEvent>(handlers.onAttack) as EventListener)
  es.addEventListener("trace", parse<TraceEvent>(handlers.onTrace) as EventListener)
  es.addEventListener("verdict", parse<VerdictEvent>(handlers.onVerdict) as EventListener)
  es.addEventListener("complete", ((ev: MessageEvent) => {
    parse<CompleteEvent>(handlers.onComplete)(ev)
    es.close()
  }) as EventListener)
  if (handlers.onError) es.onerror = handlers.onError
  return () => es.close()
}
