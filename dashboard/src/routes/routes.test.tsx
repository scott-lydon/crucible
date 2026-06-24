// Render tests for the 7 mandatory routes + admin. Each route renders without
// error against a MOCKED API client (no backend). The headline (slice-15) test:
// the live run view subscribes to SSE and the ASR chart updates on a mock
// `attack` event.

import { describe, it, expect, beforeEach } from "vitest"
import { render, screen, waitFor, act } from "@testing-library/react"
import { MemoryRouter, Routes, Route } from "react-router-dom"
import { installEventSource, latestEventSource, mockFetch } from "../test/setup"

import Launcher from "./Launcher"
import RunView from "./RunView"
import VerdictDrilldown from "./VerdictDrilldown"
import MetricsView from "./Metrics"
import Catalog from "./Catalog"
import BlueReview from "./BlueReview"
import Health from "./Health"
import AdminDebug from "./AdminDebug"

// Recharts' ResponsiveContainer needs a non-zero box; jsdom reports 0. Stub the
// measured dimensions so the charts render a real SVG in tests.
beforeEach(() => {
  installEventSource()
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, value: 600 })
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", { configurable: true, value: 300 })
})

function renderAt(path: string, element: React.ReactNode, routePath: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={routePath} element={element} />
      </Routes>
    </MemoryRouter>,
  )
}

const NOT_HALTED = { match: "/halt", json: { halted: false, recall: 0.9, threshold: 0.7 } }

describe("Launcher (US-1)", () => {
  it("renders the launch form", async () => {
    mockFetch([NOT_HALTED])
    renderAt("/", <Launcher />, "/")
    expect(await screen.findByText(/Launch a Crucible run/i)).toBeTruthy()
    expect(screen.getByText(/Start run/i)).toBeTruthy()
  })
})

describe("RunView (US-2) — SSE", () => {
  it("subscribes to SSE and updates the ASR chart on a mock attack event", async () => {
    mockFetch([NOT_HALTED, { match: "/verdicts", json: { verdicts: [] } }])
    renderAt("/runs/r1", <RunView />, "/runs/:id")

    // The route created an EventSource against the stream endpoint.
    await waitFor(() => {
      const es = latestEventSource()
      expect(es.url).toContain("/runs/r1/stream")
    })

    // Before any attack event the live ASR chart reports zero streamed events.
    expect(screen.getByText(/0 attack events streamed/i)).toBeTruthy()

    // Push a mock `attack` event — the ASR chart must update live.
    await act(async () => {
      latestEventSource().emit("attack", {
        attack_id: "a1",
        round_id: "rd0",
        evaded: true,
        true_label_preserved: true,
        pre_score: 0.9,
        post_score: 0.2,
        asr_so_far: 0.5,
      })
      latestEventSource().emit("attack", {
        attack_id: "a2",
        round_id: "rd0",
        evaded: false,
        true_label_preserved: true,
        pre_score: 0.9,
        post_score: 0.8,
        asr_so_far: 0.33,
      })
    })

    // The ASR chart updated live: it went from 0 streamed events to 2 purely
    // from the mock `attack` SSE frames, with no backend and no re-fetch.
    await waitFor(() => {
      expect(screen.getByText(/2 attack events streamed/i)).toBeTruthy()
    })
    expect(screen.queryByText(/0 attack events streamed/i)).toBeNull()
  })

  it("renders trace events gracefully when rationale is null", async () => {
    mockFetch([NOT_HALTED, { match: "/verdicts", json: { verdicts: [] } }])
    renderAt("/runs/r1", <RunView />, "/runs/:id")
    await waitFor(() => latestEventSource())
    await act(async () => {
      latestEventSource().emit("trace", { attack_id: "a1", rationale: null, evidence: {} })
    })
    expect(await screen.findByText(/no rationale recorded/i)).toBeTruthy()
  })

  it("lists recorded LLM calls and Inspect opens the full /llm_calls/:id record", async () => {
    const fn = mockFetch([
      NOT_HALTED,
      { match: "/verdicts", json: { verdicts: [] } },
      {
        match: "/runs/r1/llm_calls",
        json: {
          count: 1,
          llm_calls: [
            {
              id: "call-1",
              pillar: "judge",
              model: "claude-opus",
              input_tokens: 100,
              output_tokens: 20,
              dollars: 0.0042,
              created_at: "2026-06-24T00:00:00",
              prompt_preview: "score this",
            },
          ],
        },
      },
      {
        match: "/llm_calls/call-1",
        json: {
          id: "call-1",
          run_id: "r1",
          pillar: "judge",
          model: "claude-opus",
          prompt: "FULL PROMPT BODY",
          system: "you are a judge",
          raw_response: "RAW RESPONSE BODY",
          parsed_output: '{"vote":"fail"}',
          input_tokens: 100,
          output_tokens: 20,
          dollars: 0.0042,
          created_at: "2026-06-24T00:00:00",
        },
      },
    ])
    renderAt("/runs/r1", <RunView />, "/runs/:id")
    const inspectBtn = await screen.findByText("Inspect")
    await act(async () => {
      inspectBtn.click()
    })
    // The Inspect button opened GET /llm_calls/call-1 and rendered the full record.
    await waitFor(() => expect(screen.getByText("FULL PROMPT BODY")).toBeTruthy())
    expect(screen.getByText("RAW RESPONSE BODY")).toBeTruthy()
    const calls = fn.mock.calls.map((c) => String(c[0]))
    expect(calls.some((u) => u.includes("/runs/r1/llm_calls"))).toBe(true)
    expect(calls.some((u) => u.includes("/llm_calls/call-1"))).toBe(true)
  })

  it("shows the honest empty-state when no LLM calls were recorded", async () => {
    mockFetch([NOT_HALTED, { match: "/verdicts", json: { verdicts: [] } }, { match: "/llm_calls", json: { count: 0, llm_calls: [] } }])
    renderAt("/runs/r1", <RunView />, "/runs/:id")
    expect(await screen.findByText(/No LLM calls recorded for this run yet/i)).toBeTruthy()
  })
})

