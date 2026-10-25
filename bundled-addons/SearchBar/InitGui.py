import FreeCAD as App
import FreeCADGui as Gui
from PySide.QtWidgets import QMainWindow, QToolBar, QMenu, QWidget, QWidgetAction, QDialog, QHBoxLayout
from PySide.QtGui import QShortcut, QKeySequence, QCursor
from PySide.QtCore import Qt, Signal, QEvent, QObject
import os
import Parameters_SearchBar

# FusionMyFreeCAD ships its own release information.  Suppress SearchBar's
# always-on-top startup changelog at the source so add-on load order cannot
# re-enable it before FusionMyFreeCAD preferences are applied.
Parameters_SearchBar.Settings.SetStringSetting("DoNotShowAgain", "1.8")
Parameters_SearchBar.Settings.SetBoolSetting("ShowChangeDialog", False)
Parameters_SearchBar.DO_NOT_SHOW_AGAIN = "1.8"

# Avoid garbage collection by storing the action in a global variable
wax = None
sea = None
tbr = None
_event_filter = None
_event_filter_targets = []
_workbench_signal_connected = False

ChangeDialogLoaded = False

# Define the translation
translate = App.Qt.translate

PrefLoaded = False
Gui.addIconPath(Parameters_SearchBar.ICON_LOCATION)
Gui.addResourcePath(Parameters_SearchBar.ICON_LOCATION)
PreferenceUI = os.path.join(Parameters_SearchBar.UI_LOCATION, "PreferencesUI_SearchBar.ui")
Gui.addPreferencePage(PreferenceUI, "SearchBar")


def QT_TRANSLATE_NOOP(context, text):
    return text

class SearchBar(Gui.Workbench):
    # This is needed to avoid crashes
    def GetClassName(self):
        # This function is mandatory if this is a full Python workbench
        # This is not a template, the returned string should be exactly "Gui::PythonWorkbench"
        return "Gui::PythonWorkbench"

    def addToolSearchBox():
        global wax, sea, tbr, ChangeDialogLoaded, _event_filter
        mw: QMainWindow = Gui.getMainWindow()
        cp = mw.centralWidget()
        vp: QWidget = cp.viewport()
        import SearchBox
        import MouseBar
        from MouseBar import EventInspector_SB
        from PySide.QtWidgets import QToolBar
        import Parameters_SearchBar
        
        if mw:
            # The bundled startup changelog is intentionally non-interactive.
            ChangeDialogLoaded = True
            
            # If the mousebar is enabled in preferences, enable it.
            if Parameters_SearchBar.Settings.GetBoolSetting("EnableMouseBar", True) is True:
                # Activate the searchBar at the pointer module
                MouseBar.SearchBar_Pointer()
                
                if _event_filter is None:
                    _event_filter = EventInspector_SB(mw)
                for target in (mw, mw.centralWidget(), vp, *vp.children()):
                    if target not in _event_filter_targets:
                        target.installEventFilter(_event_filter)
                        _event_filter_targets.append(target)
            
            # if the toolbars are enabled in preferences, load them
            if Parameters_SearchBar.Settings.GetBoolSetting("EnableToolbars", True) is True:          
                if sea is None:
                    wax = SearchBox.SearchBoxFunction(mw)
                if tbr is None:
                    tbr = QToolBar("SearchBar")  # QtGui.QDockWidget()
                    # Include FreeCAD in the name so that one can find windows labeled with
                    # FreeCAD easily in window managers which allow search through the list of open windows.
                    tbr.setObjectName("SearchBar")
                    tbr.addAction(wax)
                mw.addToolBar(tbr)
                tbr.show()
            return   

def install():
    """Install one shared event filter and one workbench callback."""
    global _workbench_signal_connected
    SearchBar.addToolSearchBox()
    if not _workbench_signal_connected:
        Gui.getMainWindow().workbenchActivated.connect(SearchBar.addToolSearchBox)
        _workbench_signal_connected = True


def uninstall():
    """Release SearchBar's long-lived callbacks and event filters."""
    global _event_filter, _workbench_signal_connected
    main_window = Gui.getMainWindow()
    if _workbench_signal_connected:
        try:
            main_window.workbenchActivated.disconnect(SearchBar.addToolSearchBox)
        except Exception:
            pass
        _workbench_signal_connected = False
    if _event_filter is not None:
        for target in tuple(_event_filter_targets):
            try:
                target.removeEventFilter(_event_filter)
            except RuntimeError:
                pass
        _event_filter_targets.clear()
        _event_filter.deleteLater()
        _event_filter = None


install()


