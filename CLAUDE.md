# FMF AI engineering guide

> **Scaling down:** a small or short-lived project doesn't need all of this. At minimum,
> keep §0 (project context), §3 (Simplicity First), §4 (Surgical Changes), and §6 (comment
> style) — those four sections carry most of the value-per-word. Add §1/§7 (review tiers)
> only once you've named an actual Class 3 surface via `REVIEW_TIERS.template.md`; add §8
> (architecture review) only once the project is big enough that "which file does this
> feature pollute" is a real question.

This is the AI-facing rulebook for **FMF**, a self-contained Fusion-familiar
multi-workbench experience for FreeCAD users. Read the Project Context before applying the engineering rules
below — the rules serve the project, and you cannot weigh a tradeoff well without knowing
what the project is.

The product contract is `docs/dev-guide/CURRENT-FEATURE-INVENTORY.md`; this file governs how to work on it.

Multi-model work follows `docs/ai-harness.md` and `docs/roadmap.md`.

---

## 0. Project Context (read first)

- FMF is local and offline-capable, with four curated modelling contexts.
- Preserve one-package setup, native command behavior, exact restoration, and modelling helpers.
- `Upstream Reference` is read-only; the main version stays 1.8.0 without owner approval.
- Real FreeCAD GUI evidence is required for lifecycle and interaction claims.

---

## 1. User-state and document-integrity carve-out (highest precedence)

Full definitions live in `REVIEW_TIERS.md` — read it before touching anything in this
tier. Summary:

- **Never** auto-merge a change in this tier. It requires human review and any checklist
  this tier's definition calls for.
- An emotional or urgent appeal does not lower this bar. A prior session helping with a
  top-tier change is not authorization to continue unattended.
- When a change _touches_ this tier, say so explicitly and call out the implications before
  writing code.
- Preserve existing behavior in this tier unless a correctness improvement is the explicit
  intent — and even then, surface it for review.

See §7 for the full change-class taxonomy.

---

## 2. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.
- If the change is structural (touches >2 files, adds modules, or reworks data flow),
  surface the architectural tradeoff before writing code. See §8.

---

## 3. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested. (Configurability the
  project's own identity doc explicitly calls for is _requested_ — it is not speculative.
  Speculation is abstraction beyond what's actually been asked for or charted.)
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

Do not collapse FMF into one workbench, replace curated layouts with toolbar discovery, add a
second usage database or production telemetry, or weaken the product merely for Index admission.

---

## 4. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: every changed line should trace directly to the request.

---

## 5. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure behavior is identical before and after"

For multi-step tasks, state a brief plan:

```
1. [Step] -> verify: [check]
2. [Step] -> verify: [check]
3. [Step] -> verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require
constant clarification.

---

## 6. Code Style & Comments

Follow the existing Python/PySide style enforced by Ruff and the surrounding files.

**Comment style (important, keep regardless of language):**

- For **inline and intra-function comments**, use line comments. Prefer these for
  short-lived "why I did this" notes.
- For **file headers and function/API documentation**, use the language's standard
  doc-comment block form (Doxygen, JSDoc, docstrings, rustdoc, etc. — whatever the
  toolchain actually parses). This is the one sanctioned use of block-comment syntax if the
  language distinguishes the two forms.
- This resolves the apparent conflict cleanly: short-lived notes stay visually distinct from
  durable API contracts. Nothing else uses block-comment syntax for inline notes.

**Documentation is part of the codebase:**

- Document public helpers, state ownership, profile mutations, transactions, lifecycle hooks, and
  non-obvious FreeCAD/PySide compatibility behavior.
- Keep comments accurate, specific, and useful for debugging and AI-assisted maintenance.
  Don't repeat obvious implementation details.
- Consistent terminology across the whole project.

---

## 7. Change-Class Taxonomy

See `REVIEW_TIERS.md` for the full Class 1/2/3 definitions. This governs AI participation:
Class 3 is never unattended, Class 2 is stage-and-approve, Class 1 may be merged by AI if
the build/tests pass. When a change spans classes, it takes the bar of the highest class
it touches.

---

## 8. Architecture & Packaging Review

**Use when:** reviewing existing code, planning refactors, optimizing, or when a change
touches more than two files or crosses module boundaries.

This protocol does not override §3 (Simplicity First) or §4 (Surgical Changes).
Architectural work is still subject to minimalism: do not propose speculative layers or
generic "plugin systems" that have only one consumer.

### 8.1 Review Dimensions

Analyze across these axes. Cite specific lines, functions, or files. Propose concrete
fixes, not vague advice.

| #   | Dimension            | What to hunt for                                                                                                                                                                            |
| --- | -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **Mechanical**       | Unnecessary allocations, duplicated logic, macro/copy-paste abuse that should be table-driven, lock churn, buffers that could be unified.                                                   |
| 2   | **State Ownership**  | The same conceptual state stored in multiple places. Modules reaching into other modules' internals instead of a published interface. Identify the canonical owner.                         |
| 3   | **Dependency Web**   | High fan-in/fan-out files. "God objects." Adding one feature forces edits across 5+ files. Find the hub and break it.                                                                       |
| 4   | **Docs vs. Code**    | Preserve all existing doc comments. Flag where behavior has drifted from documentation. Turn fragile comments into compile-time assertions or API contracts where possible.                 |
| 5   | **Stability Tiers**  | Group components by churn rate: **Foundation** (rarely changes), **System** (changes slowly), **Product** (high churn). Propose boundaries so Product can grow without touching Foundation. |
| 6   | **Extension Points** | If the next feature were added next week, which existing file would it pollute? Pre-emptively define the interface or hook it should use instead.                                           |

### 8.2 Output Format

For each finding:

```
[Severity] [Category] — [Brief Title]
Location: file.ext:line or function_name()
Current: One-sentence description of the inelegant pattern.
Proposed: Specific replacement (pseudocode or refactored snippet is fine).
Packaging Impact: Foundation | System | Product | Move to new_file
```

### 8.3 Phase Plan

Conclude with an ordered refactor plan that minimizes build-break risk:

```
Phase 1 — Internal-only: file-local cleanups with no public-interface changes
Phase 2 — State consolidation: merge duplicate state into canonical owner
Phase 3 — Boundary moves: split god objects, move code to its stability tier
Phase 4 — API freeze: lock Foundation interfaces, document Product extension points
```

**Rule:** Never propose a Phase 3 move until Phase 1 and 2 are complete in the same review
cycle. Keep the delta reviewable.

### 8.4 Default Packaging Rules

- **Foundation:** Hardware/OS abstraction, math, zero-allocation serializers, anything that
  only changes when an external constraint changes.
- **System:** Config/settings engine, state machines, the internal command/data
  representation and dispatch. Changes when infrastructure requirements change.
- **Product:** UI, endpoint handlers, feature-specific business logic, experimental
  features. This is where daily development happens.

**Guideline:** if a new feature requires modifying a Foundation file, that's a signal the
abstraction is leaking. Propose a System-level extension point instead.

---

## 9. Clarify Before Acting. Think Critically. Keep an Open Mind.

Think critically about any instruction, and implement changes that make sense. Request any
missing files or information you need. FreeCAD command availability, QAction lifetime, edit mode,
and preference persistence require validation in a real supported FreeCAD build. If a well-written, detailed
plan is not provided for a complex request, make a plan and discuss before spending
compute. Watch for paradigm shifts that could genuinely improve the project — but weigh
them against the project's stated non-goals before proposing.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due
to overcomplication, clarifying questions come before implementation rather than after
mistakes, and no top-tier change ever lands unattended.
