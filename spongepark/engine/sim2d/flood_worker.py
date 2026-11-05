"""One 2D flood run in its own process:
``python -m spongepark.engine.sim2d.flood_worker <parent pid> <project folder> <option> <rp> <engine>``.

The storms of Simulate run side by side behind the app, one process each (:func:`..site.analysis.flood_storms`). This
process ends as soon as its parent does, so no storm goes on running after the engine has stopped.
"""

from __future__ import annotations

import os
import sys
import threading
import time


def _end_with_parent(pid: int) -> None:
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x00100000, False, pid)   # SYNCHRONIZE
        if handle:
            kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)
    else:
        while os.getppid() == pid:
            time.sleep(1.0)
    os._exit(1)


def main() -> None:
    from ..project import Project
    from .run import run2d

    parent, root, option, rp, engine = sys.argv[1:6]
    threading.Thread(target=_end_with_parent, args=(int(parent),), daemon=True).start()
    run2d(Project.open(root), option, int(rp), engine=engine)


if __name__ == "__main__":
    main()
