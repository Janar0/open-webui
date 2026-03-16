/**
 * AudioWorklet processor for capturing PCM16 audio at 24kHz for OpenAI Realtime API.
 *
 * Receives Float32 samples from the microphone (typically 48kHz),
 * downsamples to 24kHz, converts to Int16, and posts chunks to the main thread.
 */
class RealtimeCaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this._targetSampleRate = 24000;
    // sampleRate is a global in AudioWorkletGlobalScope
    this._inputSampleRate = sampleRate;
    this._ratio = this._inputSampleRate / this._targetSampleRate;
    this._buffer = [];
    // Send chunks every ~100ms worth of samples
    this._chunkSize = Math.floor(this._targetSampleRate * 0.1);
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (!input || !input[0]) return true;

    const inputData = input[0]; // mono channel

    // Simple downsampling by picking nearest sample
    for (let i = 0; i < inputData.length; i++) {
      const targetIndex = this._buffer.length;
      const sourceIndex = targetIndex * this._ratio;
      // Only push if this input sample corresponds to a target sample
      if (Math.floor(i / this._ratio) > this._buffer.length - 1 || this._buffer.length === 0) {
        // Clamp to [-1, 1] and convert to Int16
        const s = Math.max(-1, Math.min(1, inputData[i]));
        this._buffer.push(s < 0 ? s * 0x8000 : s * 0x7fff);
      }
    }

    if (this._buffer.length >= this._chunkSize) {
      const chunk = new Int16Array(this._buffer.splice(0, this._chunkSize));
      this.port.postMessage({ type: 'audio', samples: chunk.buffer }, [chunk.buffer]);
    }

    return true;
  }
}

registerProcessor('realtime-capture-processor', RealtimeCaptureProcessor);
