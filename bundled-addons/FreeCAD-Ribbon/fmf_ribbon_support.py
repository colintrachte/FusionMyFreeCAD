"""FMF helpers for the vendored FreeCAD-Ribbon modules.

Not part of upstream FreeCAD-Ribbon. Keeping the bodies here means
`tools/sync_bundled_addons.py` has only one-line hooks to re-apply in upstream's
own files after a refresh, and it never has to carry a block of logic as a
string literal.
"""

import FreeCAD as App
from PySide.QtCore import Qt

_dragFailureReported = False


def start_drag(drag, action=None):
    """Run a drag under whichever spelling this Qt binding provides.

    Qt6 dropped ``QDrag.exec_()``; Qt5 never had ``QDrag.exec()``. Upstream
    already guards both where it drags a whole panel, in
    ``FCBinding.setPanelProperties``, but not in the five places where it drags
    an icon, a separator, or a quick-access button. On the wrong binding each of
    those raised ``AttributeError`` inside a handler that printed to a stream
    FreeCAD does not display, so dragging an icon silently did nothing.
    """
    if action is None:
        action = Qt.DropAction.MoveAction
    runner = getattr(drag, "exec", None)
    if not callable(runner):
        runner = getattr(drag, "exec_", None)
    if not callable(runner):
        raise AttributeError("QDrag exposes neither exec() nor exec_()")
    return runner(action)


def report_drag_failure(error):
    """Say once why a drag did nothing, rather than printing into the void."""
    global _dragFailureReported
    if _dragFailureReported:
        App.Console.PrintLog("FMF: a ribbon drag failed: {}\n".format(error))
        return
    _dragFailureReported = True
    App.Console.PrintWarning(
        "FMF could not start a ribbon drag: {}. "
        "Rearranging ribbon icons will not work until this is resolved; "
        "further occurrences go to the log only.\n".format(error)
    )
