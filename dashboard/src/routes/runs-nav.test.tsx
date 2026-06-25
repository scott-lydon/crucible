// Tests for the runs-list page, the run pickers (Metrics / Blue / Catalog), and
// the chart-recovery path on RunView. Everything runs against a MOCKED API
// client (no backend); the SSE is driven through MockEventSource. These cover
// the critical-path fix: an operator can find a run without memorizing its id,
// pickers default to the newest run, and navigating back to a run repopulates
// the charts from the replayed SSE stream.

import { describe, it, expect, beforeEach } from "vitest"
import { render, screen, waitFor, act, fireEvent } from "@testing-library/react"
import { MemoryRouter, Routes, Route } from "react-router-dom"
import { installEventSource, latestEventSource, mockFetch } from "../test/setup"

import { getRuns } from "../api"
import Runs from "./Runs"
import RunView from "./RunView"
import MetricsView from "./Metrics"
import Catalog from "./Catalog"
import BlueReview from "./BlueReview"

beforeEach(() => {
  installEventSource()
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, value: 600 })
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", { configurable: true, value: 300 })
})

const NOT_HALTED = { match: "/halt", json: { halted: false, recall: 0.9, threshold: 0.7 } }

const RUNS = {
  match: "/runs?limit",
  json: {
    runs: [
      { run_id: "run-newest-1", target: "sparkov", status: "complete", created_at: "2026-06-25T10:00:00", rounds: 3 },
      { run_id: "run-older-22", target: "synth", status: "failed", created_at: "2026-06-24T09:00:00", rounds: 2 },
    ],
  },
}

function renderRoutes(path: string, routes: { path: string; element: React.ReactNode }[]) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        {routes.map((r) => (
          <Route key={r.path} path={r.path} element={r.element} />
        ))}
      </Routes>
    </MemoryRouter>,
  )
}

describe("getRuns() (contract)", () => {
  it("parses the GET /runs contract into RunSummary[]", async () => {
    mockFetch([RUNS])
    const runs = await getRuns()
    expect(runs).toHaveLength(2)
    expect(runs[0]).toMatchObject({ run_id: "run-newest-1", target: "sparkov", status: "complete", rounds: 3 })
    expect(runs[0].created_at).toBe("2026-06-25T10:00:00")
  })
})

describe("Runs list page", () => {
  it("renders one row per run from the mocked GET /runs", async () => {
    mockFetch([NOT_HALTED, RUNS])
    renderRoutes("/runs", [{ path: "/runs", element: <Runs /> }])
    // Short run ids + targets + status pills are rendered from the real contract.
    await waitFor(() => expect(screen.getByText("sparkov")).toBeTruthy())
    expect(screen.getByText("synth")).toBeTruthy()
    expect(screen.getByText("complete")).toBeTruthy()
    expect(screen.getByText("failed")).toBeTruthy()
    // The short run id (first 8 chars) links to the live run view.
    const link = screen.getByText("run-newe")
    expect(link.closest("a")?.getAttribute("href")).toContain("/runs/run-newest-1")
  })

  it("shows the honest empty-state when there are no runs", async () => {
    mockFetch([NOT_HALTED, { match: "/runs?limit", json: { runs: [] } }])
    renderRoutes("/runs", [{ path: "/runs", element: <Runs /> }])
    expect(await screen.findByText(/No runs yet/i)).toBeTruthy()
  })
})

describe("Metrics run picker", () => {
  it("renders picker options, defaults to the newest run, and loads its metrics", async () => {
    const fn = mockFetch([
      NOT_HALTED,
      RUNS,
      { match: "/metrics", json: { status: "Not yet measured" } },
      { match: "/corpus", json: { count: 0, rows: [] } },
    ])
    renderRoutes("/metrics", [{ path: "/metrics", element: <MetricsView /> }])
    // Defaulted to the newest run (run-newest-1) with NO run_id in the URL.
    await waitFor(() => {
      const calls = fn.mock.calls.map((c) => String(c[0]))
      expect(calls.some((u) => u.includes("/runs/run-newest-1/metrics"))).toBe(true)
    })
    // The picker exposes both runs as options.
    const select = (await screen.findByLabelText("Select run")) as HTMLSelectElement
    expect(select.options.length).toBe(2)
  })

  it("navigates to the chosen run on picker change", async () => {
    const fn = mockFetch([
      NOT_HALTED,
      RUNS,
      { match: "/metrics", json: { status: "Not yet measured" } },
      { match: "/corpus", json: { count: 0, rows: [] } },
    ])
    renderRoutes("/metrics", [{ path: "/metrics", element: <MetricsView /> }])
    const select = (await screen.findByLabelText("Select run")) as HTMLSelectElement
    await act(async () => {
      fireEvent.change(select, { target: { value: "run-older-22" } })
    })
    await waitFor(() => {
      const calls = fn.mock.calls.map((c) => String(c[0]))
      expect(calls.some((u) => u.includes("/runs/run-older-22/metrics"))).toBe(true)
    })
  })
})

