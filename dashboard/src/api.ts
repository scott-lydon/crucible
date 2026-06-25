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
  target: string
  rounds: number
  batch_size?: number | null
  seed: string
  run_blue: boolean
  // Operator-supplied sealed-spec YAML (US-1 input side). When non-blank it
  // OVERRIDES the target's default; blank/omitted falls back to the default.
  spec?: string | null
}

export type HaltError = { error: "certification_halted"; recall: number | null; threshold: number }

// The typed 422 body when a pasted sealed spec fails parse/validation. The
// launcher renders ``message`` inline (and does NOT navigate).
export type SpecValidationError = { error: "invalid_sealed_spec"; message: string }

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
  if (r.status === 422) {
    const detail = (await safeBody(r)) as { detail?: SpecValidationError } | null
    throw new HttpError(422, detail?.detail ?? detail)
  }
  if (!r.ok) throw new HttpError(r.status, await safeBody(r))
  return (await r.json()) as { run_id: string }
}

// ---------------------------------------------------------------------------
// Target registry (US-1 input side) — real, server-side; no hardcoded list.
// ---------------------------------------------------------------------------

export type TargetSummary = {
  name: string
  kind: string
  model_artifact_ref: string
  has_default_spec: boolean
}

export async function getTargets(): Promise<TargetSummary[]> {
  const data = await getJson<{ targets: TargetSummary[] }>("/targets")
  return data.targets
}

// The target's DEFAULT sealed spec as YAML text (pre-fills the launcher textarea).
export async function getTargetSpec(name: string): Promise<string> {
  const r = await fetch(url(`/targets/${encodeURIComponent(name)}/spec`))
  if (!r.ok) throw new HttpError(r.status, await safeBody(r))
  return r.text()
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

// A row in the recent-runs index (GET /runs). Newest first. Powers the Runs-list
// page and the run pickers on Metrics/Blue/Catalog so an operator no longer has
// to memorize a run id.
export type RunSummary = {
  run_id: string
  target: string
  status: string
  created_at: string
  rounds: number
}

export async function getRuns(limit = 50): Promise<RunSummary[]> {
  const data = await getJson<{ runs: RunSummary[] }>(`/runs?limit=${limit}`)
  return data.runs
}

// Request a graceful stop of a still-running campaign. The backend halts at the
// next checkpoint, so the returned status is ``stopping`` (then eventually
// ``stopped``). Idempotent: a terminal run returns its terminal status. Only the
// operator's confirmed Stop action calls this.
export async function stopRun(runId: string): Promise<{ run_id: string; status: string }> {
  const r = await fetch(url(`/runs/${runId}/stop`), { method: "POST" })
  if (!r.ok) throw new HttpError(r.status, await safeBody(r))
  return (await r.json()) as { run_id: string; status: string }
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
      // Real cost tile (US-10): total recorded LLM dollars / caught hacks.
      // ``null`` when there are no caught hacks or no recorded calls — rendered
      // honestly as "Not yet measured", never a fabricated 0.0.
      dollars_per_caught_hack: number | null
      // Honestly null: there is no human-review signal in the system, so the
      // human-minutes tile stays "Not yet measured" rather than fabricating one.
      human_minutes_per_1k_outputs: number | null
    }

export function isNotMeasured(m: Metrics): m is { status: "Not yet measured"; white_box?: WhiteBox | null } {
  return "status" in m && m.status === "Not yet measured"
}

export function getMetrics(runId: string): Promise<Metrics> {
  return getJson<Metrics>(`/runs/${runId}/metrics`)
}

// ---------------------------------------------------------------------------
// LLM calls / Inspect (US-2, US-3)
// ---------------------------------------------------------------------------

export type LlmCallSummary = {
  id: string
  pillar: string
  model: string
  input_tokens: number
  output_tokens: number
  dollars: number | null
  created_at: string
  prompt_preview: string
}

export type LlmCallDetail = {
  id: string
  run_id: string
  pillar: string
  model: string
  prompt: string
  system: string | null
  raw_response: string | null
  parsed_output: string | null
  input_tokens: number
  output_tokens: number
  dollars: number | null
  created_at: string
}

export async function getLlmCalls(runId: string): Promise<LlmCallSummary[]> {
  try {
    const data = await getJson<{ count: number; llm_calls: LlmCallSummary[] }>(`/runs/${runId}/llm_calls`)
    return data.llm_calls
  } catch (e) {
    if (e instanceof HttpError && e.status === 404) return []
    throw e
  }
}

export function getLlmCall(callId: string): Promise<LlmCallDetail> {
  return getJson<LlmCallDetail>(`/llm_calls/${callId}`)
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
// Strategy catalog (US-6) — the persisted cross-run institutional memory.
// ---------------------------------------------------------------------------

export type CatalogRow = {
  tactic: string
  target_type: string
  first_discovered_run: string
  reuse_count: number
  avg_dollars_to_succeed: number | null
}

export function getCatalog(targetType?: string): Promise<{ count: number; rows: CatalogRow[] }> {
  const q = targetType ? `?target_type=${encodeURIComponent(targetType)}` : ""
  return getJson<{ count: number; rows: CatalogRow[] }>(`/catalog${q}`)
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
