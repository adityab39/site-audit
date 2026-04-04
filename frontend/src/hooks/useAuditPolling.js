import { useState, useEffect, useRef } from 'react'
import { getAuditStatus } from '../api/audit'

const TERMINAL_STATUSES = new Set(['completed', 'failed'])
const POLL_INTERVAL_MS = 2000

export function useAuditPolling(jobId) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const timeoutRef = useRef(null)
  const cancelledRef = useRef(false)

  useEffect(() => {
    if (!jobId) return
    cancelledRef.current = false
    setLoading(true)
    setData(null)
    setError(null)

    const poll = async () => {
      try {
        const result = await getAuditStatus(jobId)
        if (cancelledRef.current) return
        setData(result)
        if (!TERMINAL_STATUSES.has(result.status)) {
          timeoutRef.current = setTimeout(poll, POLL_INTERVAL_MS)
        } else {
          setLoading(false)
        }
      } catch (err) {
        if (cancelledRef.current) return
        setError(err.message)
        setLoading(false)
      }
    }

    poll()

    return () => {
      cancelledRef.current = true
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  }, [jobId])

  return { data, error, loading }
}
