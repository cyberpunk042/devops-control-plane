"""
Request timing diagnostics for ``./manage.sh web --timing``.

When enabled, instruments every Flask request with:
  - Start / end timestamps (relative to server boot)
  - Duration in ms
  - Thread ID (to show concurrency)
  - Request method + path

On shutdown (Ctrl+C), prints a comprehensive summary:

  1. **Timeline** — every request in chronological order with duration
     bar, highlighting slow requests (>500ms) and very slow (>2s).
  2. **Gaps** — periods where no request was being served (indicates
     the browser was starved of connection slots).
  3. **Slowest endpoints** — top 15 by duration.
  4. **Per-endpoint stats** — count, total time, avg, max per route.
  5. **Concurrency** — peak concurrent threads serving requests.
  6. **Page load timeline** — first GET / to last request per load.

Zero overhead when not enabled — the module does nothing unless
``enable()`` is called.
"""

from __future__ import annotations

import atexit
import sys
import threading
import time
from dataclasses import dataclass, field

from flask import Flask, g, request

# ── State ────────────────────────────────────────────────────────

_enabled = False
_boot_time: float = 0.0
_lock = threading.Lock()
_records: list[RequestRecord] = []
_peak_concurrent = 0
_active_count = 0


@dataclass
class RequestRecord:
    """One completed request."""
    method: str
    path: str
    status: int
    start: float          # monotonic, relative to boot
    end: float            # monotonic, relative to boot
    duration_ms: float
    thread_id: int
    wall_start: str       # HH:MM:SS.mmm for display


# ── Public API ───────────────────────────────────────────────────

def enable(app: Flask) -> None:
    """Attach before/after hooks and register shutdown printer."""
    global _enabled, _boot_time
    _enabled = True
    _boot_time = time.monotonic()

    app.before_request(_timing_before)
    app.after_request(_timing_after)

    # atexit fires on normal exit — we also hook SIGINT below
    atexit.register(print_summary)

    # Hook into the graceful shutdown to print BEFORE os._exit
    _hook_shutdown_signal()


def is_enabled() -> bool:
    return _enabled


# ── Flask hooks ──────────────────────────────────────────────────

