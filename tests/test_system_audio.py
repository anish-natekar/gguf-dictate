import io
import subprocess

import numpy as np
import pytest

from gguf_dictate.platform import UnsupportedSystemAudio, default_system_source
from gguf_dictate.platform.linux import PipeWireMonitorSource

WPCTL = '''id 52, type PipeWire:Interface:Node
    node.description = "Family 17h/19h HD Audio Controller Analog Stereo"
  * node.name = "alsa_output.pci-0000_06_00.6.analog-stereo"
    media.class = "Audio/Sink"
'''


class FakeProc:
    def __init__(self, data=b""):
        self.stdout, self.terminated, self.killed = io.BytesIO(data), 0, 0

    def terminate(self):
        self.terminated += 1

    def kill(self):
        self.killed += 1

    def wait(self, timeout=None):
        return 0


def make(data=b"", wpctl=WPCTL, run_error=None, popen_error=None):
    procs, calls = [], []

    def run(cmd, **kw):
        calls.append(cmd)
        if run_error:
            raise run_error
        return subprocess.CompletedProcess(cmd, 0, stdout=wpctl)

    def popen(cmd, **kw):
        calls.append(cmd)
        if popen_error:
            raise popen_error
        procs.append(FakeProc(data))
        return procs[-1]

    return PipeWireMonitorSource(popen=popen, run=run), procs, calls


def collect(src):
    got = []
    src.open(lambda chunk: got.append(chunk))
    src.thread.join(2)
    return got


def test_records_the_default_sink_monitor_as_16k_mono_float():
    src, procs, calls = make(np.arange(10, dtype="<f4").tobytes())
    collect(src)
    cmd = calls[-1]
    assert cmd[0] == "pw-record" and cmd[-1] == "-"
    assert cmd[cmd.index("--target") + 1] == "alsa_output.pci-0000_06_00.6.analog-stereo"
    assert "stream.capture.sink=true" in cmd
    assert cmd[cmd.index("--rate") + 1] == "16000" and cmd[cmd.index("--channels") + 1] == "1" and cmd[cmd.index("--format") + 1] == "f32"


def test_delivers_every_sample_as_float32():
    data = np.linspace(-1, 1, 5000, dtype="<f4")
    src, *_ = make(data.tobytes())
    got = collect(src)
    assert all(c.dtype == np.float32 for c in got) and len(got) > 1
    assert np.array_equal(np.concatenate(got), data)


def test_a_torn_final_sample_is_dropped():
    src, *_ = make(np.ones(10, "<f4").tobytes() + b"\x00\x00")
    assert sum(len(c) for c in collect(src)) == 10


def test_missing_wpctl_gives_an_actionable_error():
    src, *_ = make(run_error=FileNotFoundError("wpctl"))
    with pytest.raises(RuntimeError, match="PipeWire"):
        src.open(lambda c: None)


def test_no_default_sink_is_an_error():
    src, *_ = make(wpctl="Could not find default sink")
    with pytest.raises(RuntimeError, match="sink"):
        src.open(lambda c: None)


def test_missing_pw_record_gives_an_actionable_error():
    src, *_ = make(popen_error=FileNotFoundError("pw-record"))
    with pytest.raises(RuntimeError, match="pw-record"):
        src.open(lambda c: None)


def test_close_stops_the_process_and_is_idempotent():
    src, procs, _ = make(b"")
    src.open(lambda c: None)
    src.close()
    src.close()
    assert procs[0].terminated == 1


def test_close_before_open_is_harmless():
    make()[0].close()


def test_default_system_source_per_platform():
    assert isinstance(default_system_source("linux"), PipeWireMonitorSource)
    other = default_system_source("win32")
    assert isinstance(other, UnsupportedSystemAudio)
    with pytest.raises(RuntimeError, match="not supported"):
        other.open(lambda c: None)
    other.close()
