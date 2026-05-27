"""Shared runtime knobs (configurable via environment variables).

These limits control how aggressively the pipeline tries before giving up.
Keeping them in one place lets us tune them without hunting through the
workflow files.
"""

from __future__ import annotations

import os


def max_impl_iterations() -> int:
    """Implementation-loop iteration budget.

    paper_7bd78579 (hyper_kggen) hit 800/800 with 24/28 files of
    substantive code (300-650 lines/file). The plan was 26 .py files and
    each took ~33 iterations on average — not loops, just real work.
    Bumped default to 1200 (~50% headroom) so dense reproductions don't
    get cut off near the finish line.

    Override with PAPER2CODE_MAX_IMPL_ITERATIONS env var.
    """
    raw = os.environ.get("PAPER2CODE_MAX_IMPL_ITERATIONS")
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return 1200
