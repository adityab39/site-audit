import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { submitAudit, getHistory } from '../api/audit'
import HistoryCard from '../components/HistoryCard'

const PLACEHOLDERS = [
  'stripe.com',
  'linear.app',
  'vercel.com',
  'notion.so',
  'yoursite.com',
]

const FEATURES = [
  {
    title: 'Performance',
    desc: 'Core Web Vitals, LCP, CLS, TBT — measured via Lighthouse.',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
      </svg>
    ),
  },
  {
    title: 'SEO Health',
    desc: 'Meta tags, headings, Open Graph, canonical URLs and more.',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 15.803a7.5 7.5 0 0010.607 0z" />
      </svg>
    ),
  },
  {
    title: 'Accessibility',
    desc: 'Alt text, ARIA, semantic markup, contrast and keyboard patterns.',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
      </svg>
    ),
  },
  {
    title: 'Design & UX',
    desc: 'Visual hierarchy, typography, CTA placement and mobile-readiness.',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.53 16.122a3 3 0 00-5.78 1.128 2.25 2.25 0 01-2.4 2.245 4.5 4.5 0 008.4-2.245c0-.399-.078-.78-.22-1.128zm0 0a15.998 15.998 0 003.388-1.62m-5.043-.025a15.994 15.994 0 011.622-3.395m3.42 3.42a15.995 15.995 0 004.764-4.648l3.876-5.814a1.151 1.151 0 00-1.597-1.597L14.146 6.32a15.996 15.996 0 00-4.649 4.763m3.42 3.42a6.776 6.776 0 00-3.42-3.42" />
      </svg>
    ),
  },
  {
    title: 'Trust & Credibility',
    desc: 'Social proof, SSL, contact info, legal pages and security signals.',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
      </svg>
    ),
  },
  {
    title: 'Copy & Messaging',
    desc: 'Value proposition, headline clarity, CTAs and tone consistency.',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 01.865-.501 48.172 48.172 0 003.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z" />
      </svg>
    ),
  },
]

