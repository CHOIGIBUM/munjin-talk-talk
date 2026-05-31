import { useState, useRef, useCallback, useEffect } from 'react'

/**
 * 브라우저 MediaRecorder API 래퍼 훅
 * - 녹음 시작/중지
 * - 녹음된 Blob 반환
 * - 경과 시간 추적
 *
 * 실제 STT 호출은 services/api.js에서 처리.
 */
export function useAudioRecorder() {
  const [isRecording, setIsRecording] = useState(false)
  const [audioBlob, setAudioBlob] = useState(null)
  const [elapsed, setElapsed] = useState(0)  // 초

  const streamRef = useRef(null)
  const audioContextRef = useRef(null)
  const sourceRef = useRef(null)
  const processorRef = useRef(null)
  const sampleRateRef = useRef(16000)
  const samplesRef = useRef([])
  const recordingRef = useRef(false)
  const startTimeRef = useRef(0)
  const intervalRef = useRef(null)

  const start = useCallback(async () => {
    try {
      if (recordingRef.current) return
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
      streamRef.current = stream
      samplesRef.current = []

      const AudioContextClass = window.AudioContext || window.webkitAudioContext
      const audioContext = new AudioContextClass({ sampleRate: 16000 })
      audioContextRef.current = audioContext
      sampleRateRef.current = audioContext.sampleRate

      const source = audioContext.createMediaStreamSource(stream)
      const processor = audioContext.createScriptProcessor(4096, 1, 1)
      sourceRef.current = source
      processorRef.current = processor

      processor.onaudioprocess = (event) => {
        if (!recordingRef.current) return
        const input = event.inputBuffer.getChannelData(0)
        samplesRef.current.push(new Float32Array(input))
      }

      source.connect(processor)
      processor.connect(audioContext.destination)

      recordingRef.current = true
      startTimeRef.current = Date.now()
      setIsRecording(true)
      setAudioBlob(null)
      setElapsed(0)

      // 경과 시간 업데이트
      intervalRef.current = setInterval(() => {
        setElapsed(Math.floor((Date.now() - startTimeRef.current) / 1000))
      }, 200)
    } catch (err) {
      console.error('녹음 시작 실패:', err)
      alert('마이크 권한을 허용해주세요.')
    }
  }, [])

  const stop = useCallback(() => {
    if (!recordingRef.current) return
    recordingRef.current = false

    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }

    processorRef.current?.disconnect()
    sourceRef.current?.disconnect()
    processorRef.current = null
    sourceRef.current = null

    const blob = encodeWav(samplesRef.current, sampleRateRef.current)
    setAudioBlob(blob)
    samplesRef.current = []

    streamRef.current?.getTracks().forEach(t => t.stop())
    streamRef.current = null
    audioContextRef.current?.close()
    audioContextRef.current = null
    setIsRecording(false)
  }, [])

  const reset = useCallback(() => {
    setAudioBlob(null)
    setElapsed(0)
  }, [])

  // 언마운트 시 정리
  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
      recordingRef.current = false
      processorRef.current?.disconnect()
      sourceRef.current?.disconnect()
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(t => t.stop())
      }
      audioContextRef.current?.close()
    }
  }, [])

  return { isRecording, audioBlob, elapsed, start, stop, reset }
}

function encodeWav(chunks, sampleRate) {
  const length = chunks.reduce((sum, chunk) => sum + chunk.length, 0)
  const samples = new Float32Array(length)
  let offset = 0
  chunks.forEach((chunk) => {
    samples.set(chunk, offset)
    offset += chunk.length
  })

  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(buffer)
  writeString(view, 0, 'RIFF')
  view.setUint32(4, 36 + samples.length * 2, true)
  writeString(view, 8, 'WAVE')
  writeString(view, 12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeString(view, 36, 'data')
  view.setUint32(40, samples.length * 2, true)

  let pos = 44
  for (let i = 0; i < samples.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(pos, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
    pos += 2
  }

  return new Blob([view], { type: 'audio/wav' })
}

function writeString(view, offset, value) {
  for (let i = 0; i < value.length; i += 1) {
    view.setUint8(offset + i, value.charCodeAt(i))
  }
}
