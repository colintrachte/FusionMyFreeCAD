"""Fast in-canvas Parameters dock widget for FMF.

Allows creating, editing, and inspecting model parameters directly from the 3D
canvas sidebar without interrupting CAD workflows by switching to the
Spreadsheet workbench.
"""

from __future__ import annotations

import FreeCAD as App
import FreeCADGui as Gui

from fmf_common import log_swallowed, transaction

try:
    from PySide import QtCore, QtWidgets
except ImportError:
    try:
        from PySide import QtCore, QtGui

        QtWidgets = QtGui
    except ImportError:
        QtWidgets = None
        QtCore = None

_active_parameters_dock = None


def _get_document_by_name(name: str | None):
    if not name:
        return None
    if hasattr(App, "getDocument"):
        try:
            return App.getDocument(name)
        except Exception:
            pass
    if hasattr(App, "listDocuments"):
        try:
            return App.listDocuments().get(name)
        except Exception:
            pass
    active = getattr(App, "ActiveDocument", None)
    if active and getattr(active, "Name", "") == name:
        return active
    return None


def get_or_create_parameters_sheet(document=None):
    """Find or create the dedicated 'Parameters' spreadsheet."""
    doc = document or getattr(App, "ActiveDocument", None)
    if doc is None:
        return None

    sheet = next(
        (
            obj
            for obj in getattr(doc, "Objects", [])
            if getattr(obj, "isDerivedFrom", lambda t: False)("Spreadsheet::Sheet")
            and getattr(obj, "Label", "") == "Parameters"
        ),
        None,
    )
    if sheet is None:
        sheet = doc.addObject("Spreadsheet::Sheet", "Parameters")
        sheet.Label = "Parameters"
        sheet.set("A1", "Parameter")
        sheet.set("B1", "Value / Expression")
        sheet.set("C1", "Notes")
        if hasattr(sheet, "setStyle"):
            sheet.setStyle("A1:C1", "bold", "add")
        if hasattr(sheet, "setColumnWidth"):
            sheet.setColumnWidth("A", 160)
            sheet.setColumnWidth("B", 160)
            sheet.setColumnWidth("C", 200)
        doc.recompute()
    return sheet


