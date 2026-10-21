"""Build a local, attributed snapshot from an official geogebra/manual checkout."""

import argparse
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "geometry3d/geogebra/manual/commands.json"
PAGES = "en/modules/ROOT/pages/commands"


def build_snapshot(repo: Path) -> dict:
    revision = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain", "--", PAGES], text=True)
    if dirty:
        raise ValueError("command pages have local changes; use a clean checkout for reproducible attribution")
    documents = []
    for path in sorted((repo / PAGES).glob("*.adoc")):
        text = path.read_text(encoding="utf-8")
        first_line = text.splitlines()[0]
        documents.append({"command": path.stem, "title": re.sub(r"^=\s*", "", first_line), "content": text})
    if not documents:
        raise ValueError(f"no command pages found under {repo / PAGES}")
    return {"version": 1, "repository": "https://github.com/geogebra/manual", "revision": revision, "language": "en", "source_directory": PAGES, "documents": documents}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    snapshot = build_snapshot(args.source_repo.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Indexed {len(snapshot['documents'])} pages at {snapshot['revision']} -> {args.output}")


if __name__ == "__main__":
    main()
