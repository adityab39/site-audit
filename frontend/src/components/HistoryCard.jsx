import { useNavigate } from 'react-router-dom'

function ScorePill({ score }) {
  if (score == null) return <span className="badge bg-zinc-800 text-zinc-500">—</span>
  const color =
    score >= 75 ? 'bg-green-500/15 text-green-400 border-green-500/30'
    : score >= 50 ? 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30'
    : 'bg-red-500/15 text-red-400 border-red-500/30'
  return (
    <span className={`badge border font-bold ${color}`}>
      {score}<span className="font-normal opacity-60">/100</span>
    </span>
  )
}

function relativeTime(iso) {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

function ModePill({ mode }) {
  return mode === 'roast'
    ? <span className="badge bg-orange-500/10 text-orange-400 border border-orange-500/20 text-[10px]">Roast</span>
    : <span className="badge bg-zinc-800 text-zinc-500 text-[10px]">Pro</span>
}

export default function HistoryCard({ audit }) {
  const navigate = useNavigate()
  const domain = (() => {
    try { return new URL(audit.url).hostname }
    catch { return audit.url }
  })()

  return (
    <button
      onClick={() => navigate(`/audit/${audit.job_id}`)}
      className="w-full flex items-center gap-3 px-4 py-3 bg-zinc-900/60 border border-zinc-800 rounded-xl hover:border-violet-500/40 hover:bg-zinc-900 transition-all duration-150 text-left group"
    >
      <ModePill mode={audit.mode} />

      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-zinc-200 truncate group-hover:text-white transition-colors">
          {domain}
        </p>
        <p className="text-xs text-zinc-500 truncate">{audit.url}</p>
      </div>

      <div className="flex items-center gap-3 flex-shrink-0">
        <ScorePill score={audit.overall_score} />
        <span className="text-xs text-zinc-600 hidden sm:block">{relativeTime(audit.created_at)}</span>
      </div>

      <svg
        className="w-4 h-4 text-zinc-600 group-hover:text-zinc-400 transition-colors flex-shrink-0"
        fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
      >
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
      </svg>
    </button>
  )
}
