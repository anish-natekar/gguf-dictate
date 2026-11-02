"""Tiny datagram messaging between dictate.py and the tray, over abstract unix sockets."""
import socket

OVERLAY = b"\0dictate-overlay"     # tray listens: rec | lvl <rms> | busy | idle | snip | paste | cancel | ctrlv | note <text>
CONTROL = b"\0dictate-control"     # dictate.py listens: start | stop


def send(msg, addr):
    """Fire-and-forget; harmless if nobody is listening."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        s.sendto(msg.encode(), addr)
    except OSError:
        pass
    finally:
        s.close()
