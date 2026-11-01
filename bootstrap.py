"""Double-click launcher setup and browser startup; uses only Python's standard library."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent


def environment_python(environment: Path) -> Path:
    return environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def setup() -> Path:
    if sys.version_info < (3, 11):
        raise RuntimeError("Install Python 3.11 or newer, then double-click the launcher again.")
    environment = ROOT / ".venv"
    interpreter = environment_python(environment)
    if not interpreter.exists():
        print("First run: creating a private Python environment...", flush=True)
        subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
    requirements = ROOT / "requirements.txt"
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    marker = environment / ".trend-lab-requirements"
    configured = marker.exists() and marker.read_text().strip() == digest
    if configured:
        check = subprocess.run(
            [str(interpreter), "-c", "import streamlit, yfinance, plotly, pyarrow, pandas_market_calendars"],
            capture_output=True,
        )
        configured = check.returncode == 0
    if not configured:
        print("Installing the app's packages. The first run needs Internet access and may take several minutes.",
              flush=True)
        subprocess.run([str(interpreter), "-m", "pip", "install", "-r", str(requirements)], check=True)
        marker.write_text(digest)
    else:
        print("Setup is already complete.", flush=True)
    return interpreter


def available_port() -> int:
    for port in range(8501, 8521):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def serve(interpreter: Path, *, smoke_test: bool = False) -> None:
    port = available_port()
    address = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [str(interpreter), "-m", "streamlit", "run", str(ROOT / "app.py"),
         "--server.address", "127.0.0.1", "--server.port", str(port),
         "--server.headless", "true", "--browser.gatherUsageStats", "false"],
        cwd=ROOT,
    )
    # Local readiness must not be sent through a system HTTP proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"Dashboard exited before startup (exit code {process.returncode}).")
            try:
                with opener.open(address + "/_stcore/health", timeout=2) as response:
                    if response.status == 200 and response.read().strip() == b"ok":
                        break
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(0.25)
        else:
            raise RuntimeError("The dashboard did not become ready within 90 seconds.")
        print(f"\nMA Trend Lab is ready: {address}", flush=True)
        if smoke_test:
            print("Launcher smoke check passed: HTTP 200.", flush=True)
            return
        print("Opening your browser. Keep this window open while using the app.", flush=True)
        if not webbrowser.open(address):
            print(f"Click or open this address in your browser: {address}", flush=True)
        process.wait()
        if process.returncode:
            raise RuntimeError(f"Dashboard stopped with exit code {process.returncode}.")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-test", action="store_true", help="Set up, verify startup, then stop without a browser")
    args = parser.parse_args()
    try:
        serve(setup(), smoke_test=args.smoke_test)
        return 0
    except KeyboardInterrupt:
        return 0
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"\nUnable to start MA Trend Lab: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
