class Pcm16Processor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0]?.[0]
    if (!input || input.length === 0) return true

    let sum = 0
    const pcm = new Uint8Array(input.length * 2)
    const view = new DataView(pcm.buffer)
    for (let i = 0; i < input.length; i += 1) {
      const sample = Math.max(-1, Math.min(1, input[i]))
      sum += sample * sample
      view.setInt16(i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
    }
    this.port.postMessage({
      pcm,
      rms: Math.sqrt(sum / Math.max(1, input.length)),
      timestamp: Date.now(),
    }, [pcm.buffer])
    return true
  }
}

registerProcessor('pcm16-processor', Pcm16Processor)
