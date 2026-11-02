"""Single-instance lock: held by an open file, released by the OS if the process dies."""
import os


class SingleInstance:
    def __init__(self, path):
        self.path, self.file = path, None

    def acquire(self):
        if self.file:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        f = open(self.path, "w")
        try:
            if os.name == "nt":      # untested: needs a Windows run
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            f.close()
            return False
        self.file = f
        return True

    def release(self):
        if self.file:
            self.file.close()        # closing drops the lock on both platforms
            self.file = None
