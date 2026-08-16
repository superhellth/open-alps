"""Records how long pipeline phases take, so later runs can be compared against real numbers
instead of guesses - see pipeline/CLAUDE.md for why this matters (scope is expected to grow past
AT+Bayern, and this is how we'll see which phases stop scaling).

Appends one JSON line per phase to data/timings.jsonl. A phase's line is only written if its
`with phase(...):` block completes without raising - contextlib.contextmanager already skips the
post-yield code on an exception, so a failed run leaves no (misleading, partial) record.
"""

import json
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

TIMINGS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "timings.jsonl"


@contextmanager
def phase(script: str, name: str, **meta):
    t0 = time.monotonic()
    yield
    elapsed = time.monotonic() - t0
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "script": script,
        "phase": name,
        "seconds": round(elapsed, 2),
    }
    if meta:
        rec["meta"] = meta
    with open(TIMINGS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
