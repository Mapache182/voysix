# ADR 0001: Client-Worker Split Architecture

* Status: Accepted
* Deciders: Antigravity, USER
* Date: 2026-05-14

## Context and Problem Statement

Transcription using AI models like Whisper is computationally intensive. Desktop users may have varying hardware:
1. Some have powerful NVIDIA GPUs capable of local real-time transcription.
2. Others have thin clients (laptops, older PCs) that would struggle or drain battery quickly.
3. Some users want to offload the load to a dedicated home server or a cloud instance to keep the desktop responsive.

We need an architecture that supports both local processing and remote offloading seamlessly.

## Decision Drivers

* **Performance**: Low latency for high-end machines.
* **Accessibility**: Support for low-power devices via remote processing.
* **Scalability**: Ability to use more powerful remote hardware (GPU servers).
* **Maintainability**: Clear separation between UI logic and heavy AI processing.

## Considered Options

1. **Monolithic App**: All transcription logic is strictly local.
2. **Cloud-only**: Force all transcription through a central API (e.g., OpenAI API).
3. **Hybrid Client-Worker Split**: Decoupled architecture where the client can process locally or delegate to a private worker.

## Decision Outcome

Chosen option: **Hybrid Client-Worker Split**, because it offers the most flexibility. 

### Implementation Details:
- **Voysix App (Client)**: A PySide6 desktop application that handles recording, UI, and orchestration. It contains a `WhisperTranscriber` (local) and a `RemoteWhisperTranscriber` (proxy).
- **Voysix Worker**: A FastAPI-based service that exposes a REST API (`/transcribe`, `/config`, `/health`). It is designed to run in Docker and utilize NVIDIA GPUs if available.
- **Protocol**: HTTP/REST for simplicity and compatibility across different network setups.

### Consequences

* **Good**: Users with multiple devices can run one "Worker" on a powerful PC and use "Client" on multiple laptops.
* **Good**: Easier to update the AI engine (Worker) independently of the UI (App).
* **Bad**: Increased complexity in discovery and network communication.
* **Bad**: Potential latency introduced by network transfer of audio data.

## Pros and Cons of the Options

### Monolithic App
* Good: No network configuration required.
* Bad: Useless on machines without AVX2 or decent GPUs.

### Cloud-only
* Good: Guaranteed performance regardless of local hardware.
* Bad: Privacy concerns; cost of API tokens; requires internet.

### Hybrid Split (Chosen)
* Good: Privacy-first (private workers); works offline (local mode); high performance (remote mode).
* Bad: Requires managing two components.
