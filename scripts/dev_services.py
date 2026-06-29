from __future__ import annotations

import argparse
import http.client
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Service:
    name: str
    command: list[str]
    health_host: str
    health_port: int


SERVICES = [
    Service(
        "demo-business-agent",
        ["uv", "run", "--package", "demo-business-agent", "demo-business-agent"],
        "localhost",
        8011,
    ),
    Service("master-agent", ["uv", "run", "--package", "master-agent", "master-agent"], "localhost", 8010),
    Service("agent-gateway", ["uv", "run", "--package", "agent-gateway", "agent-gateway"], "localhost", 8001),
    Service("agent-server", ["uv", "run", "--package", "agent-server", "agent-server"], "localhost", 8000),
]


def log(message: str) -> None:
    print(message, flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the local MVP agent services.")
    parser.add_argument("--health-timeout", type=float, default=20.0, help="Seconds to wait for all services to be healthy.")
    parser.add_argument(
        "--runtime-store",
        choices=("memory", "redis"),
        default=os.environ.get("AGENT_RUNTIME_STORE", "memory"),
        help="Runtime store to pass to all services.",
    )
    parser.add_argument(
        "--redis-url",
        default=os.environ.get("AGENT_REDIS_URL", "redis://localhost:6379/0"),
        help="Redis URL used when --runtime-store redis is selected.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OPENAI_MODEL"),
        help="Optional OPENAI_MODEL value to pass to agent services. Use 'test' for local PydanticAI TestModel smoke.",
    )
    parser.add_argument("--smoke", action="store_true", help="Run scripts/smoke_backend.py after all services are healthy.")
    parser.add_argument("--exit-after-smoke", action="store_true", help="Stop services after --smoke completes.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    processes: list[tuple[Service, subprocess.Popen[bytes]]] = []
    stopping = False

    def stop(_signum: int | None = None, _frame: object | None = None) -> None:
        nonlocal stopping
        if stopping:
            return
        stopping = True
        for service, process in processes:
            if process.poll() is None:
                log(f"stopping {service.name}")
                process.terminate()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    child_env = os.environ.copy()
    child_env["AGENT_RUNTIME_STORE"] = args.runtime_store
    child_env["AGENT_REDIS_URL"] = args.redis_url
    child_env.setdefault("UV_CACHE_DIR", "/tmp/agent-uv-cache")
    if args.model:
        child_env["OPENAI_MODEL"] = args.model

    if args.runtime_store == "redis" and not check_redis(args.redis_url):
        return 1

    try:
        for service in SERVICES:
            log(f"starting {service.name}: {' '.join(service.command)}")
            processes.append((service, subprocess.Popen(service.command, env=child_env)))

        if not wait_for_health(processes, timeout_seconds=args.health_timeout):
            return 1
        if args.smoke:
            smoke_code = run_smoke()
            if smoke_code != 0 or args.exit_after_smoke:
                return smoke_code

        while not stopping:
            for service, process in processes:
                code = process.poll()
                if code is not None:
                    log(f"{service.name} exited with {code}")
                    stop()
                    return code
            time.sleep(0.5)
    finally:
        stop()
        for _, process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
    return 0


def wait_for_health(processes: list[tuple[Service, subprocess.Popen[bytes]]], *, timeout_seconds: float) -> bool:
    pending = {service.name: service for service, _ in processes}
    deadline = time.time() + timeout_seconds
    while pending and time.time() < deadline:
        for service, process in processes:
            code = process.poll()
            if code is not None:
                log(f"{service.name} exited before becoming healthy with {code}")
                return False
        healthy = [service_name for service_name, service in pending.items() if is_healthy(service)]
        for service_name in healthy:
            log(f"{service_name} healthy")
            pending.pop(service_name, None)
        if pending:
            time.sleep(0.25)
    if pending:
        names = ", ".join(sorted(pending))
        log(f"services did not become healthy within {timeout_seconds:.1f}s: {names}")
        return False
    return True


def is_healthy(service: Service) -> bool:
    conn = http.client.HTTPConnection(service.health_host, service.health_port, timeout=1)
    try:
        conn.request("GET", "/health")
        response = conn.getresponse()
        response.read()
        return response.status == 200
    except OSError:
        return False
    finally:
        conn.close()


def check_redis(redis_url: str) -> bool:
    try:
        import redis

        client = redis.Redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        client.close()
    except Exception as exc:
        log(f"redis is not reachable at {redis_url}: {exc}")
        log("start Redis first, for example: docker compose -f deploy/docker-compose.yml up -d redis")
        return False
    return True


def run_smoke() -> int:
    script = Path(__file__).resolve().parent / "smoke_backend.py"
    log(f"running smoke: {sys.executable} {script}")
    return subprocess.run([sys.executable, str(script)], check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
