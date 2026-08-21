# Research brief: FreeCAD advantages worth surfacing in FusionMyFreeCAD

**Status:** Independent research pass for implementation
**Date:** 2026-08-01
**Question:** Which FreeCAD capabilities are legitimately stronger or more flexible than Autodesk Fusion for a mechanical CAD user, are likely to be used repeatedly, and should be placed in context-specific ribbons?
**Method:** Compared current FreeCAD documentation and 1.1.3 source with current Autodesk documentation. Reviewed parameterization, cross-body geometry, low-level solid operations, inspection, automation, mesh work, drawings, and assembly. Product claims were rejected where the advantage was only price, openness, or preference rather than capability or workflow.

## Executive finding

Three advantages justify primary UI space:

1. **Property- and spreadsheet-driven parametrics.** Fusion has the cleaner conventional parameter manager, but FreeCAD expressions can reference arbitrary object properties, named sketch constraints, spreadsheet aliases, computed shape information, conditionals, units, and—with limitations—other documents [1]. A parameter spreadsheet can also mix driving values, calculations, model-derived reporting, and notes [2]. This is a flexibility advantage, not a usability advantage.
2. **Granular linked geometry.** SubShapeBinder can reference objects, faces, edges, or vertices from multiple parents and even external documents, while tracking placement and optionally offsetting 2D geometry [3]. Fusion Derive is capable and easier for normal component reuse, but its documented unit of derivation is a selected set of components, bodies, sketches, construction geometry, or parameters from a design [4]. FreeCAD's binder is unusually granular inside the feature model.
3. **Low-level B-rep surgery and diagnosis.** Boolean Fragments exposes Open Cascade's General Fuse operation, creates every non-overlapping fragment, supports mixed inputs and fuzzy tolerance, and remains parametric [5]. Refine Shape removes residual planar/cylindrical splitter edges [6]. Check Geometry can perform the more expensive Boolean-operation check [7]. Fusion has Combine, Boundary Fill, and Validate, so FreeCAD is not categorically better at booleans; its advantage is direct access to lower-level topology, all-fragment output, tolerance, and cleanup.

These should be surfaced without making unrelated workbenches noisy:

- Part Design: **Parameter Table** and **Linked Geometry**.
- Sketcher: retain the already-prominent **Under-Constrained**, **Conflicts**, **Project / Include**, and **Carbon Copy** tools.
- Part: create a focused ribbon for **Boolean**, **Split**, **Repair**, and **Inspect** operations.

## What already exists / key findings

### 1. Parameter tables and expressions

FreeCAD expressions can read normal object properties and shape-derived values, use named spreadsheet cells, preserve physical units, and use conditional expressions [1]. This is more open-ended than a normal user-parameter table. Fusion's current parameter dialog is substantially friendlier and supports named user parameters, expressions, text values, favorites, automatic updates, and import/export [8].

**Decision:** Add a one-click Parameter Table command, but do not claim that FreeCAD's parameter UI is better. The command should create or reopen a native spreadsheet and leave the native editor intact.

### 2. Cross-body and cross-document references

SubShapeBinder accepts geometry from one or multiple parent objects, can link external documents, tracks relative placement, and can produce faces or 2D offsets [3]. Fusion Derive links model objects and parameters between designs and is well suited to component reuse [4].

**Decision:** Put SubShapeBinder in Part Design's Construct panel as **Linked Geometry**. Do not substitute it for ordinary sketch projection or put it in Sketcher, where it cannot be used directly.

### 3. Solid splitting, cleanup, and imported geometry

Boolean Fragments computes all fragments from intersecting inputs and offers Standard, Split, and CompSolid output modes plus tolerance [5]. Refine Shape removes unnecessary residual edges, and FreeCAD's import documentation specifically uses Shape From Mesh → Make Solid → Refine Shape as a conversion pipeline while warning that FreeCAD's mesh repair itself is limited [6, 9]. Fusion's Boundary Fill also creates cells from intersecting solids, surfaces, and planes [10], so Boolean Fragments is an advanced-control advantage rather than a unique operation.

**Decision:** Add an authoritative Part ribbon with primitives/import conversion, ordinary booleans, Boolean Fragments, Slice Apart, Explode Compound, Refine Shape, Defeaturing, Check Geometry, and Measure. Keep these out of Part Design because most act on selected generic Part shapes and imported topology, not an active Part Design feature.

### 4. Inspection and dependency visibility

FreeCAD exposes geometry validation and its native tree is unusually transparent. The project already makes Check Geometry prominent and restores the native Model tree. The dependency graph is useful for debugging but depends on an additional graph-rendering path and is not a frequent modeling command.

