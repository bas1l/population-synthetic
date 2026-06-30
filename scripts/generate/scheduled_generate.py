"""
scheduled_generate.py -- Run identity generation at fixed clock times.

Before each scheduled run, any still-running previous generation process
is terminated (SIGTERM → SIGKILL fallback) as a safety measure.

Usage:
    python scripts/generate/scheduled_generate.py

Edit SCHEDULED_TIMES and MANIFEST below to change the configuration.
"""

import logging
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# ── Configuration ───────────────────────────────────────────────────
MANIFEST = "config/synthetic/manifests/identity_manifest_022_claude_sonnet.yaml"

# Each entry is an (hour, minute) tuple.
SCHEDULED_TIMES = [
    (1, 9),
    (1, 30),
    (3, 30),
]

# (hour, minute) — kills the active run and exits the script at this time.
STOP_TIME = (4, 55)
# ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("scheduler")

POLL_INTERVAL_SECONDS = 10


def kill_previous(proc: subprocess.Popen | None) -> None:
    """Terminate a running subprocess, escalating to kill if needed."""
    if proc is None or proc.poll() is not None:
        return
    log.warning("Terminating previous run (PID %d) ...", proc.pid)
    proc.terminate()
    try:
        proc.wait(timeout=15)
        log.info("Previous run terminated gracefully.")
    except subprocess.TimeoutExpired:
        log.warning("Graceful termination timed out — killing PID %d", proc.pid)
        proc.kill()
        proc.wait()
        log.info("Previous run killed.")


def launch(manifest: str) -> subprocess.Popen:
    """Start a new generation subprocess."""
    target = Path(__file__).resolve().parent / "generate_identities_parallel.py"
    cmd = [
        sys.executable,
        str(target),
        "--manifest", manifest,
    ]
    log.info("Launching: %s", " ".join(cmd))
    return subprocess.Popen(cmd)


def resolve_next(hour: int, minute: int, after: datetime) -> datetime:
    """Return the next occurrence of (hour, minute) strictly after the given datetime."""
    today = after.date()
    dt = datetime.combine(today, datetime.min.time().replace(hour=hour, minute=minute))
    if dt <= after:
        dt = datetime.combine(today + timedelta(days=1), dt.time())
    return dt


def build_schedule() -> tuple[list[datetime], datetime]:
    """Return (sorted launch times, stop time). Times already past are pushed to tomorrow."""
    now = datetime.now()
    stop = resolve_next(*STOP_TIME, after=now)
    times = []
    for hour, minute in SCHEDULED_TIMES:
        dt = resolve_next(hour, minute, after=now)
        if dt < stop:
            times.append(dt)
        else:
            log.info("Skipping %s (at or after stop time %s).", dt.strftime("%Y-%m-%d %H:%M"), stop.strftime("%H:%M"))
    times.sort()
    return times, stop


def main() -> None:
    manifest_path = Path(MANIFEST)
    if not manifest_path.exists():
        log.error("Manifest not found: %s", manifest_path)
        sys.exit(1)

    schedule, stop = build_schedule()
    if not schedule:
        log.info("No scheduled times before stop time %s. Exiting.", stop.strftime("%Y-%m-%d %H:%M"))
        return

    log.info(
        "Scheduled runs: %s  |  Stop: %s",
        ", ".join(t.strftime("%Y-%m-%d %H:%M") for t in schedule),
        stop.strftime("%Y-%m-%d %H:%M"),
    )

    active_proc: subprocess.Popen | None = None

    try:
        for target_time in schedule:
            wait_seconds = (target_time - datetime.now()).total_seconds()
            if wait_seconds > 0:
                log.info(
                    "Waiting until %s (%.0f min) ...",
                    target_time.strftime("%Y-%m-%d %H:%M"),
                    wait_seconds / 60,
                )
                while datetime.now() < target_time:
                    time.sleep(POLL_INTERVAL_SECONDS)

            log.info("── Trigger: %s ──", target_time.strftime("%H:%M"))
            kill_previous(active_proc)
            active_proc = launch(MANIFEST)

        log.info("All runs launched. Waiting for final run or stop time %s ...", stop.strftime("%H:%M"))
        if active_proc is not None:
            while active_proc.poll() is None:
                if datetime.now() >= stop:
                    log.warning("Stop time reached. Terminating active run.")
                    kill_previous(active_proc)
                    break
                time.sleep(POLL_INTERVAL_SECONDS)
            else:
                log.info("Final run exited with code %d.", active_proc.returncode)

    except KeyboardInterrupt:
        log.warning("Interrupted by user.")
        kill_previous(active_proc)
        sys.exit(130)

    log.info("Scheduler finished.")


if __name__ == "__main__":
    main()
