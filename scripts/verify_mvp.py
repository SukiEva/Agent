from __future__ import annotations

import argparse
from contextlib import AbstractContextManager, nullcontext
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse

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
    parser.add_argument(
        "--redis-start",
        choices=("auto", "none", "redis-server", "docker-run", "docker-compose"),
        default="auto",
        help="How to start a temporary Redis when --redis required is requested and Redis is not reachable.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run([sys.executable, "scripts/verify_all.py"])
    run([sys.executable, "scripts/dev_services.py", "--smoke", "--exit-after-smoke"])
    run([sys.executable, "scripts/dev_services.py", "--model", "test", "--smoke", "--exit-after-smoke"])

    if args.redis == "skip":
        print("redis-backed smoke skipped")
        return 0

    with _redis_context(args.redis, args.redis_url, args.redis_start) as redis_ready:
        if not redis_ready:
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


def _redis_context(redis_mode: str, redis_url: str, start_mode: str) -> AbstractContextManager[bool]:
    if check_redis(redis_url):
        return nullcontext(True)
    if redis_mode != "required" or start_mode == "none":
        return nullcontext(False)
    if start_mode in {"auto", "redis-server"} and shutil.which("redis-server"):
        return TempRedisServer(redis_url)
    if start_mode in {"auto", "docker-run"} and docker_run_available():
        return DockerRunRedis(redis_url)
    if start_mode in {"auto", "docker-compose"}:
        compose_command = docker_compose_command()
        if compose_command:
            return DockerComposeRedis(redis_url, compose_command)
    print("redis-backed smoke requires Redis, but no usable redis-server or docker executable was found")
    return nullcontext(False)


def docker_compose_command() -> list[str] | None:
    if shutil.which("docker"):
        command = ["docker", "compose"]
        if _command_succeeds([*command, "version"]):
            return command
    if shutil.which("docker-compose"):
        command = ["docker-compose"]
        if _command_succeeds([*command, "version"]):
            return command
    return None


def docker_run_available() -> bool:
    return bool(shutil.which("docker")) and _command_succeeds(["docker", "version"])


def _command_succeeds(command: list[str]) -> bool:
    try:
        return subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode == 0
    except OSError:
        return False


class TempRedisServer:
    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self.process: subprocess.Popen[bytes] | None = None
        self.tmpdir: tempfile.TemporaryDirectory[str] | None = None

    def __enter__(self) -> bool:
        parsed = urlparse(self.redis_url)
        port = parsed.port or 6379
        host = parsed.hostname or "127.0.0.1"
        self.tmpdir = tempfile.TemporaryDirectory(prefix="agent-redis-", dir="/tmp")
        command = [
            "redis-server",
            "--bind",
            host,
            "--port",
            str(port),
            "--save",
            "",
            "--appendonly",
            "no",
            "--dir",
            self.tmpdir.name,
        ]
        print("+", " ".join(command), flush=True)
        self.process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return _wait_for_redis(self.redis_url, timeout_seconds=5.0)

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        if self.tmpdir:
            self.tmpdir.cleanup()


class DockerComposeRedis:
    def __init__(self, redis_url: str, compose_command: list[str]) -> None:
        self.redis_url = redis_url
        self.compose_command = compose_command

    def __enter__(self) -> bool:
        compose_file = ROOT / "deploy" / "docker-compose.yml"
        command = [*self.compose_command, "-f", str(compose_file), "up", "-d", "redis"]
        print("+", " ".join(command), flush=True)
        try:
            subprocess.run(command, cwd=ROOT, check=True)
        except subprocess.CalledProcessError:
            return False
        return _wait_for_redis(self.redis_url, timeout_seconds=20.0)

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        compose_file = ROOT / "deploy" / "docker-compose.yml"
        subprocess.run([*self.compose_command, "-f", str(compose_file), "down"], cwd=ROOT, check=False)


class DockerRunRedis:
    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self.container_name = "agent-mvp-redis"

    def __enter__(self) -> bool:
        parsed = urlparse(self.redis_url)
        host_port = str(parsed.port or 6379)
        command = [
            "docker",
            "run",
            "--rm",
            "-d",
            "--name",
            self.container_name,
            "-p",
            f"{host_port}:6379",
            "redis:7-alpine",
        ]
        print("+", " ".join(command), flush=True)
        try:
            subprocess.run(command, cwd=ROOT, check=True)
        except subprocess.CalledProcessError:
            return False
        return _wait_for_redis(self.redis_url, timeout_seconds=20.0)

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        subprocess.run(["docker", "stop", self.container_name], cwd=ROOT, check=False)


def _wait_for_redis(redis_url: str, timeout_seconds: float) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if check_redis(redis_url):
            return True
        time.sleep(0.2)
    return False


if __name__ == "__main__":
    sys.exit(main())
