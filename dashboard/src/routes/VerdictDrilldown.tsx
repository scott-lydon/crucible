import { useEffect, useState } from "react"
import { useParams } from "react-router-dom"

type Vote = {
  oracle: string
  vote: string
  weight: number
  reason: string
  is_stub: boolean
  is_mock: boolean
}

export default function VerdictDrilldown() {
  const { id, vid } = useParams<{ id: string; vid: string }>()
  const [votes, setVotes] = useState<Vote[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id || !vid) return
    fetch(`/api/runs/${id}/verdicts/${vid}`)
      .then((r) => r.json())
      .then((data) => setVotes(data.votes))
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load"))
  }, [id, vid])

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-red-500 text-sm">{error}</p>
      </div>
    )
  }

  if (!votes) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-500 text-sm">Loading…</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <h1 className="text-xl font-semibold text-gray-800 mb-6">
        Verdict: {vid}
      </h1>
      <div className="space-y-3 max-w-2xl">
        {votes.map((v, i) => (
          <div key={i} className="bg-white rounded-lg shadow-sm p-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="font-medium text-gray-800 text-sm">{v.oracle}</span>
              {v.is_stub && (
                <span className="text-xs bg-gray-200 text-gray-600 px-1.5 py-0.5 rounded">
                  STUB
                </span>
              )}
              {v.is_mock && (
                <span
                  className="text-xs bg-yellow-100 text-yellow-700 px-1.5 py-0.5 rounded"
                  title="One vote; not a real LLM judge"
                >
                  MOCK · one vote
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-sm text-gray-700 font-medium">{v.vote}</span>
              <span className="text-xs text-gray-400">weight: {v.weight}</span>
            </div>
            <p className="text-sm text-gray-600">{v.reason}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
