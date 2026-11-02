"""Microphone source on top of PortAudio (works on Linux, Windows and macOS)."""
from ..core.state import RATE

BLOCK = RATE // 50     # 20 ms


class SoundDeviceSource:
    def __init__(self):
        self.stream = None

    def open(self, callback):
        try:
            import sounddevice as sd
        except (ImportError, OSError) as e:      # OSError: the PortAudio library itself is missing
            raise RuntimeError("microphone needs the 'sounddevice' package and PortAudio (Linux: sudo apt install libportaudio2)") from e

        def on_audio(indata, frames, time_info, status):
            callback(indata[:, 0].copy())        # PortAudio reuses its buffer

        self.stream = sd.InputStream(samplerate=RATE, channels=1, dtype="float32", blocksize=BLOCK, callback=on_audio)
        self.stream.start()

    def close(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
