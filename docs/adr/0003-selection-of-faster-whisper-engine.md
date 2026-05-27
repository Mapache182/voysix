# ADR 0003: Selection of Faster-Whisper Engine

* Status: Accepted
* Deciders: Antigravity, USER
* Date: 2026-05-14

## Context and Problem Statement

The original OpenAI Whisper implementation, while accurate, is resource-heavy and slow on standard CPUs. For a desktop "voice-to-paste" application, latency is critical—users expect the text to appear almost instantly after they finish speaking.

We need a transcription engine that balances high accuracy with low latency, especially on consumer-grade hardware.

## Decision Drivers

* **Latency**: Minimum delay between recording and output.
* **Accuracy**: Must maintain the high quality of the Whisper models.
* **Resource Efficiency**: Ability to run on CPUs without requiring high-end GPUs.
* **VRAM Usage**: Optimized memory footprint for local GPU processing.

## Considered Options

1. **OpenAI Whisper (Original)**: The reference implementation using PyTorch.
2. **Whisper.cpp**: A C++ port optimized for CPU and Apple Silicon.
3. **Faster-Whisper**: A reimplementation using CTranslate2 (a fast inference engine for Transformer models).

## Decision Outcome

Chosen option: **Faster-Whisper**, with **OpenAI Whisper** as a fallback.

### Implementation Details:
- **Quantization**: Faster-Whisper allows for `int8` quantization on CPU and `float16` on GPU, significantly reducing memory usage and increasing speed with negligible loss in accuracy.
- **Engine Support**: The `WhisperTranscriber` (client) and `service.py` (worker) are built to handle both engines.
- **VAD (Voice Activity Detection)**: Faster-Whisper includes built-in VAD (Silero VAD) to filter out silence and reduce processing time.
- **Model Storage**: Models are downloaded to a central directory (`APPDATA/voysix/models` on client, `/data/models` on worker) to avoid redundant downloads.

### Consequences

* **Good**: 2x to 4x faster transcription compared to the original implementation on the same hardware.
* **Good**: Works well on non-NVIDIA hardware (Intel/AMD CPUs) using `int8`.
* **Bad**: Adds dependency on `faster-whisper` and `ctranslate2` libraries.
* **Bad**: Some niche Whisper parameters might not be perfectly identical across engines.

## Pros and Cons of the Options

### OpenAI Whisper
* Good: Most compatible; reference implementation.
* Bad: Slow; high VRAM/RAM consumption.

### Whisper.cpp
* Good: Extremely fast; minimal dependencies.
* Bad: Harder to integrate with Python-based PySide6 and FastAPI ecosystems.

### Faster-Whisper (Chosen)
* Good: Best balance of speed (CTranslate2) and Python integration; supports GPU acceleration.
* Bad: Requires specific libraries that can be tricky to package (cx_Freeze).
