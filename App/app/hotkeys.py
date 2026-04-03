from pynput import mouse, keyboard
import threading

class GlobalListener:
    def __init__(self, on_press_callback, on_release_callback, on_abort_callback=None):
        self.on_press_callback = on_press_callback
        self.on_release_callback = on_release_callback
        self.on_abort_callback = on_abort_callback
        self.mouse_listener = None
        self.key_listener = None

    def start(self, hotkey_str="middle_click"):
        self.stop()
        
        
        # We always start a keyboard listener to catch 'Escape' for aborting
        self.key_listener = keyboard.Listener(
            on_press=lambda k: self._on_key(k, True, hotkey_str),
            on_release=lambda k: self._on_key(k, False, hotkey_str)
        )
        self.key_listener.start()
        
        if hotkey_str == "middle_click":
            self.mouse_listener = mouse.Listener(on_click=self._on_mouse_click)
            self.mouse_listener.start()
            print("Listening for Middle Click + Escape (abort)...")
        else:
            print(f"Listening for keyboard hotkey: {hotkey_str} + Escape (abort)")

    def _on_mouse_click(self, x, y, button, pressed):
        try:
            if button == mouse.Button.middle:
                self._trigger(pressed)
        except:
            pass
        return True # 🔹 CRITICAL: Explicitly return True for pynput to continue

    def _on_key(self, key, pressed, target_str):
        # Convert pynput key to string for comparison
        try:
            # Check for Escape (Abort)
            if key == keyboard.Key.esc:
                if pressed and self.on_abort_callback:
                    self._trigger_abort()
                return True

            if hasattr(key, 'char') and key.char:
                k_str = key.char.lower()
            else:
                k_str = str(key).replace('Key.', '').lower()
            
            if k_str == target_str.lower():
                self._trigger(pressed)
        except:
            pass
        return True # 🔹 CRITICAL: Explicitly return True for pynput to continue

    def _trigger_abort(self):
        def target():
            try:
                if self.on_abort_callback:
                    self.on_abort_callback()
            except Exception as e:
                print(f"Abort callback execution error: {e}")
        threading.Thread(target=target, daemon=True).start()

    def _trigger(self, pressed):
        def target():
            try:
                if pressed:
                    if self.on_press_callback:
                        self.on_press_callback()
                else:
                    if self.on_release_callback:
                        self.on_release_callback()
            except Exception as e:
                print(f"Listener callback execution error: {e}")
        
        # 🔹 CRITICAL: Run in a separate thread to avoid blocking the OS hook thread.
        # This prevents 0xc000041d (FATAL_USER_CALLBACK_EXCEPTION).
        threading.Thread(target=target, daemon=True).start()

    def stop(self):
        if self.mouse_listener:
            try: self.mouse_listener.stop()
            except: pass
            self.mouse_listener = None
        if self.key_listener:
            try: self.key_listener.stop()
            except: pass
            self.key_listener = None