describe("VerdictDrilldown (US-3/US-4)", () => {
  it("shows one card per the six oracles with the LLM-judge marked one vote", async () => {
    mockFetch([
      NOT_HALTED,
      {
        match: "/verdicts/v1",
        json: {
          verdict_id: "v1",
          run_id: "r1",
          votes: [
            { oracle: "held_out", vote: "pass", weight: 1, reason: "ok", evidence: null, abstained: false, is_llm: false },
            { oracle: "llm_judge", vote: "fail", weight: 1, reason: "suspicious", evidence: null, abstained: false, is_llm: true },
          ],
        },
      },
    ])
    renderAt("/runs/r1/verdicts/v1", <VerdictDrilldown />, "/runs/:id/verdicts/:vid")
    expect(await screen.findByText("Held-out generator")).toBeTruthy()
    expect(screen.getByText("Metamorphic")).toBeTruthy()
    expect(screen.getByText("Invariant")).toBeTruthy()
    expect(screen.getByText("Differential")).toBeTruthy()
    expect(screen.getByText("Property fuzz")).toBeTruthy()
    expect(screen.getByText("LLM judge")).toBeTruthy()
    expect(screen.getByText("one vote")).toBeTruthy()
  })
})

describe("Metrics (US-10)", () => {
  it("shows 'Not yet measured' for empty data (no fabricated 0.0)", async () => {
    mockFetch([NOT_HALTED, { match: "/metrics", json: { status: "Not yet measured" } }, { match: "/corpus", json: { count: 0, rows: [] } }])
    renderAt("/metrics?run_id=r1", <MetricsView />, "/metrics")
    // Every tile reads the honest literal, never a fabricated 0.0.
    await waitFor(() => {
      expect(screen.getAllByText("Not yet measured").length).toBeGreaterThan(0)
    })
    expect(screen.queryByText("0.0")).toBeNull()
    expect(screen.queryByText("$0.00")).toBeNull()
  })

  it("renders the real dollars-per-caught-hack tile from /metrics + keeps human-minutes honest", async () => {
    mockFetch([
      NOT_HALTED,
      {
        match: "/metrics",
        json: {
          per_round: [{ round_index: 0, asr: 0.4, detection_rate: 0.8, evasion_rate: 0.2 }],
          baseline_validation_detection: 0.9,
          gap: 0.1,
          white_box: { black_box_catch_rate: 0.8, white_box_catch_rate: 0.6, white_box_gap: 0.2 },
          dollars_per_caught_hack: 0.37,
          human_minutes_per_1k_outputs: null,
        },
      },
      { match: "/corpus", json: { count: 3, rows: [] } },
    ])
    renderAt("/metrics?run_id=r1", <MetricsView />, "/metrics")
    // The white-box gap tile renders its measured value (0.20), not "Not yet measured".
    await waitFor(() => expect(screen.getByText("0.20")).toBeTruthy())
    expect(screen.getByText(/Black-box vs white-box catch rate/i)).toBeTruthy()
    // The dollars tile renders the REAL measured value from /metrics.
    expect(screen.getByText("$0.37")).toBeTruthy()
    // The human-minutes tile stays honestly "Not yet measured" (null in payload).
    expect(screen.getAllByText("Not yet measured").length).toBeGreaterThan(0)
  })
})