if QtWidgets is not None:

    class _ParametersDocumentObserver:
        """Observer that keeps FastParametersDock synchronized with document changes."""

        def __init__(self, dock):
            self.dock = dock

        def slotActiveDocument(self, doc):
            if self.dock is not None:
                self.dock.on_document_activated(doc)

        slotActivatedDocument = slotActiveDocument

        def slotDeletedDocument(self, doc):
            if self.dock is not None:
                self.dock.on_document_deleted(doc)

        slotDeleteDocument = slotDeletedDocument
        slotFinishInvDoc = slotDeletedDocument

        def slotRecomputedObject(self, obj):
            if self.dock is not None and not getattr(self.dock, "_updating", False):
                self.dock.on_object_recomputed(obj)

    class FastParametersDock(QtWidgets.QDockWidget):
        """Lightweight dock widget for in-canvas parametric modeling."""

        def __init__(self, parent=None):
            super().__init__("Parameters", parent)
            self.setObjectName("FMF_ParametersDock")
            self._updating = False
            self._refresh_pending = False
            self._last_rows = None
            active_doc = getattr(App, "ActiveDocument", None)
            self._bound_doc_name: str | None = (
                getattr(active_doc, "Name", None) if active_doc else None
            )
            self._observer = _ParametersDocumentObserver(self)
            if hasattr(App, "addDocumentObserver"):
                try:
                    App.addDocumentObserver(self._observer)
                except Exception:
                    pass

            self._init_ui()

        def closeEvent(self, event):
            if hasattr(App, "removeDocumentObserver") and getattr(self, "_observer", None):
                try:
                    App.removeDocumentObserver(self._observer)
                except Exception:
                    pass
            super().closeEvent(event)

        def _init_ui(self):
            widget = QtWidgets.QWidget(self)
            layout = QtWidgets.QVBoxLayout(widget)
            layout.setContentsMargins(4, 4, 4, 4)
            layout.setSpacing(4)

            # Button bar
            btn_bar = QtWidgets.QHBoxLayout()
            self.btn_add = QtWidgets.QPushButton("+ Add", widget)
            self.btn_add.setToolTip("Add a new parameter")
            self.btn_add.clicked.connect(self.on_add_parameter)
            btn_bar.addWidget(self.btn_add)

            self.btn_del = QtWidgets.QPushButton("- Delete", widget)
            self.btn_del.setToolTip("Delete selected parameter")
            self.btn_del.clicked.connect(self.on_delete_parameter)
            btn_bar.addWidget(self.btn_del)

            if hasattr(btn_bar, "addStretch"):
                btn_bar.addStretch()

            self.btn_refresh = QtWidgets.QPushButton("Refresh", widget)
            self.btn_refresh.setToolTip("Reload parameters from document")
            self.btn_refresh.clicked.connect(self.refresh_parameters)
            btn_bar.addWidget(self.btn_refresh)

            layout.addLayout(btn_bar)

            # Table
            self.table = QtWidgets.QTableWidget(widget)
            self.table.setColumnCount(4)
            self.table.setHorizontalHeaderLabels(["Name", "Expression", "Value", "Notes"])
            header = self.table.horizontalHeader()
            if hasattr(header, "setSectionResizeMode"):
                header.setSectionResizeMode(QtWidgets.QHeaderView.Stretch)

            self.table.cellChanged.connect(self.on_cell_changed)
            layout.addWidget(self.table)

            self.setWidget(widget)
            self._update_title()
            self.refresh_parameters()

        def _update_title(self):
            if self._bound_doc_name:
                self.setWindowTitle(f"Parameters ({self._bound_doc_name})")
            else:
                self.setWindowTitle("Parameters")

        def get_bound_document(self):
            """Return the document object currently bound to this dock."""
            if not self._bound_doc_name:
                return None
            doc = _get_document_by_name(self._bound_doc_name)
            if doc is None:
                self._bound_doc_name = None
                return None
            return doc

        def bind_to_document(self, doc):
            """Bind dock to a document and refresh rows."""
            new_name = getattr(doc, "Name", None) if doc else None
            if new_name != self._bound_doc_name:
                self._last_rows = None
            self._bound_doc_name = new_name
            self._update_title()
            self.refresh_parameters()

        def on_document_activated(self, doc):
            """Synchronize dock with user activating a document."""
            new_name = getattr(doc, "Name", None) if doc else None
            if new_name != self._bound_doc_name:
                self.bind_to_document(doc)

        def on_document_deleted(self, doc):
            """Handle document closure."""
            deleted_name = getattr(doc, "Name", None) if doc else None
            if deleted_name == self._bound_doc_name:
                active = getattr(App, "ActiveDocument", None)
                if active and getattr(active, "Name", None) != deleted_name:
                    self.bind_to_document(active)
                else:
                    self.bind_to_document(None)

        def on_object_recomputed(self, obj):
            """Auto-refresh dock if bound Parameters sheet was modified externally."""
            if getattr(obj, "Label", "") == "Parameters" and getattr(
                obj, "isDerivedFrom", lambda t: False
            )("Spreadsheet::Sheet"):
                bound_doc = self.get_bound_document()
                if bound_doc and obj in getattr(bound_doc, "Objects", []):
                    self.schedule_refresh()

        def schedule_refresh(self):
            """Coalesce spreadsheet recompute bursts into one visible-dock refresh."""
            if self._refresh_pending or not self.isVisible():
                return
            self._refresh_pending = True

            def refresh_once():
                self._refresh_pending = False
                if self.isVisible():
                    self.refresh_parameters()

            QtCore.QTimer.singleShot(0, refresh_once)

        def refresh_parameters(self):
            """Populate table from bound document's Parameters sheet with gap tolerance."""
            self._refresh_pending = False
            doc = self.get_bound_document()
            self._update_title()
            if doc is None:
                if self._last_rows != ():
                    self.table.setRowCount(0)
                    self._last_rows = ()
                return

            sheet = get_or_create_parameters_sheet(doc)
            if sheet is None:
                if self._last_rows != ():
                    self.table.setRowCount(0)
                    self._last_rows = ()
                return

            rows = []
            max_empty_streak = 5
            empty_streak = 0
            row_sheet = 2
            max_scan_row = 200
            while row_sheet <= max_scan_row and empty_streak < max_empty_streak:
                name_val = getattr(sheet, "get", lambda c: None)(f"A{row_sheet}")
                if name_val is not None and str(name_val).strip():
                    empty_streak = 0
                    rows.append(
                        (
                            row_sheet,
                            str(name_val),
                            str(getattr(sheet, "get", lambda c: None)(f"B{row_sheet}") or ""),
                            str(getattr(sheet, "get", lambda c: None)(f"C{row_sheet}") or ""),
                        )
                    )
                else:
                    empty_streak += 1
                row_sheet += 1
            rows = tuple(rows)
            if rows == self._last_rows:
                return

            self._updating = True
            try:
                self.table.setRowCount(0)
                for row_sheet, name_val, expr_val, notes_val in rows:
                    r = self.table.rowCount()
                    self.table.insertRow(r)

                    name_item = QtWidgets.QTableWidgetItem(name_val)
                    name_item.setData(QtCore.Qt.UserRole, row_sheet)
                    self.table.setItem(r, 0, name_item)

                    expr_item = QtWidgets.QTableWidgetItem(expr_val)
                    expr_item.setData(QtCore.Qt.UserRole, row_sheet)
                    self.table.setItem(r, 1, expr_item)

                    eval_item = QtWidgets.QTableWidgetItem(expr_val)
                    eval_item.setFlags(eval_item.flags() & ~QtCore.Qt.ItemIsEditable)
                    eval_item.setData(QtCore.Qt.UserRole, row_sheet)
                    self.table.setItem(r, 2, eval_item)

                    notes_item = QtWidgets.QTableWidgetItem(notes_val)
                    notes_item.setData(QtCore.Qt.UserRole, row_sheet)
                    self.table.setItem(r, 3, notes_item)
                self._last_rows = rows
            finally:
                self._updating = False

        def on_add_parameter(self):
            doc = self.get_bound_document()
            if doc is None:
                return
            sheet = get_or_create_parameters_sheet(doc)
            if sheet is None:
                return

            used_rows = [
                self.table.item(r, 0).data(QtCore.Qt.UserRole)
                for r in range(self.table.rowCount())
                if self.table.item(r, 0) and self.table.item(r, 0).data(QtCore.Qt.UserRole)
            ]
            row_sheet = (max(used_rows) + 1) if used_rows else 2

            existing_names = {
                self.table.item(r, 0).text().strip()
                for r in range(self.table.rowCount())
                if self.table.item(r, 0)
            }
            idx = self.table.rowCount() + 1
            param_name = f"Param{idx}"
            while param_name in existing_names:
                idx += 1
                param_name = f"Param{idx}"

            self._updating = True
            try:
                with transaction(doc, "Add Parameter"):
                    sheet.set(f"A{row_sheet}", param_name)
                    sheet.set(f"B{row_sheet}", "10.0")
                    sheet.set(f"C{row_sheet}", "")
                    if hasattr(sheet, "setAlias"):
                        try:
                            sheet.setAlias(f"B{row_sheet}", param_name)
                        except Exception as error:
                            log_swallowed("create parameter alias", error)
                    doc.recompute()

                r = self.table.rowCount()
                self.table.insertRow(r)

                name_item = QtWidgets.QTableWidgetItem(param_name)
                name_item.setData(QtCore.Qt.UserRole, row_sheet)
                self.table.setItem(r, 0, name_item)

                expr_item = QtWidgets.QTableWidgetItem("10.0")
                expr_item.setData(QtCore.Qt.UserRole, row_sheet)
                self.table.setItem(r, 1, expr_item)

                eval_item = QtWidgets.QTableWidgetItem("10.0")
                eval_item.setFlags(eval_item.flags() & ~QtCore.Qt.ItemIsEditable)
                eval_item.setData(QtCore.Qt.UserRole, row_sheet)
                self.table.setItem(r, 2, eval_item)

                notes_item = QtWidgets.QTableWidgetItem("")
                notes_item.setData(QtCore.Qt.UserRole, row_sheet)
                self.table.setItem(r, 3, notes_item)
            finally:
                self._updating = False

        def on_delete_parameter(self):
            selected = self.table.currentRow()
            if selected < 0 or selected >= self.table.rowCount():
                return
            doc = self.get_bound_document()
            if doc is None:
                return
            sheet = get_or_create_parameters_sheet(doc)
            if sheet is None:
                return

            item = self.table.item(selected, 0)
            row_sheet = item.data(QtCore.Qt.UserRole) if item else (selected + 2)

            with transaction(doc, "Delete Parameter"):
                sheet.set(f"A{row_sheet}", "")
                sheet.set(f"B{row_sheet}", "")
                sheet.set(f"C{row_sheet}", "")
                if hasattr(sheet, "setAlias"):
                    try:
                        sheet.setAlias(f"B{row_sheet}", "")
                    except Exception as error:
                        log_swallowed("remove parameter alias", error)
                doc.recompute()

            self.refresh_parameters()

        def on_cell_changed(self, row, col):
            if self._updating:
                return
            doc = self.get_bound_document()
            if doc is None:
                return
            sheet = get_or_create_parameters_sheet(doc)
            if sheet is None:
                return

            item = self.table.item(row, col)
            val = item.text() if item else ""
            name_item = self.table.item(row, 0)
            row_sheet = name_item.data(QtCore.Qt.UserRole) if name_item else (row + 2)

            col_letter = {0: "A", 1: "B", 3: "C"}.get(col)
            if col_letter:
                with transaction(doc, "Edit Parameter"):
                    sheet.set(f"{col_letter}{row_sheet}", val)
                    if col in (0, 1) and hasattr(sheet, "setAlias"):
                        current_name = name_item.text().strip() if name_item else ""
                        if current_name:
                            try:
                                sheet.setAlias(f"B{row_sheet}", current_name)
                            except Exception as error:
                                log_swallowed("update parameter alias", error)
                    doc.recompute()

                if col == 1:
                    self._updating = True
                    try:
                        eval_item = self.table.item(row, 2)
                        if eval_item:
                            eval_item.setText(val)
                        else:
                            eval_item = QtWidgets.QTableWidgetItem(val)
                            eval_item.setFlags(eval_item.flags() & ~QtCore.Qt.ItemIsEditable)
                            eval_item.setData(QtCore.Qt.UserRole, row_sheet)
                            self.table.setItem(row, 2, eval_item)
                    finally:
                        self._updating = False

