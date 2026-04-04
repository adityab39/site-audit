import {
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip,
} from 'recharts'

const CATEGORY_SHORT = {
  copy_messaging: 'Copy',
  seo_health: 'SEO',
  performance: 'Speed',
  design_ux: 'Design',
  trust_credibility: 'Trust',
  accessibility: 'A11y',
}

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="text-zinc-400 mb-0.5">{d.fullName}</p>
      <p className="text-white font-bold">{d.score} / 10</p>
    </div>
  )
}

export default function ScoreRadar({ categoryScores = [] }) {
  const data = categoryScores.map((cs) => ({
    category: CATEGORY_SHORT[cs.category] || cs.category,
    fullName: cs.category.replace(/_/g, ' '),
    score: cs.score,
    fullMark: 10,
  }))

  if (!data.length) return null

  return (
    <ResponsiveContainer width="100%" height={260}>
      <RadarChart data={data} margin={{ top: 10, right: 30, bottom: 10, left: 30 }}>
        <PolarGrid stroke="#3f3f46" strokeDasharray="3 3" />
        <PolarAngleAxis
          dataKey="category"
          tick={{ fill: '#a1a1aa', fontSize: 11, fontWeight: 500 }}
        />
        <PolarRadiusAxis
          domain={[0, 10]}
          tick={{ fill: '#71717a', fontSize: 9 }}
          tickCount={3}
          axisLine={false}
        />
        <Radar
          dataKey="score"
          stroke="#8b5cf6"
          fill="#8b5cf6"
          fillOpacity={0.4}
          strokeWidth={2}
          dot={{ fill: '#8b5cf6', r: 3 }}
        />
        <Tooltip content={<CustomTooltip />} />
      </RadarChart>
    </ResponsiveContainer>
  )
}
