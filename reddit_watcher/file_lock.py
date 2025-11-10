import fcntl
import sys


class ExclusiveFileLock:
    def __init__(self, path: str, exit_on_fail: bool = True):
        self.path = path
        self.exit_on_fail = exit_on_fail
        self.file = None

    def __enter__(self):
        self.file = open(self.path, "w+")
        try:
            fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            msg = f"❌ Lock already held by another process: {self.path}"
            if self.exit_on_fail:
                print(msg, file=sys.stderr)
                sys.exit(1)
            else:
                raise
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file:
            try:
                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
            finally:
                self.file.close()
