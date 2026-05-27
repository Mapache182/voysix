# ADR 0004: Global Hotkey and Auto-Paste Implementation

* Status: Accepted
* Deciders: Antigravity, USER
* Date: 2026-05-14

## Context and Problem Statement

Voysix is designed to be a "ghost" application that lives in the system tray and interacts with other programs. To provide a smooth experience, the user needs to:
1. Trigger recording from any application without switching focus (Global Hotkeys).
2. Have the resulting text appear immediately at the cursor position (Auto-Paste).

Simulating user input and capturing global events is historically difficult in a cross-platform way, especially on Windows where low-level hooks can cause system-wide lag or crashes if not handled carefully.

## Decision Drivers

* **Compatibility**: Must work with 99% of Windows applications (Notepad, Word, Browsers, IDEs).
* **Stability**: Must not crash the OS or the application when hooks are active.
* **Latency**: The transition from "release hotkey" to "text appears" should be instantaneous.
* **User Experience**: Support for natural triggers like Mouse Middle Click.

## Considered Options

1. **Native OS APIs (User32.dll / Quartz)**: Writing platform-specific C-extensions for hooks.
2. **PyAutoGUI / Keyboard libraries**: Using high-level Python libraries for both hooks and simulation.
3. **Hybrid Hook/Paste (pynput + low-level API)**: Using `pynput` for event listening and direct `user32` calls for injection.

## Decision Outcome

Chosen option: **Hybrid Hook/Paste (pynput + low-level API)**.

### Implementation Details:
- **Global Listener**: Uses `pynput.mouse` and `pynput.keyboard` listeners.
- **Crash Prevention**: All listener callbacks are wrapped in a separate `threading.Thread`. This is critical on Windows to prevent `0xc000041d` (Fatal User Callback Exception) which happens if the hook thread blocks for too long.
- **Auto-Paste**:
    - The app copies the transcription to the system clipboard using `pyperclip`.
    - It then triggers a "Paste" command using the low-level `user32.keybd_event` (Ctrl+V) on Windows. 
    - Why not `pyautogui.typewrite`? Typing long texts character by character is slow and can be interrupted by the user. "Paste" is near-instant for any text length.
- **Media Integration**: Automatically pauses system media playback (Pause/Play button simulation) during recording to ensure clean audio.

### Consequences

* **Good**: Supports Middle-Click as a primary trigger, which is highly requested by power users.
* **Good**: Near-instant output of long paragraphs.
* **Bad**: Low-level hooks can sometimes be flagged as "suspicious" by overly aggressive Antivirus software.
* **Bad**: On some platforms (like Wayland on Linux), global hooks and injection are restricted by the OS for security reasons.

## Pros and Cons of the Options

### High-level libraries (PyAutoGUI)
* Good: Easy to write.
* Bad: `typewrite` is slow; unreliable global hotkey support on Windows.

### Native APIs only
* Good: Maximum performance.
* Bad: Extremely high maintenance cost; difficult to bridge with Python's event loop.

### Hybrid (Chosen)
* Good: Combines Python's ease of use for listening (`pynput`) with the reliability of native OS calls (`user32`) for injection.
* Good: Multi-threaded callbacks prevent system lag.
