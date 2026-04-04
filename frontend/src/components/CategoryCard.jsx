import { useState } from 'react'
import { MiniScoreRing } from './ScoreRing'

const SEVERITY_STYLES = {
  critical: {
    badge:      'bg-red-500/15 text-red-400 border-red-500/30',
    leftBorder: 'border-l-red-500',
    recBg:      'bg-red-500/5 border-red-500/15',
    label:      'Critical',
  },
  warning: {
    badge:      'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
    leftBorder: 'border-l-yellow-500',
    recBg:      'bg-yellow-500/5 border-yellow-500/15',
    label:      'Warning',
  },
  info: {
    badge:      'bg-blue-500/15 text-blue-400 border-blue-500/30',
    leftBorder: 'border-l-blue-500',
    recBg:      'bg-blue-500/5 border-blue-500/15',
    label:      'Info',
  },
}

const SCORE_BORDER = (s) =>
  s >= 8 ? 'border-green-500/20 hover:border-green-500/40'
  : s >= 5 ? 'border-yellow-500/20 hover:border-yellow-500/40'
  : 'border-red-500/20 hover:border-red-500/40'

const SCORE_LABEL_STYLE = (s) =>
  s >= 8 ? 'bg-green-500/15 text-green-400'
  : s >= 5 ? 'bg-yellow-500/15 text-yellow-400'
  : 'bg-red-500/15 text-red-400'

function FindingItem({ finding }) {
  const sev = SEVERITY_STYLES[finding.severity] ?? SEVERITY_STYLES.info

  return (
    <div className={`border-l-2 ${sev.leftBorder} pl-3 py-3 border-b border-zinc-800/60 last:border-b-0`}>
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <span className="text-sm font-medium text-zinc-200 leading-snug">{finding.title}</span>
        <span className={`badge border flex-shrink-0 ${sev.badge}`}>{sev.label}</span>
      </div>

      {finding.description && (
        <p className="text-xs text-zinc-400 mb-2 leading-relaxed">{finding.description}</p>
      )}

      {finding.recommendation && (
        <div className={`rounded-lg px-3 py-2 border ${sev.recBg}`}>
          <p className="text-xs text-zinc-300 leading-relaxed">{finding.recommendation}</p>
        </div>
      )}
    </div>
  )
}

export default function CategoryCard({ name, score, label, findings = [] }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className={`glass-card border transition-all duration-200 overflow-hidden ${SCORE_BORDER(score)}`}>
      {/* Header */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-4 p-4 text-left"
      >
        <MiniScoreRing score10={score} size={64} />

        <div className="flex-1 min-w-0">
          <p className="font-semibold text-sm text-zinc-100 truncate mb-1.5">{name}</p>
          <span className={`badge ${SCORE_LABEL_STYLE(score)}`}>{label}</span>
        </div>

        <div className="flex flex-col items-end gap-0.5 flex-shrink-0">
          {findings.length > 0 && (
            <span className="text-xs text-zinc-500">{findings.length} findings</span>
          )}
          <svg
            className={`w-4 h-4 text-zinc-500 transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {/* Expanded findings */}
      {expanded && (
        <div className="px-4 pb-4 animate-fade-in">
          <div className="border-t border-zinc-800/60 pt-2 space-y-0">
            {findings.length === 0 ? (
              <p className="text-sm text-zinc-500 py-3 text-center">No findings recorded.</p>
            ) : (
              findings.map((f, i) => <FindingItem key={i} finding={f} />)
            )}
          </div>
        </div>
      )}
    </div>
  )
}
