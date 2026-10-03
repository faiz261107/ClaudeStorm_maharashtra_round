"""
One-command launcher for Re:Learn.

    python run.py            # generate data + train (first time only), evaluate, start the server, open the browser
    python run.py --retrain  # force regenerate + retrain + re-evaluate
    python run.py --no-open  # don't open a browser tab
    python run.py --port 9000

Everything is CPU-only and takes a few seconds on first run.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

# Windows consoles may default to a legacy code page; keep ✓/✗/≥ printable.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
PY = sys.executable


def run(label: str, *args: str) -> None:
    print(f"\n==> {label}")
    subprocess.run([PY, *args], cwd=ROOT, check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--retrain", action="store_true")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()

    try:
        import fastapi, sklearn, uvicorn  # noqa: F401
    except ImportError:
        sys.exit("Dependencies missing. Run:  pip install -r requirements.txt")

    model = ROOT / "ml" / "models" / "classifier.joblib"
    metrics = ROOT / "ml" / "reports" / "metrics.json"
    if a.retrain or not (ROOT / "ml" / "data" / "responses.csv").exists():
        run("Generating dataset", "ml/generate_dataset.py")
    if a.retrain or not model.exists():
        run("Training classifier", "ml/train.py")
    if a.retrain or not metrics.exists():
        run("Evaluating (held-out questions, unseen misconceptions, calibration)", "ml/evaluate.py")

    url = f"http://{a.host}:{a.port}"
    print(f"\n==> Starting Re:Learn at {url}  (Ctrl+C to stop)\n")
    if not a.no_open:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    import uvicorn
    uvicorn.run("backend.app:app", host=a.host, port=a.port, reload=False, log_level="info")


if __name__ == "__main__":
    main()
