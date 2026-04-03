# Voysix — Professional Speech-to-Text for Desktop

![Voysix Logo](new_logo.png)

[![CI/CD Status](https://github.com/your-username/voysix/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/your-username/voysix/actions)
![License](https://img.shields.io/github/license/your-username/voysix)
![Release](https://img.shields.io/github/v/release/your-username/voysix?include_prereleases)

**Voysix** is an open-source, versatile desktop application that brings the power of **OpenAI's Whisper** (and `faster-whisper`) directly into your daily workflow. Record your ideas, messages, or notes with a single hotkey and have them transcribed and pasted instantly into any application.

---

## ✨ Why Voysix?

- 🚀 **Global Hotkeys**: Control everything from anywhere in Windows with a single click.
- 🎨 **Glassmorphism UI**: A minimalist, high-quality floating interface that stays out of your way.
- 🛠️ **Local or Remote**: Use your own GPU locally OR offload processing to a dedicated worker.
- 💨 **Ultra-Fast**: Optimized for speed with `faster-whisper` and optional worker caching.
- 🔒 **Private**: No third-party APIs required. Your voice data stays on your machine or your private worker nodes.
- 🔗 **Tailscale Native**: Easy, secure remote worker setup with built-in Tailscale discovery.

---

## 🏗️ Architecture & Core Components

Voysix is split into two independent parts, allowing for flexible deployment scenarios:

```mermaid
graph TD
    subgraph "Desktop Client (Voysix App)"
        A[Hotkey Monitor] --> B[Audio Recorder]
        B --> C[Orchestrator]
        C --> D[Local Whisper Engine]
        C --> E[Remote Worker Client]
        D --> F[Active Window / Paste]
        E --> F
    end

    subgraph "Remote Worker (Optional)"
        E -.->|REST API over Tailscale| G[FastAPI Service]
        G --> H[Transcription Engine]
        H -.->|JSON Response| E
    end
```

### 1. Voysix App (`/App`)
Built with **PySide6**, this component handles the recording logic and system-wide integration. It includes features like:
- **Audio Recorder**: Low-latency capture via `sounddevice`.
- **System Tray**: Comprehensive settings management and log viewer.
- **Auto-Paste**: Seamless text insertion into any target app.
- **Smart Cleanup**: Sophisticated punctuation and cleanup logic.

### 2. Voysix Worker (`/worker`)
A high-performance **FastAPI** backend for offloading computations.
- Optimized for **Docker** and **NVIDIA GPUs**.
- Tailscale integration for secure remote access without port forwarding.
- Model caching to avoid reloading overhead.

---

## 🚀 Getting Started

### Installation (Standard User)
If you just want to use Voysix, wait for the first release or follow the build steps below to create your own `.exe`.

### Installation (Developer)

1. **Clone the Repo**:
   ```bash
   git clone https://github.com/your-username/voysix.git
   cd voysix
   ```
2. **Setup Client**:
   ```bash
   cd App
   python -m venv venv
   source venv/Scripts/activate
   pip install -r requirements.txt
   python main.py
   ```
3. **Setup Worker (Optional)**:
   ```bash
   cd worker
   docker build -t voysix-worker .
   docker run -d --privileged -e TS_AUTHKEY=<your-key> voysix-worker
   ```

---

## 🔄 Automated CI/CD

Voysix uses **GitHub Actions** for automated building and quality assurance:
- **`worker-v*`** tags: Automatically builds the Docker image and pushes to both **GitHub Container Registry (GHCR)** and **Docker Hub**.
- **`app-v*`** tags: Automatically compiles the Windows Setup EXE installer and creates a GitHub Release.


---

## 📦 Building Standalone Version

Для сборки Windows-версии (EXE + установщик) используется автоматизированный скрипт:

1. Перейдите в папку приложения: `cd App`
2. Запустите сборку:
   ```bash
   python build_dist.py
   ```

**Что делает этот скрипт:**
- Автоматически увеличивает версию (patch) в `version.txt`, `main.py` и `setup.py`.
- Компилирует Python-код в `.exe` с помощью **cx_Freeze**.
- Собирает финальный инсталлятор через **Inno Setup**.

Результат будет доступен в: `App/dist/Voysix_Setup.exe`.

---

## 📜 Project Structure
- `App/` — All desktop-side files (logic, UI, assets).
- `worker/` — Server-side code for remote processing.
- `.github/workflows/` — Automated build pipelines.
- `LICENSE` — Open source licensing details.

---

## 🤝 Contributing
Contributions are what make the open-source community so amazing. If you have a suggestion that would make this better, please fork the repo and create a pull request.

1. Fork the Project.
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`).
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`).
4. Push to the Branch (`git push origin feature/AmazingFeature`).
5. Open a Pull Request.

---

## ⚖️ License
Distributed under the **MIT License**. See `LICENSE` for more information.
