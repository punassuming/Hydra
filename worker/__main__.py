"""Entry point for ``python -m worker``.

Supports two runtime modes:

1. **Worker mode** (default): runs the Hydra worker process.

   .. code-block:: sh

       python -m worker

2. **Bootstrap mode**: manages the Windows Task Scheduler watchdog task.

   .. code-block:: sh

       python -m worker bootstrap install
       python -m worker bootstrap remove
       python -m worker bootstrap run
       python -m worker bootstrap validate

"""
from __future__ import annotations

import sys


def main() -> None:
    # Detect "bootstrap" sub-mode: the first positional argument (after any
    # flags) is the word "bootstrap".
    if len(sys.argv) > 1 and sys.argv[1] == "bootstrap":
        from .bootstrap import main as bootstrap_main
        sys.exit(bootstrap_main(sys.argv[2:]))
    else:
        # Normal worker entrypoint — import and run the worker.
        from .worker import worker_main
        worker_main()


if __name__ == "__main__":
    main()