else:
    FastParametersDock = None


def show_parameters_dock():
    """Show and raise the Parameters dock widget in FreeCAD."""
    global _active_parameters_dock
    if QtWidgets is None or FastParametersDock is None:
        return None

    main_window = Gui.getMainWindow() if hasattr(Gui, "getMainWindow") else None
    if main_window is None:
        return None

    if _active_parameters_dock is None:
        _active_parameters_dock = FastParametersDock(main_window)
        area = getattr(QtCore.Qt, "RightDockWidgetArea", None)
        if area is None:
            area = QtCore.Qt.DockWidgetArea.RightDockWidgetArea
        main_window.addDockWidget(area, _active_parameters_dock)

    active_doc = getattr(App, "ActiveDocument", None)
    _active_parameters_dock.bind_to_document(active_doc)
    _active_parameters_dock.show()
    _active_parameters_dock.raise_()
    return _active_parameters_dock


def toggle_parameters_dock():
    """Show or toggle the Parameters dock widget in FreeCAD."""
    global _active_parameters_dock
    if _active_parameters_dock is not None and _active_parameters_dock.isVisible():
        _active_parameters_dock.hide()
        return _active_parameters_dock
    return show_parameters_dock()


def close_parameters_dock():
    """Remove the FMF Parameters dock and detach its document observer."""
    global _active_parameters_dock
    dock = _active_parameters_dock
    if dock is None:
        return

    observer = getattr(dock, "_observer", None)
    if observer is not None and hasattr(App, "removeDocumentObserver"):
        try:
            App.removeDocumentObserver(observer)
        except Exception as error:
            log_swallowed("remove Parameters dock observer", error)
    dock._observer = None

    try:
        dock.hide()
        main_window = Gui.getMainWindow() if hasattr(Gui, "getMainWindow") else None
        if main_window is not None and hasattr(main_window, "removeDockWidget"):
            main_window.removeDockWidget(dock)
        if hasattr(dock, "deleteLater"):
            dock.deleteLater()
    except Exception as error:
        log_swallowed("close Parameters dock", error)
    finally:
        _active_parameters_dock = None


class ParameterDockCommand:
    """``FMF_ParameterDock`` ribbon command."""

    def GetResources(self):
        return {
            "Pixmap": "Spreadsheet",
            "MenuText": "Parameters Dock",
            "ToolTip": "Open the in-canvas Parameters dock widget to manage model variables.",
        }

    def IsActive(self):
        return True

    def Activated(self):
        toggle_parameters_dock()


def register(add_command=None):
    register_with = add_command or Gui.addCommand
    register_with("FMF_ParameterDock", ParameterDockCommand())
