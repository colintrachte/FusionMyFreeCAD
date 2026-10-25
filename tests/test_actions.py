"""Native QAction adapter contracts."""

from fmf_actions import (
    CanonicalActionRegistry,
    NativeActionAdapter,
    RibbonActionBindingRegistry,
)


class Signal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def disconnect(self, callback):
        self.callbacks.remove(callback)

    def emit(self, *args):
        for callback in list(self.callbacks):
            callback(*args)


class Action:
    def __init__(self, name, enabled=True, checkable=False, checked=False):
        self.name = name
        self.enabled = enabled
        self.checkable = checkable
        self.checked = checked
        self.trigger_count = 0
        self.changed = Signal()
        self.toggled = Signal()
        self.triggered = Signal()
        self.destroyed = Signal()

    def objectName(self):
        return self.name

    def isEnabled(self):
        return self.enabled

    def isCheckable(self):
        return self.checkable

    def isChecked(self):
        return self.checked

    def trigger(self):
        self.trigger_count += 1


class Button:
    def __init__(self):
        self.enabled = None
        self.checkable = None
        self.checked = None
        self.destroyed = Signal()

    def setEnabled(self, enabled):
        self.enabled = enabled

    def setCheckable(self, checkable):
        self.checkable = checkable

    def setChecked(self, checked):
        self.checked = checked


class Window:
    def __init__(self, actions):
        self.actions = actions

    def findChildren(self, _action_type):
        return self.actions


class Gui:
    def __init__(self, actions):
        self.window = Window(actions)

    def getMainWindow(self):
        return self.window


class Command:
    def __init__(self, actions):
        self.actions = actions

    def getAction(self):
        return self.actions


class CommandApi:
    def __init__(self, commands):
        self.commands = commands

    def get(self, name):
        return self.commands.get(name)


class GuiWithCommands(Gui):
    def __init__(self, window_actions, commands):
        super().__init__(window_actions)
        self.Command = CommandApi(commands)


def test_registry_direct_lookup_avoids_global_scan():
    action = Action("PartDesign_Pad")
    gui = GuiWithCommands([Action("Unrelated")], {action.name: Command([action])})
    registry = CanonicalActionRegistry(gui, Action)

    assert registry.resolve(action.name) is action
    assert registry.resolve(action.name) is action
    assert registry.snapshot() == {
        "cachedActions": 1,
        "triggerConnections": 0,
        "directLookups": 1,
        "inventoryScans": 0,
        "generation": 0,
        "missingActions": 0,
    }


def test_registry_scans_once_for_non_command_actions():
    unnamed = Action("")
    gui = Gui([unnamed])
    registry = CanonicalActionRegistry(gui, Action)

    assert registry.inventory() == (unnamed,)
    assert registry.inventory() == (unnamed,)
    assert registry.snapshot()["inventoryScans"] == 1


def test_registry_retries_a_missing_command_only_after_generation_change():
    action = Action("Late_Command")
    gui = GuiWithCommands([], {})
    registry = CanonicalActionRegistry(gui, Action)

    assert registry.resolve(action.name) is None
    assert registry.resolve(action.name) is None
    assert registry.snapshot()["directLookups"] == 1

    gui.Command.commands[action.name] = Command([action])
    assert registry.resolve(action.name) is None
    registry.advance_generation("FMFPartWorkbench")
    assert registry.resolve(action.name) is action
    assert registry.snapshot()["directLookups"] == 2


def test_registry_owns_trigger_connection_and_explicit_cleanup():
    action = Action("PartDesign_Pad")
    registry = CanonicalActionRegistry(Gui([action]), Action)
    calls = []

    assert registry.connect_triggered(action.name, "runtime", calls.append) is True
    assert registry.connect_triggered(action.name, "runtime", calls.append) is False
    action.triggered.emit(True)
    assert calls == [True]

    registry.dispose()
    state = registry.snapshot()
    assert state["cachedActions"] == 0
    assert state["triggerConnections"] == 0
    assert action.triggered.callbacks == []


