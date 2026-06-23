import { useEffect, useRef, useState } from "react"
import { useParams, Link } from "react-router-dom"
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from "recharts"
import { getMetrics, getVerdicts, isNotMeasured, type Metrics, type VerdictSummary } from "../api"

const VERDICT_PAGE_SIZE = 50

export default function RunView() {
  const { id } = useParams<{ id: string }>()
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [verdicts, setVerdicts] = useState<VerdictSummary[] | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!id) return
    timerRef.current = setInterval(async () => {
      try {
        const m = await getMetrics(id)
        setMetrics(m)
        // Stop polling once we have a real metrics payload
        if (!isNotMeasured(m)) {
          if (timerRef.current !== null) {
            clearInterval(timerRef.current)
            timerRef.current = null
          }
        }
      } catch {
        // keep polling on error
      }
    }, 1000)
    return () => {
      if (timerRef.current !== null) {
        clearInterval(timerRef.current)
      }
    }
  }, [id])

  useEffect(() => {
    if (!id) return
    getVerdicts(id).then(setVerdicts)
  }, [id])

  if (!metrics) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-500 text-sm">Loading…</p>
      </div>
    )
  }

  if (isNotMeasured(metrics)) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-400 text-sm">Not yet measured.</p>
      </div>
    )
  }

  const chartData = metrics.per_round.map((r) => ({
    round: r.round_index,
    evasion: r.evasion_rate,
    detection: r.detection_rate,
  }))

  const firstAsr = metrics.per_round[0]?.asr

  const shownVerdicts = verdicts ? verdicts.slice(0, VERDICT_PAGE_SIZE) : []

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <h1 className="text-xl font-semibold text-gray-800 mb-6">Run: {id}</h1>

      <div className="grid grid-cols-2 gap-4 mb-8 max-w-lg">
        <div className="bg-white rounded-lg shadow-sm p-4">
          <p className="text-xs text-gray-500 mb-1">Validation-vs-held-out gap</p>
          <p className="text-lg font-semibold text-gray-800">
            {metrics.gap === null ? "Not yet measured" : metrics.gap.toFixed(2)}
          </p>
        </div>
        <div className="bg-white rounded-lg shadow-sm p-4">
          <p className="text-xs text-gray-500 mb-1">Attack success (round 0, per attempt)</p>
          <p className="text-lg font-semibold text-gray-800">
            {firstAsr == null ? "Not yet measured" : (firstAsr * 100).toFixed(0) + "%"}
          </p>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow-sm p-4 inline-block mb-8">
        <LineChart width={600} height={300} data={chartData}>
          <XAxis dataKey="round" />
          <YAxis domain={[0, 1]} />
          <Tooltip />
          <Legend />
          <Line type="monotone" dataKey="evasion" stroke="#dc2626" dot={false} />
          <Line type="monotone" dataKey="detection" stroke="#2563eb" dot={false} />
        </LineChart>
      </div>

      <div className="max-w-2xl">
        <h2 className="text-base font-semibold text-gray-800 mb-3">Verdicts</h2>
        {verdicts === null ? (
          <p className="text-gray-400 text-sm">Loading verdicts…</p>
        ) : verdicts.length === 0 ? (
          <p className="text-gray-400 text-sm">No verdicts recorded.</p>
        ) : (
          <>
            {verdicts.length > VERDICT_PAGE_SIZE && (
              <p className="text-xs text-gray-400 mb-2">
                showing first {VERDICT_PAGE_SIZE} of {verdicts.length}
              </p>
            )}
            <table className="w-full text-sm bg-white rounded-lg shadow-sm overflow-hidden">
              <thead className="bg-gray-100 text-gray-600 text-xs uppercase">
                <tr>
                  <th className="px-4 py-2 text-left">Verdict ID</th>
                  <th className="px-4 py-2 text-left">Result</th>
                  <th className="px-4 py-2 text-left">Fail Weight</th>
                </tr>
              </thead>
              <tbody>
                {shownVerdicts.map((v) => (
                  <tr key={v.verdict_id} className="border-t border-gray-100 hover:bg-gray-50">
                    <td className="px-4 py-2 font-mono">
                      <Link
                        to={`/runs/${id}/verdicts/${v.verdict_id}`}
                        className="text-blue-600 hover:underline"
                      >
                        {v.verdict_id.slice(0, 8)}
                      </Link>
                    </td>
                    <td className="px-4 py-2">
                      {v.aggregate_pass ? (
                        <span className="text-green-700 font-medium">sound</span>
                      ) : (
                        <span className="text-red-600 font-medium">MISSED</span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-gray-600">{v.fail_weight.toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    </div>
  )
}
