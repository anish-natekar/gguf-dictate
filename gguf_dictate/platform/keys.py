"""Global hotkey listener (pynput). Imported lazily: pynput needs a display at import time."""


def key_name(key):
    from pynput import keyboard
    return key.char.lower() if isinstance(key, keyboard.KeyCode) and key.char else getattr(key, "name", str(key))


def start_listener(router):
    from pynput import keyboard
    listener = keyboard.Listener(on_press=lambda k: router.press(key_name(k)), on_release=lambda k: router.release(key_name(k)))
    listener.start()
    return listener
