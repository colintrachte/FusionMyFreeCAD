"""Native QAction adapter contracts."""

from fusion_actions import NativeActionAdapter


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