def _timing_before() -> None:
    """Record request start time and update concurrency counter."""
    global _peak_concurrent, _active_count

    g._timing_start = time.monotonic()
    g._timing_wall = time.strftime("%H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d}"

    with _lock:
        _active_count += 1
        if _active_count > _peak_concurrent:
            _peak_concurrent = _active_count


def _timing_after(response):
    """Record completed request."""
    global _active_count

    start = getattr(g, '_timing_start', None)
    if start is None:
        return response

    end = time.monotonic()
    duration_ms = (end - start) * 1000

    record = RequestRecord(
        method=request.method,
        path=request.path,
        status=response.status_code,
        start=start - _boot_time,
        end=end - _boot_time,
        duration_ms=round(duration_ms, 1),
        thread_id=threading.current_thread().ident or 0,
        wall_start=getattr(g, '_timing_wall', ''),
    )

    with _lock:
        _records.append(record)
        _active_count -= 1

    return response


# ── Summary printer ──────────────────────────────────────────────

# ANSI colors
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_CYAN = "\033[36m"
_MAGENTA = "\033[35m"
_WHITE = "\033[37m"

_summary_printed = False


def print_summary() -> None:
    """Print comprehensive timing summary to stderr."""
    global _summary_printed
    if _summary_printed or not _records:
        return
    _summary_printed = True

    out = sys.stderr
    records = sorted(_records, key=lambda r: r.start)

    out.write(f"\n{'=' * 80}\n")
    out.write(f"{_BOLD}{_CYAN}  ⏱  REQUEST TIMING SUMMARY{_RESET}\n")
    out.write(f"{'=' * 80}\n\n")

    total_requests = len(records)
    total_time = records[-1].end - records[0].start if total_requests > 1 else 0
    sse_records = [r for r in records if r.path == '/api/events']
    api_records = [r for r in records if r.path != '/api/events'
                   and not r.path.startswith('/static/')
                   and r.path != '/sw.js']

    out.write(f"  Total requests: {_BOLD}{total_requests}{_RESET}\n")
    out.write(f"  Wall time:      {_BOLD}{total_time:.1f}s{_RESET}\n")
    out.write(f"  SSE streams:    {len(sse_records)}\n")
    out.write(f"  API calls:      {len(api_records)}\n")
    out.write(f"  Peak concurrent: {_BOLD}{_peak_concurrent}{_RESET} threads\n")
    out.write(f"\n")

    # ── 1. Page Load Timelines ───────────────────────────────────
    # Group by GET / (page loads)
    page_loads: list[list[RequestRecord]] = []
    current_load: list[RequestRecord] = []
    for r in records:
        if r.method == 'GET' and r.path == '/':
            if current_load:
                page_loads.append(current_load)
            current_load = [r]
        else:
            current_load.append(r)
    if current_load:
        page_loads.append(current_load)

    if page_loads:
        out.write(f"{_BOLD}  ── Page Load Summary ──{_RESET}\n\n")
        for i, load in enumerate(page_loads):
            if not load:
                continue
            api_in_load = [r for r in load
                           if r.path != '/api/events'
                           and not r.path.startswith('/static/')
                           and r.path != '/'
                           and r.path != '/sw.js'
                           and r.path != '/.well-known/appspecific/com.chrome.devtools.json']
            if not api_in_load:
                continue
            first = load[0]
            last_api = max(api_in_load, key=lambda r: r.end)
            load_s = last_api.end - first.start
            slowest = max(api_in_load, key=lambda r: r.duration_ms)
            over_500 = [r for r in api_in_load if r.duration_ms > 500]

            out.write(f"  Load #{i+1} at {first.wall_start}\n")
            out.write(f"    Total:    {_BOLD}")
            if load_s > 5:
                out.write(f"{_RED}{load_s:.1f}s{_RESET}\n")
            elif load_s > 2:
                out.write(f"{_YELLOW}{load_s:.1f}s{_RESET}\n")
            else:
                out.write(f"{_GREEN}{load_s:.1f}s{_RESET}\n")
            out.write(f"    API calls: {len(api_in_load)}\n")
            out.write(f"    Slowest:  {slowest.path} ({slowest.duration_ms:.0f}ms)\n")
            if over_500:
                out.write(f"    {_YELLOW}Blocking (>500ms): {len(over_500)}{_RESET}\n")
                for r in sorted(over_500, key=lambda r: -r.duration_ms):
                    out.write(f"      {_RED}▸ {r.duration_ms:7.0f}ms{_RESET}  {r.method} {r.path}\n")
            out.write(f"\n")

    # ── 2. Full Request Timeline ─────────────────────────────────
    out.write(f"{_BOLD}  ── Request Timeline ──{_RESET}\n\n")
    out.write(f"  {'Time':>12}  {'Dur(ms)':>8}  {'Meth':4}  {'St':>3}  {'Path'}\n")
    out.write(f"  {'─'*12}  {'─'*8}  {'─'*4}  {'─'*3}  {'─'*40}\n")

    prev_end = None
    for r in records:
        # Skip SSE (long-lived, pollutes timeline)
        if r.path == '/api/events':
            continue

        # Detect gap (>200ms between end of last request and start of this one)
        if prev_end is not None:
            gap = r.start - prev_end
            if gap > 0.2:
                gap_ms = gap * 1000
                out.write(f"  {_DIM}{'':>12}  {'':>8}  {'':4}  {'':>3}  "
                          f"⏸ gap: {gap_ms:.0f}ms{_RESET}\n")

        # Color by duration
        if r.duration_ms > 2000:
            color = _RED
            marker = "🔴"
        elif r.duration_ms > 500:
            color = _YELLOW
            marker = "🟡"
        elif r.duration_ms > 100:
            color = _WHITE
            marker = "  "
        else:
            color = _DIM
            marker = "  "

        # Duration bar (1 char per 100ms, max 30)
        bar_len = min(30, int(r.duration_ms / 100))
        bar = "█" * bar_len if bar_len > 0 else "▏"

        out.write(
            f"  {r.wall_start:>12}  "
            f"{color}{r.duration_ms:7.0f}ms{_RESET}  "
            f"{r.method:4}  {r.status:>3}  "
            f"{r.path}"
        )
        out.write(f"  {color}{marker}{bar}{_RESET}\n")

        prev_end = r.end

    out.write(f"\n")

    # ── 3. Slowest Endpoints ─────────────────────────────────────
    out.write(f"{_BOLD}  ── Top 15 Slowest Requests ──{_RESET}\n\n")
    top = sorted(api_records, key=lambda r: -r.duration_ms)[:15]
    for r in top:
        if r.duration_ms > 2000:
            color = _RED
        elif r.duration_ms > 500:
            color = _YELLOW
        else:
            color = _RESET
        out.write(
            f"  {color}{r.duration_ms:7.0f}ms{_RESET}  "
            f"{r.method:4}  {r.path}\n"
        )
    out.write(f"\n")

    # ── 4. Per-Endpoint Aggregate ────────────────────────────────
    endpoint_stats: dict[str, dict] = {}
    for r in api_records:
        key = f"{r.method} {r.path}"
        if key not in endpoint_stats:
            endpoint_stats[key] = {
                'count': 0, 'total_ms': 0, 'max_ms': 0, 'min_ms': float('inf'),
            }
        s = endpoint_stats[key]
        s['count'] += 1
        s['total_ms'] += r.duration_ms
        s['max_ms'] = max(s['max_ms'], r.duration_ms)
        s['min_ms'] = min(s['min_ms'], r.duration_ms)

    if endpoint_stats:
        out.write(f"{_BOLD}  ── Per-Endpoint Stats ──{_RESET}\n\n")
        out.write(f"  {'Cnt':>4}  {'Total':>8}  {'Avg':>7}  {'Max':>7}  Endpoint\n")
        out.write(f"  {'─'*4}  {'─'*8}  {'─'*7}  {'─'*7}  {'─'*40}\n")

        for key in sorted(endpoint_stats, key=lambda k: -endpoint_stats[k]['total_ms']):
            s = endpoint_stats[key]
            avg = s['total_ms'] / s['count']
            out.write(
                f"  {s['count']:4d}  "
                f"{s['total_ms']:7.0f}ms  "
                f"{avg:6.0f}ms  "
                f"{s['max_ms']:6.0f}ms  "
                f"{key}\n"
            )
        out.write(f"\n")

    # ── 5. Gap Analysis ──────────────────────────────────────────
    non_sse = [r for r in records if r.path != '/api/events']
    gaps: list[tuple[float, float, RequestRecord, RequestRecord]] = []
    for i in range(1, len(non_sse)):
        prev = non_sse[i-1]
        curr = non_sse[i]
        gap = curr.start - prev.end
        if gap > 0.2:
            gaps.append((gap, prev.end, prev, curr))

    if gaps:
        out.write(f"{_BOLD}  ── Gaps (>200ms with no request served) ──{_RESET}\n\n")
        for gap_s, at, before, after in sorted(gaps, key=lambda g: -g[0]):
            gap_ms = gap_s * 1000
            color = _RED if gap_ms > 2000 else (_YELLOW if gap_ms > 500 else _RESET)
            out.write(
                f"  {color}{gap_ms:7.0f}ms{_RESET}  "
                f"after {before.path} → before {after.path}\n"
            )
        out.write(f"\n")

    # ── 6. Thread concurrency over time ──────────────────────────
    unique_threads = {r.thread_id for r in records}
    out.write(f"  Unique threads used: {len(unique_threads)}\n")
    out.write(f"  Peak concurrent:    {_peak_concurrent}\n")

    if _peak_concurrent <= 1:
        out.write(f"\n  {_RED}{_BOLD}⚠ SINGLE-THREADED BEHAVIOR DETECTED{_RESET}\n")
        out.write(f"  {_RED}  Despite threaded=True, requests are serialized.{_RESET}\n")
        out.write(f"  {_RED}  This means blocking calls stall ALL other requests.{_RESET}\n")
    elif _peak_concurrent < 3:
        out.write(f"\n  {_YELLOW}⚠ Low concurrency — most requests are serialized.{_RESET}\n")

    out.write(f"\n{'=' * 80}\n\n")
    out.flush()


# ── Signal hook ──────────────────────────────────────────────────

def _hook_shutdown_signal() -> None:
    """Insert our summary printer into the graceful shutdown chain.

    The server uses ``server_lifecycle.install_signal_handlers()``
    which replaces SIGINT/SIGTERM.  We monkey-patch the shutdown
    function to call our summary first.
    """
    from src.core.services import server_lifecycle

    _original = getattr(server_lifecycle, '_graceful_shutdown_original', None)
    if _original is not None:
        return  # Already hooked

    # We can't easily intercept the nested closure, so instead
    # we register an atexit handler and rely on the fact that
    # the summary prints BEFORE os._exit is called in the
    # shutdown handler.
    #
    # Since os._exit skips atexit, we hook into the signal
    # by wrapping the install function.
    original_install = server_lifecycle.install_signal_handlers

    def _patched_install() -> None:
        original_install()

        # Now re-wrap the signal handlers to print summary first
        import signal
        original_handler = signal.getsignal(signal.SIGINT)

        def _timing_shutdown(signum, frame):
            print_summary()
            if callable(original_handler):
                original_handler(signum, frame)

        signal.signal(signal.SIGINT, _timing_shutdown)
        signal.signal(signal.SIGTERM, _timing_shutdown)

    server_lifecycle.install_signal_handlers = _patched_install
