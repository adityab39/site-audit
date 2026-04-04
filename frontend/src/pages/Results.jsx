import { lazy, Suspense } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useAuditPolling } from '../hooks/useAuditPolling'
import ScoreRing from '../components/ScoreRing'
import CategoryCard from '../components/CategoryCard'
import PriorityFixes from '../components/PriorityFixes'
import LoadingSteps from '../components/LoadingSteps'

const ScoreRadar = lazy(() => import('../components/ScoreRadar'))

// ─── Constants ───────────────────────────────────────────────────────────────

const CATEGORY_META = {
  copy_messaging:    { label: 'Copy & Messaging' },
  seo_health:        { label: 'SEO Health' },
  performance:       { label: 'Performance' },
  design_ux:         { label: 'Design & UX' },
  trust_credibility: { label: 'Trust & Credibility' },
  accessibility:     { label: 'Accessibility' },
}

const CATEGORY_ORDER = [
  'copy_messaging', 'seo_health', 'performance',
  'design_ux', 'trust_credibility', 'accessibility',
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function displayUrl(raw) {
  try { return new URL(raw).hostname }
  catch { return raw }
}

function ScoreLabel({ score }) {
  if (score == null) return null
  const { text, cls } =
    score >= 75 ? { text: 'Great',      cls: 'text-green-400  bg-green-500/10  border-green-500/20' }
    : score >= 50 ? { text: 'Needs Work', cls: 'text-yellow-400 bg-yellow-500/10 border-yellow-500/20' }
    :               { text: 'Poor',       cls: 'text-red-400    bg-red-500/10    border-red-500/20' }
  return <span className={`badge border text-sm font-semibold ${cls}`}>{text}</span>
}

// ─── Lighthouse metrics row ───────────────────────────────────────────────────

function LighthouseMetrics({ lighthouse }) {
  if (!lighthouse || lighthouse.error) return null

  const metrics = [
    { label: 'LCP',        value: lighthouse.largest_contentful_paint_ms != null ? `${(lighthouse.largest_contentful_paint_ms / 1000).toFixed(1)}s` : '—' },
    { label: 'TBT',        value: lighthouse.total_blocking_time_ms       != null ? `${lighthouse.total_blocking_time_ms}ms`                         : '—' },
    { label: 'CLS',        value: lighthouse.cumulative_layout_shift       != null ? lighthouse.cumulative_layout_shift.toFixed(3)                    : '—' },
    { label: 'FCP',        value: lighthouse.first_contentful_paint_ms    != null ? `${(lighthouse.first_contentful_paint_ms / 1000).toFixed(1)}s`   : '—' },
    { label: 'Speed Idx',  value: lighthouse.speed_index_ms               != null ? `${(lighthouse.speed_index_ms / 1000).toFixed(1)}s`              : '—' },
    { label: 'Page Size',  value: lighthouse.total_byte_weight_kb         != null ? `${(lighthouse.total_byte_weight_kb / 1024).toFixed(1)} MB`       : '—' },
  ]

  return (
    <div className="grid grid-cols-3 sm:grid-cols-6 gap-3">
      {metrics.map((m) => (
        <div key={m.label} className="glass-card border border-zinc-800 p-3 text-center rounded-xl">
          <p className="text-[11px] text-zinc-500 mb-1 uppercase tracking-wider">{m.label}</p>
          <p className="text-sm font-bold text-zinc-200">{m.value}</p>
        </div>
      ))}
    </div>
  )
}

// ─── Shared nav bar ───────────────────────────────────────────────────────────

function NavBar({ onBack, right }) {
  return (
    <nav className="sticky top-0 z-10 bg-zinc-950/80 backdrop-blur-md border-b border-zinc-800/50 flex items-center justify-between px-4 sm:px-6 py-3">
      <button
        onClick={onBack}
        className="flex items-center gap-1.5 text-zinc-500 hover:text-zinc-300 transition-colors text-sm"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Back
      </button>
      {right}
    </nav>
  )
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function Results() {
  const { jobId } = useParams()
  const navigate  = useNavigate()
  const { data, error } = useAuditPolling(jobId)

  const isProcessing = !data || (data.status !== 'completed' && data.status !== 'failed')
  const isFailed     = data?.status === 'failed'

  // Error fetching the job
  if (error) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-4">
        <div className="text-center max-w-sm">
          <div className="w-12 h-12 mx-auto mb-5 rounded-xl bg-red-500/10 border border-red-500/20 flex items-center justify-center">
            <svg className="w-6 h-6 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
            </svg>
          </div>
          <h2 className="text-xl font-semibold text-zinc-100 mb-2">Could not load audit</h2>
          <p className="text-zinc-500 text-sm mb-6">{error}</p>
          <button
            onClick={() => navigate('/')}
            className="bg-violet-600 hover:bg-violet-500 text-white px-5 py-2.5 rounded-xl font-medium transition-colors"
          >
            Go Home
          </button>
        </div>
      </div>
    )
  }

  // Processing / loading state
  if (isProcessing) {
    const urlDisplay = data?.url ? displayUrl(data.url) : 'your site'
    return (
      <div className="min-h-screen bg-zinc-950 flex flex-col">
        <div className="fixed inset-0 pointer-events-none">
          <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-96 h-96 bg-violet-600/8 rounded-full blur-3xl" />
        </div>

        <NavBar onBack={() => navigate('/')} />

        <div className="flex-1 flex items-center justify-center p-6">
          <div className="w-full max-w-md animate-fade-in">
            {/* Pulsing icon */}
            <div className="flex justify-center mb-8">
              <div className="relative">
                <div className="w-14 h-14 rounded-2xl bg-violet-600/15 border border-violet-500/25 flex items-center justify-center">
                  <svg className="w-6 h-6 text-violet-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 15.803a7.5 7.5 0 0010.607 0z" />
                  </svg>
                </div>
                <div className="absolute inset-0 rounded-2xl bg-violet-600/15 animate-ping" />
              </div>
            </div>

            <h2 className="text-xl font-semibold text-center text-zinc-100 mb-1">
              Auditing <span className="text-violet-400">{urlDisplay}</span>
            </h2>
            <p className="text-center text-zinc-500 text-sm mb-8">
              This typically takes 30–60 seconds
            </p>

            <LoadingSteps />
          </div>
        </div>
      </div>
    )
  }

  // Failed state
  if (isFailed) {
    return (
      <div className="min-h-screen bg-zinc-950 flex flex-col">
        <NavBar onBack={() => navigate('/')} />
        <div className="flex-1 flex items-center justify-center p-6">
          <div className="text-center max-w-sm">
            <div className="w-12 h-12 mx-auto mb-5 rounded-xl bg-red-500/10 border border-red-500/20 flex items-center justify-center">
              <svg className="w-6 h-6 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h2 className="text-xl font-semibold text-zinc-100 mb-2">Audit Failed</h2>
            <p className="text-zinc-500 text-sm mb-2">
              We couldn't analyze <span className="text-zinc-300">{displayUrl(data.url)}</span>.
            </p>
            <p className="text-zinc-600 text-xs mb-8">
              The site may be unreachable or blocked crawler access.
            </p>
            <button
              onClick={() => navigate('/')}
              className="bg-violet-600 hover:bg-violet-500 text-white px-5 py-2.5 rounded-xl font-medium transition-colors"
            >
              Try Another Site
            </button>
          </div>
        </div>
      </div>
    )
  }

  // ─── Results ───────────────────────────────────────────────────────────────

  const analysis     = data.results?.analysis ?? {}
  const lighthouse   = data.results?.lighthouse ?? {}
  const priorityFixes = analysis.priority_fixes ?? []

  const rawCategories = data.category_scores?.length
    ? data.category_scores
    : Object.entries(analysis.categories ?? {}).map(([key, val]) => ({
        category: key,
        score:    val.score,
        label:    val.score >= 8 ? 'Good' : val.score >= 5 ? 'Needs Improvement' : 'Poor',
        details:  { findings: val.findings ?? [] },
      }))

  const categories  = CATEGORY_ORDER.map((k) => rawCategories.find((c) => c.category === k)).filter(Boolean)
  const overallScore = data.overall_score ?? analysis.overall_score ?? 0
  const summary      = data.ai_summary ?? analysis.summary ?? ''
  const auditUrl     = data.url ?? ''

  return (
    <div className="min-h-screen bg-zinc-950 pb-20">
      {/* Background glow */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-64 bg-violet-600/5 blur-3xl" />
      </div>

      <NavBar onBack={() => navigate('/')} />

      <div className="max-w-3xl mx-auto px-4 sm:px-6 pt-10 space-y-10">

        {/* ── Hero ─────────────────────────────────────────────────────── */}
        <section className="animate-fade-in">
          {/* URL link */}
          <a
            href={auditUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 text-zinc-300 hover:text-white font-medium text-lg transition-colors group mb-8"
          >
            <span className="w-6 h-6 rounded-md bg-zinc-800 border border-zinc-700 flex items-center justify-center flex-shrink-0">
              <svg className="w-3.5 h-3.5 text-zinc-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
              </svg>
            </span>
            <span className="group-hover:underline underline-offset-2">{displayUrl(auditUrl)}</span>
            <svg className="w-3.5 h-3.5 text-zinc-600 group-hover:text-zinc-400 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
          </a>

          <div className="flex flex-col sm:flex-row items-center sm:items-start gap-8">
            {/* Score ring */}
            <div className="flex flex-col items-center gap-3 flex-shrink-0">
              <ScoreRing score={overallScore} size={160} strokeWidth={12} />
              <ScoreLabel score={overallScore} />
            </div>

            {/* AI Summary */}
            <div className="flex-1 min-w-0">
              <p className="text-xs text-zinc-500 font-medium uppercase tracking-wider mb-3">AI Summary</p>
              <p className="text-zinc-300 leading-relaxed text-sm sm:text-base">
                {summary || 'Analysis complete. See category scores below for details.'}
              </p>
            </div>
          </div>
        </section>

        {/* ── Score Radar ───────────────────────────────────────────────── */}
        {categories.length > 0 && (
          <section className="glass-card border border-zinc-800 p-5 rounded-2xl animate-slide-up">
            <h2 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-4">Score Overview</h2>
            <Suspense fallback={
              <div className="h-64 flex items-center justify-center text-zinc-600 text-sm">
                Loading chart…
              </div>
            }>
              <ScoreRadar categoryScores={categories} />
            </Suspense>
          </section>
        )}

        {/* ── Core Web Vitals ───────────────────────────────────────────── */}
        {lighthouse && !lighthouse.error && (
          <section className="animate-slide-up">
            <h2 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-3">Core Web Vitals</h2>
            <LighthouseMetrics lighthouse={lighthouse} />
          </section>
        )}

        {/* ── Category Scores ───────────────────────────────────────────── */}
        {categories.length > 0 && (
          <section className="animate-slide-up">
            <h2 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-4">Category Scores</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {categories.map((cs) => {
                const meta     = CATEGORY_META[cs.category] ?? { label: cs.category }
                const findings = cs.details?.findings ?? []
                return (
                  <CategoryCard
                    key={cs.category}
                    name={meta.label}
                    score={cs.score}
                    label={cs.label}
                    findings={findings}
                  />
                )
              })}
            </div>
          </section>
        )}

        {/* ── Priority Fixes ────────────────────────────────────────────── */}
        {priorityFixes.length > 0 && (
          <section className="animate-slide-up">
            <div className="flex items-center gap-2 mb-4">
              <h2 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">Priority Fixes</h2>
              <span className="badge bg-violet-500/10 text-violet-400 border border-violet-500/20 text-xs">
                {priorityFixes.length} actions
              </span>
            </div>
            <PriorityFixes fixes={priorityFixes} />
          </section>
        )}

        {/* ── Footer ───────────────────────────────────────────────────── */}
        <section className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-4 border-t border-zinc-800">
          <span className="text-xs text-zinc-600">
            Analyzed {new Date(data.completed_at ?? data.created_at).toLocaleString()}
          </span>
          <Link
            to="/"
            className="bg-violet-600 hover:bg-violet-500 text-white font-semibold px-6 py-3 rounded-xl transition-colors text-sm flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
            Analyze Another Site
          </Link>
        </section>

      </div>
    </div>
  )
}
