// Vitest test harness shared mocks. No real backend or browser EventSource is
// available under jsdom, so we provide a controllable MockEventSource and a
// default fetch stub. Individual tests override fetch / drive the EventSource.

import { afterEach, vi } from "vitest"
import { cleanup } from "@testing-library/react"

export type SseFrame = { event: string; data: unknown }

// A minimal, drivable EventSource. Tests grab the latest instance from
// `mockEventSources` and call `emit(event, data)` to push a frame.
export class MockEventSource {
  static instances: MockEventSource[] = []
  url: string
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {}
  onerror: ((e: Event) => void) | null = null
  closed = false

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }
  addEventListener(type: string, cb: (e: MessageEvent) => void) {
    ;(this.listeners[type] ??= []).push(cb)
  }
  emit(event: string, data: unknown) {
    const ev = { data: JSON.stringify(data) } as MessageEvent
    for (const cb of this.listeners[event] ?? []) cb(ev)
  }
  close() {
    this.closed = true
  }
}

export function latestEventSource(): MockEventSource {
  const es = MockEventSource.instances[MockEventSource.instances.length - 1]
  if (!es) throw new Error("no EventSource was created")
  return es
}

export function installEventSource() {
  MockEventSource.instances = []
  ;(globalThis as unknown as { EventSource: unknown }).EventSource = MockEventSource as unknown
}

// A fetch stub keyed by URL substring. Returns 404 for anything unmatched so
// routes exercise their honest empty/not-found states by default.
export function mockFetch(routes: { match: string; status?: number; json?: unknown; text?: string }[]) {
  const fn = vi.fn(async (input: RequestInfo | URL) => {
    const u = typeof input === "string" ? input : input.toString()
    const hit = routes.find((r) => u.includes(r.match))
    if (!hit) return new Response(null, { status: 404 })
    const status = hit.status ?? 200
    if (hit.text !== undefined) return new Response(hit.text, { status })
    return new Response(JSON.stringify(hit.json ?? {}), {
      status,
      headers: { "Content-Type": "application/json" },
    })
  })
  globalThis.fetch = fn as unknown as typeof fetch
  return fn
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  MockEventSource.instances = []
})
