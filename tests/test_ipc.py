import socket

from gguf_dictate import ipc


def test_send_delivers_datagram():
    addr = b"\0dictate-test-" + str(id(object())).encode()
    rx = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    rx.bind(addr)
    rx.settimeout(2)
    ipc.send("note hello", addr)
    assert rx.recv(1024) == b"note hello"
    rx.close()


def test_send_without_listener_does_not_raise():
    ipc.send("rec", b"\0dictate-nobody-home")
