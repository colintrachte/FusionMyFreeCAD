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

    action: Any | None = None
    connections: list[tuple[Any, Callable[..., None]]] = field(default_factory=list)

    def dispose(self) -> None:
        for signal, callback in reversed(self.connections):
            try:
                signal.disconnect(callback)
            except (RuntimeError, TypeError, ValueError):
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
        try:
            checkable = bool(action.isCheckable())
            return {
                "enabled": self._is_enabled(action),
                "checkable": checkable,
                "checked": bool(action.isChecked()) if checkable else False,
            }
        except RuntimeError:
            return None

    def subscribe(
        self,
        command_id: str,
        callback: Callable[[dict[str, bool]], None],
        on_destroyed: Callable[[], None] | None = None,
    ):
        action = self.resolve(command_id)
        if action is None:
            return None
        subscription = ActionSubscription(action=action)

        def publish(*_arguments):
            state = self.snapshot(command_id)
            if state is not None:
                callback(state)

        for signal_name in ("changed", "toggled"):
            signal = getattr(action, signal_name, None)
            if signal is not None and hasattr(signal, "connect"):
                signal.connect(publish)
                subscription.connections.append((signal, publish))
        destroyed = getattr(action, "destroyed", None)
        if destroyed is not None and hasattr(destroyed, "connect"):

            def action_destroyed(*_arguments):
                subscription.dispose()
                if on_destroyed is not None:
                    on_destroyed()

            destroyed.connect(action_destroyed)
            subscription.connections.append((destroyed, action_destroyed))
        publish()
        return subscription

    @staticmethod
    def _is_enabled(action: Any) -> bool:
        try:
            return bool(action.isEnabled())
        except RuntimeError:
            return False


@dataclass
class RibbonActionBinding:
    """One ribbon widget's disposable connection to a native command action."""

    command_id: str
    button: Any
    action_subscription: ActionSubscription
    destroyed_connection: tuple[Any, Callable[..., None]] | None = None

    def dispose(self) -> None:
        self.action_subscription.dispose()
        if self.destroyed_connection is not None:
            signal, callback = self.destroyed_connection
            try:
                signal.disconnect(callback)
            except (RuntimeError, TypeError, ValueError):
                pass
            self.destroyed_connection = None


class RibbonActionBindingRegistry:
    """Own ribbon action subscriptions for deterministic rebuild and teardown."""

    def __init__(self, adapter: NativeActionAdapter):
        self._adapter = adapter
        self._bindings: dict[int, RibbonActionBinding] = {}

    def bind(self, command_id: str, button: Any) -> bool:
        """Bind one widget without taking ownership of command invocation."""
        self.unbind(button)
        key = id(button)

        def apply_state(state: dict[str, bool]) -> None:
            try:
                button.setEnabled(state["enabled"])
                button.setCheckable(state["checkable"])
                if state["checkable"]:
                    button.setChecked(state["checked"])
            except RuntimeError:
                self._dispose_key(id(button))

        def remove_action() -> None:
            self._dispose_key(key)

        subscription = self._adapter.subscribe(command_id, apply_state, remove_action)
        if subscription is None:
            return False

        binding = RibbonActionBinding(command_id, button, subscription)
        destroyed = getattr(button, "destroyed", None)
        if destroyed is not None and hasattr(destroyed, "connect"):

            def remove(*_arguments: Any) -> None:
                self._dispose_key(key, disconnect_widget=False)

            destroyed.connect(remove)
            binding.destroyed_connection = (destroyed, remove)
        self._bindings[key] = binding
        return True

    def unbind(self, button: Any) -> None:
        self._dispose_key(id(button))

    def dispose(self) -> None:
        for key in list(self._bindings):
            self._dispose_key(key)

    def count(self) -> int:
        return len(self._bindings)

    def _dispose_key(self, key: int, *, disconnect_widget: bool = True) -> None:
        binding = self._bindings.pop(key, None)
        if binding is None:
            return
        if not disconnect_widget:
            binding.destroyed_connection = None
        binding.dispose()