**Decision:** Keep Check Geometry primary. Do not consume ribbon space with Dependency Graph by default.

### 5. Automation

FreeCAD's integrated Python console, macro recorder, and Python-level access to workbenches and document objects are unusually direct [11]. Fusion also has Python scripts and add-ins, but its documented workflow centers on creating and managing scripts through the Scripts and Add-Ins system [12].

**Decision:** This is a real FreeCAD advantage for automation-heavy users, but not a likely high-frequency modeling command for this UI. Keep it available through the menu/search rather than expanding every contextual ribbon.

## Ideas or implications

- Context beats completeness: Part Design should gain only the binder and parameter entry points; generic topology tools belong in Part.
- Adaptive pinning should also operate in the new Part ribbon. Initial frequent defaults should favor Boolean Fragments, Refine Shape, Defeaturing, and Check Geometry, then yield to actual usage.
- The parameter command should preserve FreeCAD's native spreadsheet rather than invent a Fusion-styled editor that hides expressions and aliases.
- Labels should describe intent: **Linked Geometry**, **Parameter Table**, **All Fragments**, **Remove Features**, and **Clean Edges** are clearer than internal class names.

## Contradictions and uncertainty

- Fusion's parameter manager is easier for ordinary named dimensions [8]. FreeCAD wins only when arbitrary properties, spreadsheet calculations, reports, or cross-document expressions matter.
- Fusion Boundary Fill overlaps Boolean Fragments and is often easier [10]. FreeCAD's advantage is access to all fragments, aggregation modes, fuzziness, and scripting—not basic cell selection.
- FreeCAD documentation explicitly describes its mesh repair capabilities as limited [9]. Mesh tools should not be promoted as a FreeCAD-over-Fusion advantage.
- SubShapeBinder is flexible but can create complicated dependency graphs and external-file relationships. It should be visible, not automatically used.

## Gaps and open questions

- Real usage telemetry will determine whether Parameter Table and Linked Geometry deserve large-button status after several weeks.
- Boolean Fragments and Defeaturing are selection-sensitive; their disabled state is expected when no suitable topology is selected.
- This pass did not claim advantages in CAM, drawings, simulation, assembly, or organic modeling because the sources did not support a broad FreeCAD superiority claim for the user's likely mechanical workflow.

## Suggested decision or next experiment

Implement the two Part Design entry points and the focused Part ribbon, add Part commands to adaptive usage tracking, and keep the rest of FreeCAD's native specialized workbenches available without forcibly reskinning them. Revisit the Part defaults after usage telemetry has accumulated.

## Sources

1. FreeCAD Expressions: https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Expressions.md
2. FreeCAD Spreadsheet Workbench: https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Spreadsheet_Workbench.md
3. FreeCAD PartDesign SubShapeBinder: https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/PartDesign_SubShapeBinder.md
4. Autodesk Fusion Derive: https://help.autodesk.com/cloudhelp/ENU/Fusion-Assemble/files/ASM-DERIVE.htm
5. FreeCAD Part Boolean Fragments: https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Part_BooleanFragments.md
6. FreeCAD Part Refine Shape: https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Part_RefineShape.md
7. FreeCAD glossary, BOP check: https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Glossary.md
8. Autodesk Fusion Change Parameters: https://help.autodesk.com/cloudhelp/ENU/Fusion-Model/files/SLD-MODIFY-CHANGE-PARAMETERS.htm
9. FreeCAD Mesh to Part workflow: https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/FreeCAD_and_Mesh_Import.md
10. Autodesk Fusion Boundary Fill: https://help.autodesk.com/cloudhelp/ENU/Fusion-Model/files/GUID-575E005F-8D01-40C6-8399-602D6B196ED4.htm
11. FreeCAD product features, Python everywhere: https://www.freecad.org/features.php
12. Autodesk Fusion Scripts and Add-Ins: https://help.autodesk.com/cloudhelp/ENU/Fusion-Model/files/SLD-MANAGE-SCRIPTS-ADD-INS.htm

Local command verification used FreeCAD 1.1.3 source at `D:\Git\FreeCAD\src\Mod\PartDesign\Gui\Command.cpp`, `D:\Git\FreeCAD\src\Mod\Part\Gui\Command.cpp`, `D:\Git\FreeCAD\src\Mod\Part\Gui\CommandSimple.cpp`, `D:\Git\FreeCAD\src\Mod\Part\BOPTools\SplitFeatures.py`, and `D:\Git\FreeCAD\src\Mod\Spreadsheet\Gui\Command.cpp`.
