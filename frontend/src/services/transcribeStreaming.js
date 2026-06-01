import { getMockTranscript } from './api/mockResponses.js'
import { API_BASE_URL, ensureApiConfigured, sleep, useMockApi } from './api/client.js'

const encoder = new TextEncoder()
const decoder = new TextDecoder()
const CRC32_TABLE = makeCrc32Table()

export async function openTranscribeStream({
  sessionId,
  questionId,
  visitType,
  onTranscript,
  onStatus,
  onError,
}) {
  if (useMockApi()) {
    return openMockTranscribeStream({ questionId, visitType, onTranscript, onStatus })
  }
  ensureApiConfigured()

  const AudioContextClass = window.AudioContext || window.webkitAudioContext
  const audioContext = new AudioContextClass({ sampleRate: 16000 })
  await resumeAudioContext(audioContext)
  const sampleRate = audioContext.sampleRate

  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      sampleRate,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  })
  const { stream_url: streamUrl } = await getTranscribeStreamUrl({
    sessionId,
    questionId,
    visitType,
    sampleRate,
  })

  const socket = new WebSocket(streamUrl)
  socket.binaryType = 'arraybuffer'

  const source = audioContext.createMediaStreamSource(stream)
  const processor = audioContext.createScriptProcessor(4096, 1, 1)
  const silentGain = audioContext.createGain()
  // 완전한 0 gain은 일부 브라우저에서 오디오 그래프가 쉬어버릴 수 있어
  // 들리지 않는 수준의 아주 작은 gain으로 그래프를 계속 당겨옵니다.
  silentGain.gain.value = 0.00001

  const finalSegments = []
  let latestText = ''
  let started = false
  let stopped = false
  let framesSent = 0
  let bytesSent = 0
  const noAudioTimer = window.setTimeout(async () => {
    if (stopped || framesSent > 0) return
    await resumeAudioContext(audioContext)
    if (audioContext.state === 'suspended') {
      onError?.(new Error('audio_context_suspended'))
    } else {
      onError?.(new Error('audio_stream_no_frames'))
    }
  }, 2500)

  socket.onmessage = async (event) => {
    try {
      const buffer = event.data instanceof Blob ? await event.data.arrayBuffer() : event.data
      const message = decodeEventMessage(buffer)
      const payloadText = decoder.decode(message.payload)
      const payload = payloadText ? JSON.parse(payloadText) : {}
      if (message.headers[':message-type'] === 'exception') {
        onError?.(new Error(payload.Message || message.headers[':exception-type'] || 'transcribe_stream_exception'))
        return
      }
      const results = payload?.Transcript?.Results || []
      for (const result of results) {
        const text = result?.Alternatives?.[0]?.Transcript || ''
        if (!text) continue
        if (result.IsPartial) {
          latestText = [...finalSegments, text].join(' ').trim()
          onTranscript?.(latestText, { partial: true })
        } else {
          finalSegments.push(text)
          latestText = finalSegments.join(' ').trim()
          onTranscript?.(latestText, { partial: false })
        }
      }
    } catch (error) {
      onError?.(error)
    }
  }

  socket.onerror = () => {
    onError?.(new Error('transcribe_stream_socket_error'))
  }

  await new Promise((resolve, reject) => {
    socket.onopen = () => resolve()
    socket.onerror = () => reject(new Error('transcribe_stream_open_failed'))
  })
  socket.onerror = () => {
    onError?.(new Error('transcribe_stream_socket_error'))
  }
  socket.onclose = () => {
    if (!stopped) onStatus?.('stopped')
  }

  processor.onaudioprocess = (event) => {
    if (!started || stopped || socket.readyState !== WebSocket.OPEN) return
    if (audioContext.state === 'suspended') {
      resumeAudioContext(audioContext)
      return
    }
    const input = event.inputBuffer.getChannelData(0)
    const chunk = floatToPcm16(input)
    socket.send(encodeAudioEvent(chunk))
    framesSent += 1
    bytesSent += chunk.byteLength
  }

  source.connect(processor)
  processor.connect(silentGain)
  silentGain.connect(audioContext.destination)
  await resumeAudioContext(audioContext)
  started = true
  onStatus?.('recording')

  return {
    get transcript() {
      return latestText
    },
    async stop() {
      stopped = true
      window.clearTimeout(noAudioTimer)
      try {
        if (socket.readyState === WebSocket.OPEN) {
          socket.send(encodeAudioEvent(new Uint8Array()))
          await sleep(bytesSent > 0 ? 1000 : 250)
          socket.close()
        }
      } finally {
        processor.disconnect()
        source.disconnect()
        silentGain.disconnect()
        stream.getTracks().forEach((track) => track.stop())
        await audioContext.close()
        onStatus?.('stopped')
      }
      return latestText.trim()
    },
  }
}

