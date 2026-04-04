const CATEGORY_LABELS = {
  copy_messaging:    'Copy',
  seo_health:        'SEO',
  performance:       'Performance',
  design_ux:         'Design',
  trust_credibility: 'Trust',
  accessibility:     'Accessibility',
}

const IMPACT_STYLE = {
  high:   'bg-red-500/15 text-red-400 border-red-500/30',
  medium: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  low:    'bg-blue-500/15 text-blue-400 border-blue-500/30',
}

const EFFORT_STYLE = {
  quick:       'bg-green-500/15 text-green-400 border-green-500/30',
  medium:      'bg-zinc-700/50 text-zinc-400 border-zinc-600/30',
  significant: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
}

export default function PriorityFixes({ fixes = [] }) {
  if (!fixes.length) return null

  return (
    <div className="space-y-3">
      {fixes.map((fix, idx) => {
        const impact   = fix.impact?.toLowerCase() || 'medium'
        const effort   = fix.effort?.toLowerCase() || 'medium'
        const catLabel = CATEGORY_LABELS[fix.category] || fix.category

        return (
          <div
            key={idx}
            className="flex items-start gap-4 p-4 glass-card border border-zinc-800 rounded-xl animate-slide-up"
            style={{ animationDelay: `${idx * 60}ms` }}
          >
            {/* Rank number */}
            <div className="flex-shrink-0 w-8 h-8 rounded-full bg-violet-500/10 border border-violet-500/20 flex items-center justify-center">
              <span className="text-xs font-bold text-violet-400">{fix.rank ?? idx + 1}</span>
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                <span className="badge bg-zinc-800 text-zinc-400 text-xs">{catLabel}</span>
                <span className="text-sm font-medium text-zinc-100">{fix.title}</span>
              </div>
              {fix.description && (
                <p className="text-xs text-zinc-500 mb-2 leading-relaxed">{fix.description}</p>
              )}
              <div className="flex gap-2 flex-wrap">
                <span className={`badge border ${IMPACT_STYLE[impact] || IMPACT_STYLE.medium}`}>
                  {impact} impact
                </span>
                <span className={`badge border ${EFFORT_STYLE[effort] || EFFORT_STYLE.medium}`}>
                  {effort} effort
                </span>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
