#!/usr/bin/env python3
"""
session_write — how the Owner-side tools write, and read, a file in a Robowright Session's folder or worktree.

A session can create any entry there: a symlink, a FIFO, a hard link to a file it cannot write itself. The worker
hooks, the launcher, session-state.py, run-cost.py and spend-guard.py write into that folder outside the sandbox, so
every write opens the name itself inside a directory that is not a link, follows a link at neither, never truncates
on open, and goes ahead only on a regular file with one link. A refused write creates and changes nothing.

    session_write.py append <path>    stdin appended to <path>, created if missing
    session_write.py replace <path>   <path>'s contents replaced by stdin, created if missing
    session_write.py check <path>...  each <path> one the other two would write; nothing is created or read
    session_write.py read <path>      <path>'s bytes on stdout: an absolute path with no `.`, `..` or empty part,
                                      every folder opened under the last without following a link, and a regular
                                      file with one link of at most 64 KiB

A refusal is `refused: <path>: <why>` on stderr, exit 2.
"""

import contextlib
import fcntl
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

import owner_git

EXIT_REFUSED = 2
EXIT_USAGE = 1
# The mode a plain `>` gives a new file under the usual umask.
FILE_MODE = 0o644
# O_NONBLOCK so a FIFO planted at the name refuses at once instead of waiting for a reader.
NO_FOLLOW = os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


class Refused(Exception):
    def __init__(self, path, why):
        super().__init__(f"{owner_git.shown(os.fspath(path))}: {why}")
        self.path = path


def open_file(path, flags) -> int:
    """A blocking fd on `path`, opened with `flags`, and O_CREAT unless `flags` carries O_RDONLY. Refused, with nothing
    created, when its directory or the name itself is a link, and refused once open unless it is a regular file with
    one link. FileNotFoundError when it is missing and not created."""
    parent, name = os.path.split(os.fspath(path))
    try:
        dir_fd = os.open(parent or ".", os.O_RDONLY | os.O_DIRECTORY | NO_FOLLOW)
    except OSError as error:
        raise Refused(path, f"its directory is a link or cannot be opened ({error.strerror})") from None
    try:
        fd = os.open(name, flags | (0 if flags == os.O_RDONLY else os.O_CREAT) | NO_FOLLOW, FILE_MODE, dir_fd=dir_fd)
    except FileNotFoundError:
        raise
    except OSError as error:
        raise Refused(path, f"a link, or not a file ({error.strerror})") from None
    finally:
        os.close(dir_fd)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        os.close(fd)
        raise Refused(path, "not a regular file with one link")
    os.set_blocking(fd, True)
    return fd


def write_all(fd, data: bytes):
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]


def as_bytes(data) -> bytes:
    return data if isinstance(data, bytes) else data.encode("utf-8", "surrogateescape")


def append(path, data):
    fd = open_file(path, os.O_WRONLY | os.O_APPEND)
    try:
        write_all(fd, as_bytes(data))
    finally:
        os.close(fd)


def replace(path, data):
    fd = open_file(path, os.O_WRONLY)
    try:
        os.ftruncate(fd, 0)
        write_all(fd, as_bytes(data))
    finally:
        os.close(fd)


def check(path):
    """Refused where `append` or `replace` would be; a missing file passes and is not created."""
    try:
        os.close(open_file(path, os.O_RDONLY))
    except FileNotFoundError:
        pass


def read(path) -> bytes:
    """`path`'s bytes through owner_git.read_unlinked, refused as the writes are. FileNotFoundError when it is
    missing."""
    try:
        return owner_git.read_unlinked(path)
    except owner_git.Unreadable as why:
        raise Refused(path, str(why)) from None


@contextlib.contextmanager
def locked(path):
    """`path` held under an exclusive flock for the block; the lock file is created if missing and never truncated."""
    fd = open_file(path, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def write_json_atomic(path, value):
    """`value` as run.json is written: a fresh temp file beside it, then a rename, which replaces a link at `path`
    rather than writing through it."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=".run.json.", dir=str(path.parent))
    with os.fdopen(fd, "w") as fh:
        json.dump(value, fh, indent=2)
        fh.write("\n")
    os.chmod(tmp, stat.S_IMODE(os.stat(path).st_mode))
    os.replace(tmp, path)


def main(argv) -> int:
    if not (len(argv) == 2 and argv[0] in ("append", "replace", "read") or len(argv) >= 2 and argv[0] == "check"):
        print("usage: session_write.py append|replace|read <path>, or check <path>...", file=sys.stderr)
        return EXIT_USAGE
    try:
        if argv[0] == "read":
            try:
                data = read(argv[1])
            except FileNotFoundError:
                raise Refused(argv[1], "missing") from None
            sys.stdout.buffer.write(data)
        elif argv[0] == "check":
            for path in argv[1:]:
                check(path)
        else:
            (append if argv[0] == "append" else replace)(argv[1], sys.stdin.buffer.read())
    except Refused as refusal:
        print(f"refused: {refusal}", file=sys.stderr)
        return EXIT_REFUSED
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