describe("Catalog run picker", () => {
  it("defaults to the newest run and filters the catalog by its target", async () => {
    const fn = mockFetch([NOT_HALTED, RUNS, { match: "/catalog", json: { count: 0, rows: [] } }])
    renderRoutes("/catalog", [{ path: "/catalog", element: <Catalog /> }])
    // Newest run is sparkov => catalog filtered by target_type=sparkov.
    await waitFor(() => {
      const calls = fn.mock.calls.map((c) => String(c[0]))
      expect(calls.some((u) => u.includes("/catalog?target_type=sparkov"))).toBe(true)
    })
    const select = (await screen.findByLabelText("Select run")) as HTMLSelectElement
    expect(select.options.length).toBe(2)
  })
})

describe("BlueReview run picker", () => {
  it("renders picker options and loads the run's blue round", async () => {
    mockFetch([
      NOT_HALTED,
      RUNS,
      {
        match: "/blue",
        json: {
          run_id: "run-newest-1",
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
    renderRoutes("/blue/run-newest-1", [
      { path: "/blue", element: <BlueReview /> },
      { path: "/blue/:patchId", element: <BlueReview /> },
    ])
    expect(await screen.findByText("velocity_24h")).toBeTruthy()
    const select = (await screen.findByLabelText("Select run")) as HTMLSelectElement
    expect(select.value).toBe("run-newest-1")
    expect(select.options.length).toBe(2)
  })
})

describe("RunView chart recovery (SSE replay on remount)", () => {
  it("repopulates the ASR/detection charts and trace from a replayed stream", async () => {
    mockFetch([NOT_HALTED, { match: "/verdicts", json: { verdicts: [] } }])
    renderRoutes("/runs/run-newest-1", [{ path: "/runs/:id", element: <RunView /> }])

    // Fresh mount starts empty (charts blank), exactly the "navigated back" case.
    expect(await screen.findByText(/0 attack events streamed/i)).toBeTruthy()
    expect(screen.getByText(/0 verdict events streamed/i)).toBeTruthy()

    // The backend SSE replays all persisted frames on a fresh subscribe; emit the
    // replayed attack/verdict/trace frames and assert the charts + trace refill.
    await act(async () => {
      const es = latestEventSource()
      es.emit("attack", { attack_id: "a1", round_id: "rd0", evaded: true, true_label_preserved: true, pre_score: 0.9, post_score: 0.2, asr_so_far: 0.5 })
      es.emit("verdict", { verdict_id: "v1", round_id: "rd0", aggregate_pass: true, fail_weight: 0, detection_rate_so_far: 1 })
      es.emit("trace", { attack_id: "a1", rationale: "amount just under threshold", evidence: {} })
    })

    await waitFor(() => expect(screen.getByText(/1 attack event streamed/i)).toBeTruthy())
    expect(screen.getByText(/1 verdict event streamed/i)).toBeTruthy()
    expect(screen.getByText(/amount just under threshold/i)).toBeTruthy()
  })
})

describe("RunView Stop control + confirm dialog", () => {
  it("opens the confirm dialog on Stop and does NOT call the API until confirmed", async () => {
    const fn = mockFetch([NOT_HALTED, { match: "/verdicts", json: { verdicts: [] } }])
    renderRoutes("/runs/r1", [{ path: "/runs/:id", element: <RunView /> }])
    // A running run shows the Stop button.
    const stopBtn = await screen.findByText("Stop run")
    await act(async () => {
      fireEvent.click(stopBtn)
    })
    // The confirm dialog opened, but NO /stop request fired yet.
    expect(screen.getByRole("dialog")).toBeTruthy()
    expect(screen.getByText(/halt at the next checkpoint/i)).toBeTruthy()
    expect(fn.mock.calls.map((c) => String(c[0])).some((u) => u.includes("/stop"))).toBe(false)
  })

  it("canceling the dialog makes no API call", async () => {
    const fn = mockFetch([NOT_HALTED, { match: "/verdicts", json: { verdicts: [] } }])
    renderRoutes("/runs/r1", [{ path: "/runs/:id", element: <RunView /> }])
    await act(async () => {
      fireEvent.click(await screen.findByText("Stop run"))
    })
    await act(async () => {
      fireEvent.click(screen.getByText("Cancel"))
    })
    expect(screen.queryByRole("dialog")).toBeNull()
    expect(fn.mock.calls.map((c) => String(c[0])).some((u) => u.includes("/stop"))).toBe(false)
  })

  it("confirming calls stopRun and reflects the stopping status (button disabled)", async () => {
    const fn = mockFetch([
      NOT_HALTED,
      { match: "/verdicts", json: { verdicts: [] } },
      { match: "/stop", json: { run_id: "r1", status: "stopping" } },
    ])
    renderRoutes("/runs/r1", [{ path: "/runs/:id", element: <RunView /> }])
    await act(async () => {
      fireEvent.click(await screen.findByText("Stop run"))
    })
    // Confirm — the dialog's own "Stop run" action fires POST /runs/r1/stop.
    const confirm = screen.getAllByText("Stop run").find((el) => el.closest('[role="dialog"]'))!
    await act(async () => {
      fireEvent.click(confirm)
    })
    await waitFor(() => {
      expect(fn.mock.calls.map((c) => String(c[0])).some((u) => u.includes("/runs/r1/stop"))).toBe(true)
    })
    // Status is now "stopping": the button reads "Stopping…" and the dialog closed.
    await waitFor(() => expect(screen.getByText("Stopping…")).toBeTruthy())
    expect(screen.queryByRole("dialog")).toBeNull()
  })
})

const RUNS_WITH_RUNNING = {
  match: "/runs?limit",
  json: {
    runs: [
      { run_id: "run-live-001", target: "sparkov", status: "running", created_at: "2026-06-25T11:00:00", rounds: 3 },
      { run_id: "run-stop-002", target: "synth", status: "stopped", created_at: "2026-06-24T09:00:00", rounds: 2 },
    ],
  },
}

describe("Runs-list Stop action + stopped pill", () => {
  it("renders 'stopped' as a terminal pill and offers Stop only on running rows", async () => {
    mockFetch([NOT_HALTED, RUNS_WITH_RUNNING])
    renderRoutes("/runs", [{ path: "/runs", element: <Runs /> }])
    // The stopped run renders its status pill (terminal — no Stop action).
    await waitFor(() => expect(screen.getByText("stopped")).toBeTruthy())
    expect(screen.getByText("running")).toBeTruthy()
    // Exactly one Stop action: only the running row gets it.
    expect(screen.getAllByText("Stop")).toHaveLength(1)
  })

  it("confirms before stopping a running row and then calls stopRun", async () => {
    const fn = mockFetch([NOT_HALTED, RUNS_WITH_RUNNING, { match: "/stop", json: { run_id: "run-live-001", status: "stopping" } }])
    renderRoutes("/runs", [{ path: "/runs", element: <Runs /> }])
    const stop = await screen.findByText("Stop")
    await act(async () => {
      fireEvent.click(stop)
    })
    // Dialog opened, no call yet.
    expect(screen.getByRole("dialog")).toBeTruthy()
    expect(fn.mock.calls.map((c) => String(c[0])).some((u) => u.includes("/stop"))).toBe(false)
    const confirm = screen.getAllByText("Stop run").find((el) => el.closest('[role="dialog"]'))!
    await act(async () => {
      fireEvent.click(confirm)
    })
    await waitFor(() => {
      expect(fn.mock.calls.map((c) => String(c[0])).some((u) => u.includes("/runs/run-live-001/stop"))).toBe(true)
    })
  })
})