def test_resolve_invoke_and_missing_action():
    action = Action("Sketcher_ToggleConstruction")
    adapter = NativeActionAdapter(Gui([action]), Action)
    assert adapter.resolve(action.name) is action
    assert adapter.invoke(action.name) is True
    assert action.trigger_count == 1
    assert adapter.invoke("Missing") is False


def test_disabled_action_is_not_invoked():
    action = Action("Disabled", enabled=False)
    assert NativeActionAdapter(Gui([action]), Action).invoke("Disabled") is False
    assert action.trigger_count == 0


def test_resolve_prefers_authoritative_command_action_over_duplicate():
    duplicate = Action("Toggle", enabled=False)
    authoritative = Action("Toggle", enabled=True)
    gui = GuiWithCommands([duplicate], {"Toggle": Command([authoritative])})
    adapter = NativeActionAdapter(gui, Action)
    assert adapter.resolve("Toggle") is authoritative
    assert adapter.invoke("Toggle") is True
    assert authoritative.trigger_count == 1
    assert duplicate.trigger_count == 0


def test_subscription_publishes_native_state_and_disposes():
    action = Action("Toggle", checkable=True)
    adapter = NativeActionAdapter(Gui([action]), Action)
    states = []
    subscription = adapter.subscribe("Toggle", states.append)
    assert states[-1] == {"enabled": True, "checkable": True, "checked": False}
    action.checked = True
    action.toggled.emit(True)
    assert states[-1]["checked"] is True
    subscription.dispose()
    action.checked = False
    action.changed.emit()
    assert states[-1]["checked"] is True


def test_subscription_does_not_run_python_during_action_destruction():
    action = Action("Toggle", checkable=True)
    adapter = NativeActionAdapter(Gui([action]), Action)
    subscription = adapter.subscribe("Toggle", lambda _state: None)

    assert action.destroyed.callbacks == []
    subscription.dispose()
    assert action.changed.callbacks == []
    assert action.toggled.callbacks == []
    assert action.destroyed.callbacks == []


def test_ribbon_binding_mirrors_state_without_owning_invocation():
    action = Action("Toggle", checkable=True)
    registry = RibbonActionBindingRegistry(NativeActionAdapter(Gui([action]), Action))
    button = Button()

    assert registry.bind("Toggle", button) is True
    assert (button.enabled, button.checkable, button.checked) == (True, True, False)

    action.enabled = False
    action.checked = True
    action.changed.emit()

    assert (button.enabled, button.checkable, button.checked) == (False, True, True)
    assert action.trigger_count == 0


def test_rebinding_a_widget_does_not_duplicate_callbacks():
    action = Action("Toggle", checkable=True)
    registry = RibbonActionBindingRegistry(NativeActionAdapter(Gui([action]), Action))
    button = Button()

    for _iteration in range(50):
        assert registry.bind("Toggle", button) is True

    assert registry.count() == 1
    assert len(action.changed.callbacks) == 1
    assert len(action.toggled.callbacks) == 1
    # Native QAction destruction must not call back into Python. Qt removes
    # sender-owned connections; ribbon rebuild teardown owns our subscription.
    assert action.destroyed.callbacks == []


def test_destroyed_widget_and_registry_teardown_dispose_subscriptions():
    first = Action("First", checkable=True)
    second = Action("Second", checkable=True)
    registry = RibbonActionBindingRegistry(NativeActionAdapter(Gui([first, second]), Action))
    first_button = Button()
    second_button = Button()
    registry.bind("First", first_button)
    registry.bind("Second", second_button)

    first_button.destroyed.emit()
    assert registry.count() == 1
    assert first.changed.callbacks == []

    registry.dispose()
    assert registry.count() == 0
    assert second.changed.callbacks == []
    assert second_button.destroyed.callbacks == []