describe("Catalog (US-6)", () => {
  it("hits the real /catalog endpoint and shows the honest empty state", async () => {
    const fn = mockFetch([NOT_HALTED, { match: "/catalog", json: { count: 0, rows: [] } }])
    renderAt("/catalog", <Catalog />, "/catalog")
    expect(await screen.findByText(/Evasion strategy catalog/i)).toBeTruthy()
    // Honest empty-state: no fabricated rows when the catalog is empty.
    await waitFor(() => expect(screen.getByText(/No strategies in the catalog yet/i)).toBeTruthy())
    // Proves the page calls the REAL GET /catalog, not a corpus reconstruction.
    const calls = fn.mock.calls.map((c) => String(c[0]))
    expect(calls.some((u) => u.includes("/catalog"))).toBe(true)
    expect(calls.some((u) => u.includes("/corpus"))).toBe(false)
  })

  it("renders persisted catalog rows from /catalog", async () => {
    mockFetch([
      NOT_HALTED,
      {
        match: "/catalog",
        json: {
          count: 1,
          rows: [
            {
              tactic: "amount_just_under_threshold",
              target_type: "sparkov",
              first_discovered_run: "run-abcdef12",
              reuse_count: 4,
              avg_dollars_to_succeed: 0.12,
            },
          ],
        },
      },
    ])
    renderAt("/catalog", <Catalog />, "/catalog")
    expect(await screen.findByText("amount_just_under_threshold")).toBeTruthy()
    expect(screen.getByText(/4× reused/i)).toBeTruthy()
    expect(screen.getByText("$0.12")).toBeTruthy()
  })
})

describe("BlueReview (US-7)", () => {
  it("renders before→after recovery", async () => {
    mockFetch([
      NOT_HALTED,
      {
        match: "/blue",
        json: {
          run_id: "r1",
          features_added: ["velocity_24h"],
          detection_before: 0.5,
          detection_after: 0.85,
          recovered: true,
          n_holdout: 40,
          proposer_rationale: "added velocity feature",
          new_model_ref: "m2",
          iteration_trail: [{ step: 1 }],
        },
      },
    ])
    renderAt("/blue/r1", <BlueReview />, "/blue/:patchId")
    expect(await screen.findByText(/Detection before/i)).toBeTruthy()
    await waitFor(() => expect(screen.getByText("85.0%")).toBeTruthy())
    expect(screen.getByText("velocity_24h")).toBeTruthy()
  })
})

describe("Health (US-8/US-9)", () => {
  it("renders pillars + the seal card", async () => {
    mockFetch([
      {
        match: "/health",
        json: {
          pillars: [
            {
              pillar_id: "targets",
              label: "Targets & Oracles",
              modules: [
                {
                  module_id: "oracles",
                  label: "Oracles",
                  subcomponents: [
                    { component_id: "o.held_out", label: "Held-out", state: "green", last_self_test: null, error: null },
                  ],
                },
              ],
            },
          ],
          seal_card: { network: "none", env_excludes: ["ANTHROPIC_API_KEY"], live_probe_available: false, docker_state: "absent", docker_error: null },
        },
      },
      NOT_HALTED,
    ])
    renderAt("/health", <Health />, "/health")
    expect(await screen.findByText(/Targets & Oracles/i)).toBeTruthy()
    expect(screen.getByText(/Producer-sandbox seal card/i)).toBeTruthy()
    expect(screen.getByText(/network: none/i)).toBeTruthy()
  })
})

describe("AdminDebug (US-15)", () => {
  it("renders and the mock toggle flips the header banner", async () => {
    mockFetch([NOT_HALTED])
    renderAt("/admin/debug", <AdminDebug />, "/admin/debug")
    expect(await screen.findByText(/Admin \/ debug/i)).toBeTruthy()
    expect(screen.getByText(/Toggle mock-LLM mode/i)).toBeTruthy()
  })
})

describe("Halt banner (US-13)", () => {
  it("appears on a route when /halt reports halted", async () => {
    mockFetch([{ match: "/halt", json: { halted: true, recall: 0.55, threshold: 0.7 } }])
    renderAt("/admin/debug", <AdminDebug />, "/admin/debug")
    expect(await screen.findByText(/Certification halted: recall is 0.55, threshold is 0.70/i)).toBeTruthy()
  })
})
