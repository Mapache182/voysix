# ADR 0005: Unified Build and Distribution System

* Status: Accepted
* Deciders: Antigravity, USER
* Date: 2026-05-14

## Context and Problem Statement

Distributing Python desktop applications to end-users is challenging. Users expect a single executable (preferably an installer) and should not be required to install Python or manage virtual environments manually. 

Additionally, we need a consistent way to update version numbers across multiple files (`main.py`, `setup.py`, installer scripts) to ensure telemetry and updates are accurate.

## Decision Drivers

* **User Experience**: One-click installation on Windows.
* **Consistency**: Automated versioning to prevent human error.
* **Reproducibility**: The same build process must work locally and in GitHub Actions.
* **Completeness**: All dependencies (FFmpeg, Tailscale, Whisper models) must be discoverable or bundled.

## Considered Options

1. **PyInstaller**: The most popular "freezer" for Python.
2. **cx_Freeze**: Another popular alternative with good support for complex DLL dependencies.
3. **Custom Build Orchestration**: Using a Python script to coordinate third-party tools.

## Decision Outcome

Chosen option: **Custom Build Orchestration (`build_dist.py`) using cx_Freeze and Inno Setup**.

### Implementation Details:
- **Freezing**: `cx_Freeze` is used to create a standalone directory containing the Python interpreter and all compiled dependencies. 
- **Installer**: **Inno Setup 6** is used to package the directory into a single `Voysix_Setup.exe`. It handles desktop shortcuts, registry keys (for autostart), and uninstallation.
- **Version Management**: `build_dist.py` acts as the single entry point. It:
    - Increments the patch version in `version.txt`.
    - Synchronizes this version across `main.py`, `setup.py`, and `installer.iss`.
    - Triggers the build and installer compilation in sequence.
- **CI/CD**: GitHub Actions uses the exact same `build_dist.py` script to ensure environment parity.

### Consequences

* **Good**: Reliable Windows installers with proper code/resource management.
* **Good**: Automated versioning ensures that every release is uniquely identifiable.
* **Bad**: `cx_Freeze` configuration can be verbose and fragile when dealing with large libraries like `torch` or `sounddevice`.
* **Bad**: Requires Inno Setup 6 to be installed on the build machine.

## Pros and Cons of the Options

### PyInstaller
* Good: Simple "one-file" mode.
* Bad: "One-file" mode is slow to start (unpacks to temp); problematic DLL discovery with some audio/AI libraries.

### Custom Orchestration (Chosen)
* Good: Full control over the build pipeline; clear separation of concerns (freezing vs. installing).
* Good: Faster startup compared to PyInstaller's one-file mode.
* Bad: Higher initial setup complexity.
