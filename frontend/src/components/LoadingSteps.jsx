import { useEffect, useState } from 'react'

const STEPS = [
  { id: 0, label: 'Crawling page',         duration: 8000 },
  { id: 1, label: 'Measuring performance', duration: 15000 },
  { id: 2, label: 'AI analyzing',          duration: Infinity },
]

export default function LoadingSteps() {
  const [activeStep, setActiveStep] = useState(0)

  useEffect(() => {
    const timers = []
    let elapsed = 0
    STEPS.slice(0, -1).forEach((step, idx) => {
      elapsed += step.duration
      timers.push(setTimeout(() => setActiveStep(idx + 1), elapsed))
    })
    return () => timers.forEach(clearTimeout)
  }, [])

  return (
    <div className="space-y-2">
      {STEPS.map((step, idx) => {
        const isDone    = idx < activeStep
        const isActive  = idx === activeStep
        const isPending = idx > activeStep

        return (
          <div
            key={step.id}
            className={`flex items-center gap-3 px-4 py-3 rounded-xl border transition-all duration-300 ${
              isActive  ? 'bg-violet-500/10 border-violet-500/30'
              : isDone  ? 'bg-green-500/5  border-green-500/20'
              :            'bg-zinc-900/40  border-zinc-800'
            }`}
          >
            {/* Status indicator */}
            <div className="w-6 h-6 flex items-center justify-center flex-shrink-0">
              {isDone ? (
                <svg className="w-4 h-4 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              ) : isActive ? (
                <span className="w-4 h-4 rounded-full border-2 border-violet-400 border-t-transparent animate-spin block" />
              ) : (
                <span className="w-2 h-2 rounded-full bg-zinc-700 block" />
              )}
            </div>

            {/* Label */}
            <span className={`text-sm font-medium flex-1 ${
              isActive ? 'text-violet-300' : isDone ? 'text-green-400' : 'text-zinc-600'
            }`}>
              {step.label}
              {isActive && <span className="animate-pulse ml-0.5">...</span>}
            </span>

            {/* State tag */}
            {isActive  && <span className="text-xs text-zinc-500">In progress</span>}
            {isDone    && <span className="text-xs text-green-500/60">Done</span>}
            {isPending && <span className="text-xs text-zinc-700">Queued</span>}
          </div>
        )
      })}
    </div>
  )
}
