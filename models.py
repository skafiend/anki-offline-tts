from aqt import QAbstractTableModel, QModelIndex, mw
from aqt.qt import Qt
from .utils import sanitize_text, missing_fields

from .config import cfg


class ModelAudioTbl(QAbstractTableModel):
    HEADERS = ["Note ID", "Text Before", "Processed Text", "Status"]

    def __init__(self, note_ids: list[int], parent=None) -> None:
        super().__init__(parent)
        self.note_ids = note_ids
        self.regex_rules = cfg.regex_rules

        self._grid_preview = []
        self.refresh_data(note_ids)

        print(f"\n self._grid_preview: {self._grid_preview}")

    # We use this method at least twice:
    # - when we populate the table for a first time
    # - when presets are changed and we want to update the preview, we call it directly from the dialog
    def refresh_data(self, ids: list[int]):
        self.beginResetModel()
        self._grid_preview.clear()

        for nid in ids:
            note = mw.col.get_note(nid)
            missing_src = missing_fields(note, [cfg.fallback_src])
            missing_dst = missing_fields(note, [cfg.fallback_dst])
            cln_before, cln_after = "", ""

            if missing_src:
                cln_before = f"Missing source: {missing_src}"
                cln_after = "Nothing to sanitize!"
            else:
                cln_before = src = note[cfg.fallback_src]
                cln_after = sanitize_text(src, self.regex_rules)

            if missing_dst:
                cln_after = f"Missing destination: {missing_dst}"

            if missing_src or missing_dst:
                status = "Error"
            else:
                status = "OK"
            self._grid_preview.append([str(nid), cln_before, cln_after, status])

        self.endResetModel()

    def rowCount(self, parent=None) -> int:
        return len(self.note_ids)

    def columnCount(self, parent=None) -> int:
        return len(self.HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole) -> None:
        if role == Qt.ItemDataRole.DisplayRole and self.checkIndex(index):
            row = index.row()
            col = index.column()
            return self._grid_preview[row][col]
        return None

    def flags(self, index):
        return super().flags(index)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role=Qt.ItemDataRole.DisplayRole,
    ) -> None:
        if (
            role == Qt.ItemDataRole.DisplayRole
            and orientation == Qt.Orientation.Horizontal
        ):
            # section can be 0, 1, 2... etc.
            return self.HEADERS[section]
        # This falls back to the built-in Qt numbering behavior
        return super().headerData(section, orientation, role)


class ModelRegexTbl(QAbstractTableModel):
    HEADERS = ["Pattern", "Replace", "Comment"]

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.regex_rules: list[dict[str, str]] = []
        self.regex_rules = cfg.regex_rules

    def rowCount(self, parent=None) -> int:
        return len(self.regex_rules)

    def columnCount(self, parent=None) -> int:
        return len(self.HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole) -> None:
        if (
            role == Qt.ItemDataRole.DisplayRole or role == Qt.ItemDataRole.EditRole
        ) and self.checkIndex(index):
            row = index.row()
            column = self.HEADERS[index.column()]
            return self.regex_rules[row][column]
        # This is fallback value for all the roles that weren't specified
        return None

    def setData(self, index, value, role):
        if role == Qt.ItemDataRole.EditRole and self.checkIndex(index):
            row = index.row()
            column = self.HEADERS[index.column()]
            self.regex_rules[row][column] = value
            print("\nThe regex_rules has been changed: ", self.regex_rules)
            # Transfer changes from our instance of ConfigManager() into the meta.json
            cfg.save()
            # Inform views that the changes took place; index, index means that only one cell was changed
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole])
            return True

        print("Nothing to change")
        return False

    def flags(self, index):
        return Qt.ItemFlag.ItemIsEditable | super().flags(index)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role=Qt.ItemDataRole.DisplayRole,
    ) -> None:
        if (
            role == Qt.ItemDataRole.DisplayRole
            and orientation == Qt.Orientation.Horizontal
        ):
            return self.HEADERS[section]

        # This falls back to the built-in Qt numbering behavior
        return super().headerData(section, orientation, role)

    def insertRows(self, row: int, count: int, parent: QModelIndex) -> bool:
        try:
            new_items = [dict.fromkeys(self.HEADERS, "") for _ in range(count)]
            # Inform the View we are starting
            # if first = 1, count = 3, last = first + count - 1 = 3
            self.beginInsertRows(parent, row, row + count - 1)

            for i, item in enumerate(new_items):
                self.regex_rules.insert(row + i, item)

            # write changes in meta.json
            cfg.save()
            return True

        except Exception as e:
            print(f"Failed to insert rows: {e}")
            return False

        finally:
            # Inform the View we are finished
            self.endInsertRows()

    def removeRows(self, row: int, count: int, parent: QModelIndex) -> bool:
        try:
            first = row
            last = row + count - 1
            self.beginRemoveRows(parent, first, last)

            print(f"\ncount: {count}, row: {row}")

            # slice must be [start : start + count]
            del self.regex_rules[row : count + row]

            # update our singleton
            cfg.regex_rules = self.regex_rules

            # write changes in meta.json
            cfg.save()

            return True

        except Exception as e:
            print(f"Failed to remove rows: {e}")
            return False

        # It will be called even if we get to the return statements
        finally:
            self.endRemoveRows()

    def reset_to_defaults(self):

        self.beginResetModel()
        # __name__ == anki_offline_tts.models
        # however, anki needs the root folder of an addon to get the proper config
        addon_package = __name__.split(".")[0]

        default = mw.addonManager.addonConfigDefaults(addon_package)

        if default is None:
            print("\nWARNING: config.json not found or malformed!")
        else:
            # we update the object in memory tied to the regex_table_view to make it see changes
            # CLEAR and EXTEND to keep the object reference the same
            # self.regex_rules = default["regex_rules"] makes a new reference and audio_preview_table becomes disconnected
            # => doesn't show the changes after resetting
            self.regex_rules.clear()
            self.regex_rules.extend(default["regex_rules"])

            # we update our singleton and write the changes
            # our singleton has a setter that calls cfg.save()
            cfg.regex_rules = self.regex_rules

        self.endResetModel()
