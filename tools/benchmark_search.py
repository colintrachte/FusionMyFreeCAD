"""Compare SearchBar's substring baseline with FMF's catalog ranking."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fmf_catalog  # noqa: E402

DEFAULT_CORPUS = ROOT / "tests" / "fixtures" / "search-corpus.json"


def _baseline(query, entries):
    terms = query.casefold().split()
    return [
        entry
        for entry in entries
        if all(term in entry.searchable_text.casefold() for term in terms)
    ]


def _measure(provider, corpus, entries, repeats):
    ranks = []
    latencies = []
    for _repeat in range(repeats):
        started = time.perf_counter_ns()
        batch = [provider(item["query"], entries) for item in corpus]
        latencies.append((time.perf_counter_ns() - started) / 1_000_000)
    for item, results in zip(corpus, batch, strict=True):
        ids = [entry.id for entry in results]
        ranks.append(ids.index(item["expected"]) + 1 if item["expected"] in ids else None)
    reciprocal = [1 / value if value else 0 for value in ranks]
    return {
        "queries": len(corpus),
        "meanReciprocalRank": round(statistics.mean(reciprocal), 4),
        "top3Success": round(
            sum(value is not None and value <= 3 for value in ranks) / len(ranks), 4
        ),
        "misses": sum(value is None for value in ranks),
        "coldBatchMs": round(latencies[0], 4),
        "warmMedianBatchMs": round(statistics.median(latencies[1:] or latencies), 4),
    }


def run(corpus_path=DEFAULT_CORPUS, repeats=25):
    corpus = json.loads(Path(corpus_path).read_text(encoding="utf-8"))["queries"]
    entries = fmf_catalog.load_catalog()
    return {
        "schemaVersion": 1,
        "corpus": str(Path(corpus_path).relative_to(ROOT)).replace("\\", "/"),
        "providers": {
            "searchbar-substring-baseline": _measure(_baseline, corpus, entries, repeats),
            "fmf-catalog-ranker": _measure(fmf_catalog.rank, corpus, entries, repeats),
        },
        "decision": (
            "Keep SearchBar as the sole UI provider; use the shared FMF catalog "
            "for aliases and ranking."
        ),
        "coverage": ["command", "object", "preference", "help"],
        "packaging": "No second palette or new runtime dependency.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--repeats", type=int, default=25)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.corpus, arguments.repeats), indent=2))


if __name__ == "__main__":
    main()
