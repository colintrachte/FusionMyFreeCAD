# FMF command catalog

FMF has one discovery contract. `Resources/FMF/layout-v3.json` remains authoritative for which commands are present and where they appear. `Resources/FMF/command-catalog.json` adds only metadata that the layout cannot express: Fusion search aliases, preferred shortcuts, concise explanations, and object, preference, or help targets.

`fmf_catalog.py` merges those files into entries keyed by stable canonical IDs. An alias helps a user find an entry; it never replaces the FreeCAD command ID used for invocation. Search, shortcut planning, diagnostics, and future contextual guidance must consume this module rather than maintain separate maps.

## Entry contract

- `id`: canonical FreeCAD command ID or a namespaced non-command ID such as `preference:fmf-general`.
- `name`: visible canonical name.
- `kind`: `command`, `object`, `preference`, or `help`.
- `aliases`: additional discovery terms, including familiar Fusion language.
- `workbenches`: derived from the FMF layout for commands.
- `shortcut`: the FMF preset, when one exists.
- `target`: navigation target for non-command entries.
- `explanation`: concise semantic or availability guidance.
- `available`: runtime state; unavailable results remain explainable rather than disappearing.

## Search decision and benchmark

SearchBar remains FMF's only visible search provider because it already covers commands, document objects, and preferences. ToolSeek was studied as read-only prior art; FMF cleanly reimplements useful ranking properties in `fmf_catalog.py` and does not vendor or load ToolSeek.

Run the deterministic 32-query comparison with:

```powershell
python tools/benchmark_search.py
```

The versioned corpus is `tests/fixtures/search-corpus.json`. It includes exact names, Fusion aliases, abbreviations, typos, cross-workbench commands, objects, preferences, and help. The command reports mean reciprocal rank, top-three success, misses, and cold/warm batch latency. It also records the packaging decision: one UI provider and no new dependency.

The pure-Python benchmark cannot prove Qt lifetime safety, end-to-end keystroke latency, or live availability explanations. Those remain real-FreeCAD verification items.

## Adding metadata

1. Use the existing canonical command ID from FreeCAD or the layout.
2. Add only terms users genuinely search for; do not duplicate visible words.
3. Keep aliases semantic. Never route invocation through an alias.
4. Add or update a corpus query that demonstrates the need.
5. Run `pytest tests/test_catalog.py tests/test_searchbar.py -q` and the benchmark.
