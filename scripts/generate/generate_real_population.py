"""Dispatcher for real population generation (SCB or SSB).

Accepts a --source argument to select the statistics API, then delegates
to the appropriate existing script with the remaining arguments.
"""

import argparse
import subprocess
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent

_SOURCE_SCRIPTS = {
    "scb": _SCRIPTS_DIR / "generate_scb_population.py",
    "ssb": _SCRIPTS_DIR / "generate_ssb_population.py",
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a real population from a statistics API (SCB or SSB)"
    )
    parser.add_argument(
        "--source",
        choices=list(_SOURCE_SCRIPTS.keys()),
        required=True,
        help="Statistics API to sample from (scb = Sweden, ssb = Norway)",
    )
    parser.add_argument("--n", type=int, default=1000, help="Number of individuals to sample")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for reproducibility")
    parser.add_argument("--output", type=str, default=None, help="Output JSON file path")

    args = parser.parse_args()

    target_script = _SOURCE_SCRIPTS[args.source]
    if not target_script.exists():
        raise FileNotFoundError(f"Target script not found: {target_script}")

    cmd = [sys.executable, str(target_script), "--n", str(args.n), "--seed", str(args.seed)]
    if args.output is not None:
        cmd.extend(["--output", args.output])

    result = subprocess.run(cmd, check=False)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
