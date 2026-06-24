// US-8 / US-9: Platform Health. Renders the hierarchical self-test view
// (pillar → module → subcomponent, each leaf {state, last_self_test, error})
// plus the producer-sandbox seal card. States are honest: green / amber / red —
// we render whatever the backend reports, never fabricate green.

import { useEffect, useState } from "react"
import { getHealth } from "../api"
import Layout from "../components/Layout"
import { Card, Mono, Pill, SectionLabel } from "../components/ui"
import { C, MONO } from "../theme"

type Leaf = { component_id: string; label: string; state: string; last_self_test: string | null; error: string | null }
type Module = { module_id: string; label: string; subcomponents: Leaf[] }
type Pillar = { pillar_id: string; label: string; modules: Module[] }
type SealCard = {
  network?: string
  env_excludes?: string[]
  live_probe_available?: boolean
  docker_state?: string | null
  docker_error?: string | null
}
type HealthDoc = { pillars: Pillar[]; seal_card: SealCard }

function stateTone(s: string): "pass" | "warn" | "fail" | "neutral" {
  const v = s.toLowerCase()
  if (v.includes("green") || v === "ok" || v === "healthy") return "pass"
  if (v.includes("amber") || v.includes("warn")) return "warn"
  if (v.includes("red") || v.includes("fail")) return "fail"
  return "neutral"
}

export default function Health() {
  const [doc, setDoc] = useState<HealthDoc | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getHealth()
      .then((d) => setDoc(d as unknown as HealthDoc))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load health"))
  }, [])

  return (
    <Layout>
      <SectionLabel>Platform Health · US-8 / US-9</SectionLabel>
      <h1 style={{ color: C.textHi, fontSize: 22, fontWeight: 600, margin: "0 0 16px" }}>Hierarchical self-test</h1>

      {error && <Card style={{ borderColor: C.danger }}><span style={{ color: C.danger }}>{error}</span></Card>}
      {!doc && !error && <p style={{ color: C.textMut }}>Running smoke tests…</p>}

      {doc && (
        <>
          {doc.pillars.map((p) => (
            <div key={p.pillar_id} style={{ marginBottom: 24 }}>
              <SectionLabel>{p.label}</SectionLabel>
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {p.modules.map((m) => (
                  <Card key={m.module_id}>
                    <div style={{ color: C.textHi, fontWeight: 600, fontSize: 14, marginBottom: 10 }}>{m.label}</div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      {m.subcomponents.map((c) => (
                        <div
                          key={c.component_id}
                          style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}
                        >
                          <Pill tone={stateTone(c.state)}>{c.state}</Pill>
                          <span style={{ fontSize: 13, color: C.text }}>{c.label}</span>
                          {c.error && (
                            <Mono style={{ fontSize: 11, color: C.textMut }}>{c.error}</Mono>
                          )}
                        </div>
                      ))}
                    </div>
                  </Card>
                ))}
              </div>
            </div>
          ))}

          <SectionLabel>Producer-sandbox seal card · US-9</SectionLabel>
          <Card>
            <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 12, flexWrap: "wrap" }}>
              <Pill tone={doc.seal_card.network === "none" ? "pass" : "fail"}>
                network: {doc.seal_card.network ?? "?"}
              </Pill>
              <Pill tone={doc.seal_card.live_probe_available ? "pass" : "warn"}>
                live probe {doc.seal_card.live_probe_available ? "available" : "unavailable"}
              </Pill>
              {doc.seal_card.docker_state && (
                <Mono style={{ fontSize: 11, color: C.textMut }}>docker: {doc.seal_card.docker_state}</Mono>
              )}
            </div>
            <div style={{ fontSize: 12, color: C.textMut, marginBottom: 6 }}>The producer container inherits none of:</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {(doc.seal_card.env_excludes ?? []).map((e) => (
                <Mono key={e} style={{ fontSize: 12, color: C.text }}>
                  ✕ {e}
                </Mono>
              ))}
            </div>
            {doc.seal_card.docker_error && (
              <p style={{ fontFamily: MONO, fontSize: 11, color: C.warning, marginTop: 10 }}>{doc.seal_card.docker_error}</p>
            )}
          </Card>
        </>
      )}
    </Layout>
  )
}
