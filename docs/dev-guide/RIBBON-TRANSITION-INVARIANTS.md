# Ribbon Transition Invariants

FMF previously treated sketch entry and exit as commands to activate FMF Sketch and FMF Design.
That competed with FreeCAD's own edit-mode transition and caused re-entrant Ribbon rebuilding.
Depending on signal timing, Sketch and Design panels could then occupy the same category.

The permanent design is passive:

- FreeCAD owns the active workbench during sketch entry and exit.
- FMF's sketch observer changes only the visible Ribbon context.
- A programmatic Ribbon context change never invokes the user tab handler.
- Only a real user tab choice calls `Gui.activateWorkbench()`.
- Each workbench category is built at most once during normal operation.
- Resize events never replace live panel widgets. Compact commands remain in overflow menus.
- Part and Surface are user choices and are never selected automatically around sketch editing.

Do not restore delayed `Gui.activateWorkbench()` calls to `slotInEdit()` or `slotResetEdit()`. Extra
event-loop turns do not establish ownership; they only make the race less frequent. Likewise, do
not restore repeated `onWbActivated()`, `ApplicationMenus()`, or `buildPanels()` calls in the user
tab handler. Those were symptom-level recovery attempts, not required synchronization.

`tools/check_ribbon_transition_contract.py` enforces these invariants in CI and package builds.
The live transition probe must additionally verify repeated editing of an existing sketch because
static checks cannot model FreeCAD's exact Qt signal order.