export default function Home() {
  const [url, setUrl]                       = useState('')
  const [loading, setLoading]               = useState(false)
  const [error, setError]                   = useState('')
  const [history, setHistory]               = useState([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [phIdx, setPhIdx]                   = useState(0)
  const navigate = useNavigate()
  const inputRef = useRef(null)

  useEffect(() => {
    const t = setInterval(() => setPhIdx((i) => (i + 1) % PLACEHOLDERS.length), 3000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    getHistory()
      .then((d) => setHistory(d.audits ?? []))
      .catch(() => {})
      .finally(() => setHistoryLoading(false))
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    const trimmed = url.trim()
    if (!trimmed) return
    const fullUrl = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`
    setLoading(true)
    setError('')
    try {
      const result = await submitAudit(fullUrl)
      navigate(`/audit/${result.job_id}`)
    } catch (err) {
      setError(err.message || 'Failed to start audit. Please check the URL and try again.')
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950 flex flex-col dot-grid">

      {/* ── Layered background glows ─────────────────────────────────── */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden" aria-hidden>
        <div className="absolute -top-40 left-1/2 -translate-x-1/2 w-[900px] h-[500px] bg-violet-600/15 rounded-full blur-[120px]" />
        <div className="absolute top-1/3 -left-40 w-[500px] h-[500px] bg-indigo-600/10 rounded-full blur-[100px]" />
        <div className="absolute top-1/3 -right-40 w-[500px] h-[500px] bg-purple-600/10 rounded-full blur-[100px]" />
        <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-[600px] h-[300px] bg-violet-900/20 rounded-full blur-[80px]" />
      </div>

      {/* ── Hero ────────────────────────────────────────────────────── */}
      <main className="relative z-10 flex-1 flex flex-col items-center justify-center px-4 pt-16 pb-10">

        {/* Headline */}
        <div className="text-center mb-10 max-w-3xl animate-fade-in">
          {/* Powered by Claude AI — centred above the title */}
          <div className="flex justify-center mb-6">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-violet-500/10 border border-violet-500/20 text-violet-400 text-xs font-medium">
              <span className="w-1.5 h-1.5 bg-violet-400 rounded-full animate-pulse" />
              Powered by Claude AI
            </div>
          </div>

          <h1 className="text-5xl sm:text-6xl lg:text-7xl font-extrabold tracking-tight mb-5 leading-[1.05]">
            <span className="bg-gradient-to-br from-white via-zinc-200 to-zinc-400 bg-clip-text text-transparent">
              Know exactly what's
            </span>
            <br />
            <span className="bg-gradient-to-br from-violet-400 via-purple-400 to-cyan-400 bg-clip-text text-transparent">
              holding your site back
            </span>
          </h1>
          <p className="text-zinc-400 text-lg sm:text-xl leading-relaxed max-w-xl mx-auto">
            Paste any URL and get a complete AI analysis across performance, SEO, accessibility, design, and copy in under a minute.
          </p>
        </div>

        {/* Input card */}
        <div className="w-full max-w-2xl animate-fade-in">
          <form onSubmit={handleSubmit}>
            <div
              className={`flex items-center bg-zinc-900/80 backdrop-blur border rounded-2xl p-1.5 shadow-2xl shadow-violet-950/40 transition-all duration-200 ${
                error
                  ? 'border-red-500/50'
                  : 'border-zinc-700/80 focus-within:border-violet-500/70 focus-within:shadow-violet-700/20'
              }`}
            >
              <span className="pl-4 pr-1 text-zinc-500 text-sm font-mono flex-shrink-0 select-none whitespace-nowrap">
                https://
              </span>
              <input
                ref={inputRef}
                type="text"
                value={url}
                onChange={(e) => { setUrl(e.target.value); setError('') }}
                placeholder={PLACEHOLDERS[phIdx]}
                className="flex-1 bg-transparent px-2 py-3.5 text-white placeholder-zinc-600 outline-none text-base sm:text-lg min-w-0"
                autoFocus
                autoComplete="url"
              />
              <button
                type="submit"
                disabled={loading || !url.trim()}
                className="flex-shrink-0 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold px-6 py-3.5 rounded-xl transition-all duration-150 text-sm sm:text-base shadow-lg shadow-violet-900/50"
              >
                {loading ? (
                  <span className="flex items-center gap-2">
                    <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Starting
                  </span>
                ) : (
                  <span className="flex items-center gap-2">
                    Analyze
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
                    </svg>
                  </span>
                )}
              </button>
            </div>
          </form>

          {error && (
            <p className="text-red-400 text-sm text-center mt-3 animate-fade-in">{error}</p>
          )}

          <p className="text-center text-zinc-600 text-xs mt-4">
            No account needed — results in ~60 seconds
          </p>
        </div>

        {/* ── Feature grid ────────────────────────────────────────────── */}
        <div className="w-full max-w-5xl mt-20 px-2 animate-slide-up">
          <p className="text-center text-xs text-zinc-600 font-medium uppercase tracking-widest mb-8">
            What gets analyzed
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 lg:gap-4">
            {FEATURES.map((f) => (
              <div
                key={f.title}
                className="group bg-zinc-900/50 border border-zinc-800/80 hover:border-violet-500/30 rounded-xl p-4 transition-all duration-200 hover:bg-zinc-900"
              >
                <div className="w-8 h-8 rounded-lg bg-violet-500/10 border border-violet-500/20 text-violet-400 flex items-center justify-center mb-3 group-hover:bg-violet-500/15 transition-colors">
                  {f.icon}
                </div>
                <p className="text-sm font-semibold text-zinc-200 mb-1">{f.title}</p>
                <p className="text-xs text-zinc-500 leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </main>

      {/* ── Recent History ───────────────────────────────────────────── */}
      {!historyLoading && history.length > 0 && (
        <section className="relative z-10 w-full max-w-5xl mx-auto px-4 pb-16 animate-slide-up">
          <div className="flex items-center gap-3 mb-4">
            <div className="h-px flex-1 bg-zinc-800" />
            <span className="text-xs text-zinc-600 font-medium uppercase tracking-widest">Recent Audits</span>
            <div className="h-px flex-1 bg-zinc-800" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {history.slice(0, 6).map((audit) => (
              <HistoryCard key={audit.job_id} audit={audit} />
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