async function resumeAudioContext(audioContext) {
  if (audioContext.state !== 'suspended') return
  try {
    await audioContext.resume()
  } catch {
    // Chrome may require a direct user gesture. The UI surfaces this as an
    // empty-audio error so the patient can tap the microphone again.
  }
}

async function getTranscribeStreamUrl({ sessionId, questionId, visitType, sampleRate }) {
  const res = await fetch(`${API_BASE_URL}/transcribe-stream-url`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      question_id: questionId,
      visit_type: visitType,
      sample_rate: sampleRate,
    }),
  })
  if (!res.ok) throw new Error('transcribe_stream_url_failed')
  return res.json()
}

function openMockTranscribeStream({ questionId, visitType, onTranscript, onStatus }) {
  let currentText = ''
  let stopped = false
  let timer = null
  const jobName = `mock-${questionId}_${visitType || 'initial'}`
  onStatus?.('recording')
  getMockTranscript(jobName).then(({ transcript }) => {
    if (stopped) return
    const words = String(transcript || '').split(/\s+/)
    let index = 0
    timer = setInterval(() => {
      index += 2
      currentText = words.slice(0, index).join(' ')
      onTranscript?.(currentText, { partial: index < words.length })
      if (index >= words.length) clearInterval(timer)
    }, 250)
  })
  return {
    get transcript() {
      return currentText
    },
    async stop() {
      stopped = true
      if (timer) clearInterval(timer)
      onStatus?.('stopped')
      return currentText
    },
  }
}

function encodeAudioEvent(payload) {
  return encodeEventMessage({
    ':content-type': 'application/octet-stream',
    ':event-type': 'AudioEvent',
    ':message-type': 'event',
  }, payload)
}

function encodeEventMessage(headers, payload) {
  const headerBytes = encodeHeaders(headers)
  const totalLength = 16 + headerBytes.length + payload.length
  const message = new Uint8Array(totalLength)
  const view = new DataView(message.buffer)
  view.setUint32(0, totalLength, false)
  view.setUint32(4, headerBytes.length, false)
  view.setUint32(8, crc32(message.subarray(0, 8)), false)
  message.set(headerBytes, 12)
  message.set(payload, 12 + headerBytes.length)
  view.setUint32(totalLength - 4, crc32(message.subarray(0, totalLength - 4)), false)
  return message
}

function encodeHeaders(headers) {
  const chunks = []
  for (const [name, value] of Object.entries(headers)) {
    const nameBytes = encoder.encode(name)
    const valueBytes = encoder.encode(value)
    const chunk = new Uint8Array(1 + nameBytes.length + 1 + 2 + valueBytes.length)
    let offset = 0
    chunk[offset] = nameBytes.length
    offset += 1
    chunk.set(nameBytes, offset)
    offset += nameBytes.length
    chunk[offset] = 7
    offset += 1
    new DataView(chunk.buffer).setUint16(offset, valueBytes.length, false)
    offset += 2
    chunk.set(valueBytes, offset)
    chunks.push(chunk)
  }
  const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0)
  const out = new Uint8Array(total)
  let offset = 0
  for (const chunk of chunks) {
    out.set(chunk, offset)
    offset += chunk.length
  }
  return out
}

function decodeEventMessage(buffer) {
  const bytes = new Uint8Array(buffer)
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  const totalLength = view.getUint32(0, false)
  const headersLength = view.getUint32(4, false)
  const headers = decodeHeaders(bytes.subarray(12, 12 + headersLength))
  const payload = bytes.subarray(12 + headersLength, totalLength - 4)
  return { headers, payload }
}

function decodeHeaders(bytes) {
  const headers = {}
  let offset = 0
  while (offset < bytes.length) {
    const nameLen = bytes[offset]
    offset += 1
    const name = decoder.decode(bytes.subarray(offset, offset + nameLen))
    offset += nameLen
    const type = bytes[offset]
    offset += 1
    if (type !== 7) break
    const valueLen = new DataView(bytes.buffer, bytes.byteOffset + offset, 2).getUint16(0, false)
    offset += 2
    headers[name] = decoder.decode(bytes.subarray(offset, offset + valueLen))
    offset += valueLen
  }
  return headers
}

function floatToPcm16(input) {
  const pcm = new Uint8Array(input.length * 2)
  const view = new DataView(pcm.buffer)
  for (let i = 0; i < input.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, input[i]))
    view.setInt16(i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
  }
  return pcm
}

function makeCrc32Table() {
  const table = new Uint32Array(256)
  for (let i = 0; i < 256; i += 1) {
    let c = i
    for (let k = 0; k < 8; k += 1) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    }
    table[i] = c >>> 0
  }
  return table
}

function crc32(bytes) {
  let crc = 0xffffffff
  for (let i = 0; i < bytes.length; i += 1) {
    crc = CRC32_TABLE[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8)
  }
  return (crc ^ 0xffffffff) >>> 0
}
