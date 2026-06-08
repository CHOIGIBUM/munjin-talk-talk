import { useCallback, useEffect, useRef, useState } from 'react'
import { openTranscribeStream } from '../services/transcribeStreaming.js'

const MAX_RECORDING_MS = 60000
const FIRST_SPEECH_WAIT_MS = 9000
const SILENCE_AFTER_SPEECH_MS = 4300
const MIN_RECORDING_MS = 2500
const SPEECH_RMS_THRESHOLD = 0.018
const SPEECH_FRAME_CONFIRM_COUNT = 3

// 실시간 STT 상태를 관리하는 hook입니다.
// 음성은 애플리케이션 S3 bucket에 업로드하지 않고 Amazon Transcribe로 직접 스트리밍합니다.
export function useStreamingTranscribe({
  sessionId,
  questionId,
  visitType,
  onAutoStop,
}) {
  const [isRecording, setIsRecording] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [transcript, setTranscript] = useState('')
  const [error, setError] = useState(null)
  const controllerRef = useRef(null)
  const transcriptRef = useRef('')
  const timerRef = useRef(null)
  const autoStopRef = useRef(onAutoStop)
  const startedAtRef = useRef(0)
  const lastSpeechAtRef = useRef(0)
  const speechSeenRef = useRef(false)
  const speechFrameCountRef = useRef(0)
  const stoppingRef = useRef(false)

  useEffect(() => {
    autoStopRef.current = onAutoStop
  }, [onAutoStop])

  const clearTimer = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current)
    timerRef.current = null
  }, [])

  const stop = useCallback(async (reason = 'manual') => {
    if (stoppingRef.current) return transcriptRef.current.trim()
    stoppingRef.current = true
    const controller = controllerRef.current
    controllerRef.current = null
    clearTimer()
    setIsRecording(false)
    if (!controller) {
      stoppingRef.current = false
      return transcriptRef.current.trim()
    }
    const finalText = await controller.stop()
    transcriptRef.current = finalText || transcriptRef.current
    setTranscript(transcriptRef.current)
    stoppingRef.current = false
    return transcriptRef.current.trim()
  }, [clearTimer])

  const stopByPolicy = useCallback(async (reason) => {
    const finalText = await stop(reason)
    autoStopRef.current?.(finalText, reason)
  }, [stop])

  const evaluateAutoStop = useCallback(() => {
    const startedAt = startedAtRef.current
    if (!controllerRef.current || !startedAt || stoppingRef.current) return

    const now = Date.now()
    const elapsedMs = now - startedAt
    setElapsed(Math.floor(elapsedMs / 1000))

    if (elapsedMs >= MAX_RECORDING_MS) {
      void stopByPolicy('max_time')
      return
    }

    // 어르신이 질문을 읽고 말하기까지 걸리는 시간을 고려해 첫 발화 전에는 넉넉히 기다립니다.
    if (!speechSeenRef.current && !transcriptRef.current.trim() && elapsedMs >= FIRST_SPEECH_WAIT_MS) {
      void stopByPolicy('no_speech')
      return
    }

    // 말더듬이나 짧은 생각 시간을 끊지 않도록, 실제 STT 문장이 생긴 뒤 긴 침묵이 이어질 때만 종료합니다.
    const hasTranscript = transcriptRef.current.trim().length > 0
    const silenceMs = now - (lastSpeechAtRef.current || startedAt)
    if (
      speechSeenRef.current
      && hasTranscript
      && elapsedMs >= MIN_RECORDING_MS
      && silenceMs >= SILENCE_AFTER_SPEECH_MS
    ) {
      void stopByPolicy('silence_after_speech')
    }
  }, [stopByPolicy])

  const start = useCallback(async () => {
    if (controllerRef.current || stoppingRef.current || !questionId) return
    setError(null)
    setTranscript('')
    transcriptRef.current = ''
    setElapsed(0)
    startedAtRef.current = Date.now()
    lastSpeechAtRef.current = startedAtRef.current
    speechSeenRef.current = false
    speechFrameCountRef.current = 0
    timerRef.current = setInterval(evaluateAutoStop, 250)

    try {
      controllerRef.current = await openTranscribeStream({
        sessionId,
        questionId,
        visitType,
        onTranscript: (text) => {
          transcriptRef.current = text
          setTranscript(text)
          if (String(text || '').trim()) {
            speechSeenRef.current = true
            lastSpeechAtRef.current = Date.now()
          }
        },
        onAudioActivity: ({ rms, timestamp }) => {
          if (rms >= SPEECH_RMS_THRESHOLD) {
            speechFrameCountRef.current += 1
            if (speechFrameCountRef.current >= SPEECH_FRAME_CONFIRM_COUNT) {
              speechSeenRef.current = true
              lastSpeechAtRef.current = timestamp || Date.now()
            }
          } else {
            speechFrameCountRef.current = Math.max(0, speechFrameCountRef.current - 1)
          }
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
      clearTimer()
      controllerRef.current = null
    }
  }, [clearTimer, evaluateAutoStop, questionId, sessionId, visitType])

  useEffect(() => {
    return () => {
      clearTimer()
      controllerRef.current?.stop?.()
      controllerRef.current = null
    }
  }, [clearTimer])

  return { isRecording, elapsed, transcript, error, start, stop }
}
