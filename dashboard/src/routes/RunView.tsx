import { useEffect, useState } from "react"
import { useParams } from "react-router-dom"
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from "recharts"
import { getMetrics, isNotMeasured, type Metrics } from "../api"

export default function RunView() {
  const { id } = useParams<{ id: string }>()
  const [metrics, setMetrics] = useState<Metrics | null>(null)

  useEffect(() => {
    if (!id) return
    const timer = setInterval(async () => {
      try {
        const m = await getMetrics(id)
        setMetrics(m)
      } catch {
        // keep polling
      }
    }, 1000)
    return () => clearInterval(timer)
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

      <div className="bg-white rounded-lg shadow-sm p-4 inline-block">
        <LineChart width={600} height={300} data={chartData}>
          <XAxis dataKey="round" />
          <YAxis domain={[0, 1]} />
          <Tooltip />
          <Legend />
          <Line type="monotone" dataKey="evasion" stroke="#dc2626" dot={false} />
          <Line type="monotone" dataKey="detection" stroke="#2563eb" dot={false} />
        </LineChart>
      </div>
    </div>
  )
}
