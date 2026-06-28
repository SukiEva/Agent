from __future__ import annotations

import signal
import subprocess
import sys
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Service:
    name: str
    command: list[str]


SERVICES = [
    Service("demo-business-agent", ["uv", "run", "--package", "demo-business-agent", "demo-business-agent"]),
    Service("master-agent", ["uv", "run", "--package", "master-agent", "master-agent"]),
    Service("agent-gateway", ["uv", "run", "--package", "agent-gateway", "agent-gateway"]),
    Service("agent-server", ["uv", "run", "--package", "agent-server", "agent-server"]),
]


def main() -> int:
    processes: list[tuple[Service, subprocess.Popen[bytes]]] = []
    stopping = False

    def stop(_signum: int | None = None, _frame: object | None = None) -> None:
        nonlocal stopping
        if stopping:
            return
        stopping = True
        for service, process in processes:
            if process.poll() is None:
                print(f"stopping {service.name}")
                process.terminate()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    try:
        for service in SERVICES:
            print(f"starting {service.name}: {' '.join(service.command)}")
            processes.append((service, subprocess.Popen(service.command)))

        while not stopping:
            for service, process in processes:
                code = process.poll()
                if code is not None:
                    print(f"{service.name} exited with {code}")
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


if __name__ == "__main__":
    sys.exit(main())
