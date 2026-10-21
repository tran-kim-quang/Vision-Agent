"""Bounded, offline retrieval of official GeoGebra command documentation."""

from collections import Counter
from functools import lru_cache
import json
import math
from pathlib import Path
import re


SNAPSHOT = Path(__file__).with_name("manual") / "commands.json"
MAX_PAGE_CHARS = 4000


def _tokens(text: str) -> list[str]:
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    return re.findall(r"[a-z0-9]{2,}", text.lower())


@lru_cache(maxsize=1)
def _index():
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    documents = {doc["command"].lower(): doc for doc in snapshot["documents"]}
    frequencies, document_frequency = {}, Counter()
    for key, doc in documents.items():
        frequency = Counter(_tokens(doc["title"] + " " + doc["content"]))
        frequencies[key] = frequency
        document_frequency.update(frequency.keys())
    average_length = sum(sum(f.values()) for f in frequencies.values()) / max(1, len(documents))
    return snapshot, documents, frequencies, document_frequency, average_length


def _source(snapshot, doc):
    name = doc["command"]
    return {
        "command": name,
        "title": doc["title"],
        "revision": snapshot["revision"],
        "source_url": f"https://geogebra.github.io/docs/manual/en/commands/{name}/",
        "source_file_url": f"{snapshot['repository']}/blob/{snapshot['revision']}/{snapshot['source_directory']}/{name}.adoc",
    }


def _unavailable():
    return {"status": "unavailable", "message": "Local command snapshot is missing. Build it with scripts/sync_geogebra_docs.py; see README."}


@lru_cache(maxsize=1)
def construction_commands() -> dict[str, str]:
    """Math commands with documented signatures, excluding the manual's scripting category."""
    _, documents, _, _, _ = _index()
    scripting = documents['scripting_commands']['content']
    excluded = {name.lower() for name in re.findall(r"xref:/?commands/([^/\s]+?)\.adoc", scripting)}
    return {
        key: doc['command'] for key, doc in documents.items()
        if key not in excluded and re.search(rf"(?m)^{re.escape(doc['command'])}\s*\(", doc['content'])
    }


def search_geogebra_docs(query: str) -> dict:
    """Search English command names/concepts; returns at most five page summaries."""
    if not isinstance(query, str) or not query.strip() or len(query) > 500:
        return {"status": "invalid_query", "results": [], "message": "query must contain 1..500 characters"}
    try:
        snapshot, documents, frequencies, df, average_length = _index()
    except (OSError, ValueError, KeyError):
        return _unavailable()
    query_terms = set(_tokens(query))
    ranked = []
    for key, doc in documents.items():
        frequency = frequencies[key]
        length = sum(frequency.values())
        score = 0.0
        for term in query_terms:
            count = frequency[term]
            if count:
                idf = math.log(1 + (len(documents) - df[term] + 0.5) / (df[term] + 0.5))
                score += idf * count * 2.2 / (count + 1.2 * (0.25 + 0.75 * length / average_length))
        if query.strip().lower() == key:
            score += 100
        if score > 0:
            ranked.append((score, key, doc))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    results = []
    for _, _, doc in ranked[:5]:
        lines = [line.strip() for line in doc["content"].splitlines() if line.strip() and not line.startswith(("=", ":", "ifdef::"))]
        summary = " ".join(lines)[:240]
        results.append({**_source(snapshot, doc), "summary": summary})
    return {"status": "ok", "query": query, "revision": snapshot["revision"], "results": results}


def get_command_docs(command: str, offset: int = 0) -> dict:
    """Read one named command page, preserving syntax; continue via next_offset."""
    if not isinstance(command, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_]{0,99}", command):
        return {"status": "not_found", "message": "use a command name returned by search_geogebra_docs"}
    if type(offset) is not int or offset < 0:
        return {"status": "invalid_offset", "message": "offset must be a nonnegative integer"}
    try:
        snapshot, documents, _, _, _ = _index()
    except (OSError, ValueError, KeyError):
        return _unavailable()
    doc = documents.get(command.lower())
    if doc is None:
        return {"status": "not_found", "command": command}
    end = min(len(doc["content"]), offset + MAX_PAGE_CHARS)
    return {"status": "ok", **_source(snapshot, doc), "format": "asciidoc", "offset": offset,
            "content": doc["content"][offset:end], "next_offset": end if end < len(doc["content"]) else None}
