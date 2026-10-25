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


class CanonicalActionRegistry:
    """Resolve native command actions once and own scan/subscription lifetimes."""

    def __init__(self, gui: Any, action_type: type[Any]):
        self._gui = gui
        self._action_type = action_type
        self._actions: dict[str, Any] = {}
        self._inventory: tuple[Any, ...] | None = None
        self._trigger_connections: dict[tuple[str, str], tuple[Any, Any, Callable[..., None]]] = {}
        self._generation = 0
        self._missing_at_generation: dict[str, int] = {}
        self._direct_lookups = 0
        self._inventory_scans = 0

    def resolve(self, command_id: str, *, allow_scan: bool = False) -> Any | None:
        cached = self._actions.get(command_id)
        if cached is not None and self._is_live(cached):
            return cached
        self._actions.pop(command_id, None)
        if self._missing_at_generation.get(command_id) == self._generation:
            return None

        self._direct_lookups += 1
        action = self._resolve_direct(command_id)
        if action is not None:
            return self._remember(command_id, action)
        if allow_scan:
            for candidate in self.inventory():
                try:
                    if candidate.objectName() == command_id:
                        return self._remember(command_id, candidate)
                except RuntimeError:
                    continue
        self._missing_at_generation[command_id] = self._generation
        return None

    def inventory(self, *, force: bool = False) -> tuple[Any, ...]:
        """Return the diagnostic/shortcut inventory, scanning only when explicitly needed."""
        if force or self._inventory is None:
            if force:
                self._missing_at_generation.clear()
            main_window = self._gui.getMainWindow()
            self._inventory = (
                tuple(main_window.findChildren(self._action_type))
                if main_window is not None
                else ()
            )
            self._inventory_scans += 1
            for action in self._inventory:
                try:
                    command_id = action.objectName()
                except RuntimeError:
                    continue
                if command_id:
                    self._remember(command_id, action)
        return self._inventory

    def connect_triggered(self, command_id: str, owner: str, callback: Callable[..., None]) -> bool:
        """Connect one owner once, using the canonical action for the command."""
        key = (owner, command_id)
        if key in self._trigger_connections:
            return False
        action = self.resolve(command_id, allow_scan=True)
        signal = getattr(action, "triggered", None) if action is not None else None
        if signal is None or not hasattr(signal, "connect"):
            return False
        signal.connect(callback)
        self._trigger_connections[key] = (action, signal, callback)
        return True

    def disconnect_owner(self, owner: str) -> None:
        for key, (_action, signal, callback) in tuple(self._trigger_connections.items()):
            if key[0] != owner:
                continue
            try:
                signal.disconnect(callback)
            except (RuntimeError, TypeError, ValueError):
                pass
            del self._trigger_connections[key]

    def available(self, command_ids) -> set[str]:
        return {command_id for command_id in command_ids if self.resolve(command_id) is not None}

    def invalidate_inventory(self) -> None:
        """Drop only the optional global scan; direct command entries remain authoritative."""
        self._inventory = None

    def advance_generation(self, _workbench_name="") -> None:
        """Permit unresolved direct commands to be retried after a host lifecycle change."""
        self._generation += 1
        self._missing_at_generation.clear()

    def dispose(self) -> None:
        for owner in {key[0] for key in self._trigger_connections}:
            self.disconnect_owner(owner)
        self._actions.clear()
        self._missing_at_generation.clear()
        self._inventory = None

    def snapshot(self) -> dict[str, int]:
        return {
            "cachedActions": len(self._actions),
            "triggerConnections": len(self._trigger_connections),
            "directLookups": self._direct_lookups,
            "inventoryScans": self._inventory_scans,
            "generation": self._generation,
            "missingActions": len(self._missing_at_generation),
        }

    def _resolve_direct(self, command_id: str) -> Any | None:
        command_api = getattr(self._gui, "Command", None)
        get_command = getattr(command_api, "get", None)
        if get_command is None:
            return None
        try:
            command = get_command(command_id)
            actions = command.getAction() if command is not None else ()
            if isinstance(actions, self._action_type):
                return actions
            return next(
                (action for action in actions or () if isinstance(action, self._action_type)), None
            )
        except (AttributeError, RuntimeError, TypeError):
            return None

    def _remember(self, command_id: str, action: Any) -> Any:
        previous = self._actions.get(command_id)
        if previous is action:
            return action
        self._actions[command_id] = action
        self._missing_at_generation.pop(command_id, None)
        return action

    @staticmethod
    def _is_live(action: Any) -> bool:
        try:
            action.objectName()
            return True
        except RuntimeError:
            return False


class NativeActionAdapter:
    """Resolve command actions and mirror their native state without caching QActions."""

    def __init__(
        self,
        gui: Any,
        action_type: type[Any],
        registry: CanonicalActionRegistry | None = None,
    ):
        self._registry = registry or CanonicalActionRegistry(gui, action_type)

    def resolve(self, command_id: str) -> Any | None:
        return self._registry.resolve(command_id, allow_scan=True)

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

        subscription = self._adapter.subscribe(command_id, apply_state)
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
