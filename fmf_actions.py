"""Qt-lifetime-safe access to native FreeCAD command actions.

The adapter deliberately owns no layout, ranking, or command metadata policy. FreeCAD's QAction
remains authoritative for availability and checked state.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ActionSubscription:
    """Connections made for one action, detachable as a unit."""

    connections: list[tuple[Any, Callable[..., None]]] = field(default_factory=list)

    def dispose(self) -> None:
        for signal, callback in reversed(self.connections):
            try:
                signal.disconnect(callback)
            except (RuntimeError, TypeError):
                pass
        self.connections.clear()


class NativeActionAdapter:
    """Resolve command actions and mirror their native state without caching QActions."""

    def __init__(self, gui: Any, action_type: type[Any]):
        self._gui = gui
        self._action_type = action_type

    def resolve(self, command_id: str) -> Any | None:
        command_api = getattr(self._gui, "Command", None)
        get_command = getattr(command_api, "get", None)
        if get_command is not None:
            try:
                command = get_command(command_id)
                actions = command.getAction() if command is not None else ()
                if isinstance(actions, self._action_type):
                    return actions
                for action in actions or ():
                    if isinstance(action, self._action_type):
                        return action
            except (AttributeError, RuntimeError, TypeError):
                pass
        main_window = self._gui.getMainWindow()
        if main_window is None:
            return None
        for action in main_window.findChildren(self._action_type):
            try:
                if action.objectName() == command_id:
                    return action
            except RuntimeError:
                continue
        return None

    def invoke(self, command_id: str) -> bool:
        action = self.resolve(command_id)
        if action is None or not self._is_enabled(action):
            return False
        action.trigger()
        return True

    def snapshot(self, command_id: str) -> dict[str, bool] | None:
        action = self.resolve(command_id)
        if action is None:
            return None
        return {
            "enabled": self._is_enabled(action),
            "checkable": bool(action.isCheckable()),
            "checked": bool(action.isChecked()) if action.isCheckable() else False,
        }

    def subscribe(self, command_id: str, callback: Callable[[dict[str, bool]], None]):
        action = self.resolve(command_id)
        if action is None:
            return None
        subscription = ActionSubscription()

        def publish(*_arguments):
            state = self.snapshot(command_id)
            if state is not None:
                callback(state)

        for signal_name in ("changed", "toggled", "destroyed"):
            signal = getattr(action, signal_name, None)
            if signal is not None and hasattr(signal, "connect"):
                signal.connect(publish)
                subscription.connections.append((signal, publish))
        publish()
        return subscription

    @staticmethod
    def _is_enabled(action: Any) -> bool:
        try:
            return bool(action.isEnabled())
        except RuntimeError:
            return False
