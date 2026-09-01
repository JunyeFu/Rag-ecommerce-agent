"""In-memory fixture server used only by Android instrumentation."""

from pathlib import Path

from .demo import create_demo_app

app = create_demo_app(Path(__file__).resolve().parents[4] / "data/demo/catalog.v3.jsonl")
