import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { submitAudit, getHistory } from '../api/audit'
import HistoryCard from '../components/HistoryCard'

const PLACEHOLDERS = [
  'https://stripe.com',
  'https://linear.app',
  'https://vercel.com',
  'https://yoursite.com',
]

export default function Home() {
  const [url, setUrl]                   = useState('')
  const [mode, setMode]                 = useState('professional')
  const [loading, setLoading]           = useState(false)
  const [error, setError]               = useState('')
  const [history, setHistory]           = useState([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [placeholder, setPlaceholder]  = useState(PLACEHOLDERS[0])
  const navigate  = useNavigate()
  const inputRef  = useRef(null)

  useEffect(() => {
    let i = 0
    const t = setInterval(() => {
      i = (i + 1) % PLACEHOLDERS.length
      setPlaceholder(PLACEHOLDERS[i])
    }, 3000)
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
      const result = await submitAudit(fullUrl, mode)
      navigate(`/audit/${result.job_id}`)
    } catch (err) {
      setError(err.message || 'Failed to start audit. Please check the URL and try again.')
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950 flex flex-col">
      {/* Background glow */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-[-20%] left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-violet-600/10 rounded-full blur-3xl" />
      </div>

      {/* Hero */}
      <div className="flex-1 flex flex-col items-center justify-center px-4 py-20 relative">
        <div className="w-full max-w-2xl animate-fade-in">

          {/* Eyebrow badge */}
          <div className="flex justify-center mb-8">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-violet-500/10 border border-violet-500/20 text-violet-400 text-xs font-medium tracking-wide">
              <span className="w-1.5 h-1.5 bg-violet-400 rounded-full animate-pulse" />
              Powered by Claude AI
            </div>
          </div>

          {/* Heading */}
          <div className="text-center mb-12">
            <h1 className="text-5xl sm:text-6xl font-extrabold mb-4 tracking-tight">
              <span className="bg-gradient-to-br from-violet-400 via-purple-400 to-cyan-400 bg-clip-text text-transparent">
                Site Audit AI
              </span>
            </h1>
            <p className="text-zinc-400 text-lg sm:text-xl leading-relaxed max-w-lg mx-auto">
              AI-powered website analyzer — get actionable insights in seconds
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* URL input */}
            <div
              className={`flex items-center bg-zinc-900 border rounded-2xl p-1.5 transition-all duration-200 ${
                error
                  ? 'border-red-500/50'
                  : 'border-zinc-700 focus-within:border-violet-500/60'
              }`}
            >
              <span className="pl-4 text-zinc-600 text-sm font-mono flex-shrink-0 select-none">
                https://
              </span>
              <input
                ref={inputRef}
                type="text"
                value={url}
                onChange={(e) => { setUrl(e.target.value); setError('') }}
                placeholder={placeholder.replace('https://', '')}
                className="flex-1 bg-transparent px-2 py-3 text-white placeholder-zinc-600 outline-none text-base sm:text-lg"
                autoFocus
                autoComplete="url"
              />
              <button
                type="submit"
                disabled={loading || !url.trim()}
                className="flex-shrink-0 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold px-5 py-3 rounded-xl transition-colors duration-150 text-sm sm:text-base"
              >
                {loading ? (
                  <span className="flex items-center gap-2">
                    <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Starting
                  </span>
                ) : (
                  'Analyze'
                )}
              </button>
            </div>

            {error && (
              <p className="text-red-400 text-sm text-center animate-fade-in">{error}</p>
            )}

            {/* Mode toggle */}
            <div className="flex items-center justify-center gap-4">
              <button
                type="button"
                onClick={() => setMode('professional')}
                className={`text-sm font-medium transition-colors ${
                  mode === 'professional' ? 'text-violet-400' : 'text-zinc-600 hover:text-zinc-400'
                }`}
              >
                Professional
              </button>

              <button
                type="button"
                onClick={() => setMode(mode === 'professional' ? 'roast' : 'professional')}
                className={`relative w-12 h-6 rounded-full transition-colors duration-200 flex-shrink-0 ${
                  mode === 'roast' ? 'bg-orange-500' : 'bg-zinc-700'
                }`}
                aria-label="Toggle mode"
              >
                <span
                  className={`absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-all duration-200 ${
                    mode === 'roast' ? 'left-7' : 'left-1'
                  }`}
                />
              </button>

              <button
                type="button"
                onClick={() => setMode('roast')}
                className={`text-sm font-medium transition-colors ${
                  mode === 'roast' ? 'text-orange-400' : 'text-zinc-600 hover:text-zinc-400'
                }`}
              >
                Roast Mode
              </button>
            </div>

            {mode === 'roast' && (
              <p className="text-center text-xs text-orange-400/70 animate-fade-in">
                Brutally honest — Claude will tear your site apart, technically and creatively.
              </p>
            )}
          </form>

          {/* Feature pills */}
          <div className="flex flex-wrap justify-center gap-2 mt-10">
            {['Performance', 'SEO', 'Accessibility', 'Design & UX', 'Trust & Credibility', 'Copy & Messaging'].map((f) => (
              <span
                key={f}
                className="text-xs text-zinc-600 bg-zinc-900 border border-zinc-800 px-3 py-1 rounded-full"
              >
                {f}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Recent History */}
      <div className="pb-16 px-4 w-full max-w-2xl mx-auto">
        {!historyLoading && history.length > 0 && (
          <div className="animate-slide-up">
            <div className="flex items-center gap-3 mb-3">
              <div className="h-px flex-1 bg-zinc-800" />
              <span className="text-xs text-zinc-600 font-medium uppercase tracking-wider">Recent Audits</span>
              <div className="h-px flex-1 bg-zinc-800" />
            </div>
            <div className="space-y-2">
              {history.slice(0, 8).map((audit) => (
                <HistoryCard key={audit.job_id} audit={audit} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
