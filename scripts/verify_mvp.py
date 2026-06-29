from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from dev_services import check_redis


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the complete MVP verification suite.")
    parser.add_argument(
        "--redis",
        choices=("optional", "required", "skip"),
        default="optional",
        help="Whether to run the Redis-backed backend smoke.",
    )
    parser.add_argument(
        "--redis-url",
        default=os.environ.get("AGENT_REDIS_URL", "redis://localhost:6379/0"),
        help="Redis URL used for the Redis-backed backend smoke.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run([sys.executable, "scripts/verify_all.py"])
    run([sys.executable, "scripts/dev_services.py", "--smoke", "--exit-after-smoke"])

    if args.redis == "skip":
        print("redis-backed smoke skipped")
        return 0

    if not check_redis(args.redis_url):
        if args.redis == "required":
            return 1
        print("redis-backed smoke skipped because Redis is not reachable")
        return 0

    run(
        [
            sys.executable,
            "scripts/dev_services.py",
            "--runtime-store",
            "redis",
            "--redis-url",
            args.redis_url,
            "--smoke",
            "--exit-after-smoke",
        ]
    )
    return 0


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    sys.exit(main())
