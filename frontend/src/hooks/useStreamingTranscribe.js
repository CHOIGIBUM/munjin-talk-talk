import { useCallback, useEffect, useRef, useState } from 'react'
import { openTranscribeStream } from '../services/transcribeStreaming.js'

// Real-time STT hook. Audio is streamed directly to Amazon Transcribe and is
// never uploaded to the application S3 bucket.
export function useStreamingTranscribe({ sessionId, questionId, visitType }) {
  const [isRecording, setIsRecording] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [transcript, setTranscript] = useState('')
  const [error, setError] = useState(null)
  const controllerRef = useRef(null)
  const transcriptRef = useRef('')
  const intervalRef = useRef(null)

  const start = useCallback(async () => {
    if (controllerRef.current || !questionId) return
    setError(null)
    setTranscript('')
    transcriptRef.current = ''
    setElapsed(0)
    const startedAt = Date.now()
    intervalRef.current = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt) / 1000))
    }, 200)
    try {
      controllerRef.current = await openTranscribeStream({
        sessionId,
        questionId,
        visitType,
        onTranscript: (text) => {
          transcriptRef.current = text
          setTranscript(text)
        },
        onStatus: (status) => {
          setIsRecording(status === 'recording')
        },
        onError: (nextError) => {
          setError(nextError)
        },
      })
    } catch (nextError) {
      setError(nextError)
      setIsRecording(false)
      if (intervalRef.current) clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }, [questionId, sessionId, visitType])

  const stop = useCallback(async () => {
    const controller = controllerRef.current
    controllerRef.current = null
    if (intervalRef.current) clearInterval(intervalRef.current)
    intervalRef.current = null
    setIsRecording(false)
    if (!controller) return transcriptRef.current.trim()
    const finalText = await controller.stop()
    transcriptRef.current = finalText || transcriptRef.current
    setTranscript(transcriptRef.current)
    return transcriptRef.current.trim()
  }, [])

  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
      controllerRef.current?.stop?.()
      controllerRef.current = null
    }
  }, [])

  return { isRecording, elapsed, transcript, error, start, stop }
}
