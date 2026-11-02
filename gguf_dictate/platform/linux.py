"""Linux/X11 implementations of the interfaces core.pasting, core.dictation and core.meeting_recorder need (xdotool, notify-send, PipeWire)."""
import re
import subprocess
import threading

import numpy as np

from ..core.state import RATE
from .audio import BLOCK


class XdotoolKeys:
    def paste(self):
        subprocess.Popen(["xdotool", "key", "--clearmodifiers", "ctrl+v"])

    def type_text(self, text):
        subprocess.run(["xdotool", "type", "--clearmodifiers", "--delay", "1", "--", text], check=False)


class NotifySend:
    def toast(self, title, body):
        subprocess.Popen(["notify-send", "-i", "camera-photo", "-t", "3500", title, body])


class PipeWireMonitorSource:
    """System audio: whatever the default output device is playing, recorded from its monitor with `pw-record`.

    PipeWire does the resampling, so raw 16 kHz mono float32 comes straight off the pipe. The sink is fixed when
    recording starts; if the output device changes mid-meeting the stream ends and the system track stops there.
    """

    def __init__(self, popen=subprocess.Popen, run=subprocess.run, rate=RATE):
        self.popen, self.run, self.rate = popen, run, rate
        self.proc = self.thread = None

    def default_sink(self):
        try:
            out = self.run(["wpctl", "inspect", "@DEFAULT_AUDIO_SINK@"], capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError) as e:
            raise RuntimeError("system audio needs PipeWire with the 'wpctl' tool (sudo apt install wireplumber)") from e
        found = re.search(r'node\.name = "([^"]+)"', out)
        if not found:
            raise RuntimeError("no default audio output (sink) found")
        return found.group(1)

    def open(self, callback):
        cmd = ["pw-record", "--target", self.default_sink(), "-P", "stream.capture.sink=true",
               "--rate", str(self.rate), "--channels", "1", "--format", "f32", "-"]
        try:
            self.proc = self.popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError as e:
            raise RuntimeError("system audio needs 'pw-record' (sudo apt install pipewire-bin)") from e
        self.thread = threading.Thread(target=self.pump, args=(self.proc.stdout, callback), daemon=True)
        self.thread.start()

    @staticmethod
    def pump(stream, callback):
        pending = b""
        try:
            while True:
                data = stream.read(BLOCK * 4)
                if not data:
                    return      # a torn final sample is dropped
                pending += data
                whole = len(pending) // 4 * 4
                if whole:
                    callback(np.frombuffer(pending[:whole], dtype="<f4").astype(np.float32))
                    pending = pending[whole:]
        except (OSError, ValueError):
            return      # the pipe was closed under us by close()

    def close(self):
        proc, self.proc = self.proc, None
        if proc:
            proc.terminate()
            try:
                proc.wait(2)
            except subprocess.TimeoutExpired:
                proc.kill()
        if self.thread:
            self.thread.join(1)
            self.thread = None
        if proc and proc.stdout:
            proc.stdout.close()
