import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "benchmark_search", ROOT / "tools" / "benchmark_search.py"
)
BENCHMARK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BENCHMARK)


def test_catalog_ranker_improves_the_versioned_search_corpus():
    result = BENCHMARK.run(repeats=2)
    baseline = result["providers"]["searchbar-substring-baseline"]
    ranked = result["providers"]["fmf-catalog-ranker"]
    assert ranked["meanReciprocalRank"] > baseline["meanReciprocalRank"]
    assert ranked["top3Success"] >= 0.9
    assert ranked["misses"] < baseline["misses"]
    assert result["coverage"] == ["command", "object", "preference", "help"]
