"""Export browser fixtures through the production validator and compiler."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from geometry3d.geogebra.compiler import compile_construction  # noqa: E402
from geometry3d.geogebra.validation import validate_spec  # noqa: E402


FIXTURE_DIR = ROOT / "tests" / "fixtures" / "geogebra"
OUTPUT = ROOT / "frontend" / "e2e" / "fixtures" / "compiled-artifacts.json"
NAMES = ("tetrahedron", "projection", "line-plane", "undefined-intersection", "function2d", "surface")


def export() -> None:
    artifacts = {}
    for name in NAMES:
        raw = json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))
        artifact = compile_construction(validate_spec(raw))
        artifact.id = str(uuid5(NAMESPACE_URL, f"vision-agent/geogebra/{name}"))
        artifacts[name] = artifact.model_dump(mode="json")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(artifacts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    export()
