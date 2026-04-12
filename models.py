from dataclasses import fields
from aqt import QAbstractTableModel, QModelIndex, mw
from aqt.qt import Qt
from .utils import (
    find_decks,
    is_preset_valid,
    sanitize_text,
    has_audio,
)

from .config import cfg


class GenericTable(QAbstractTableModel):
    def __init__(self, parent, headers, data: list | None = None) -> None:
        super().__init__(parent)
        self._data = data if data is not None else []
        self._headers = headers

    def rowCount(self, parent=None) -> int:
        return len(self._data)

    def columnCount(self, parent=None) -> int:
        return len(self._headers)

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
            return self._headers[section].capitalize()
        # This falls back to the built-in Qt numbering behavior
        return super().headerData(section, orientation, role)


class ModelAudioTable(GenericTable):
    def __init__(self, parent, note_ids: list[int], headers) -> None:
        super().__init__(parent, headers, data=[])
        self.note_ids = note_ids
        self.refresh_data(note_ids)

        print(f"\n self._grid_preview: {self._data}")

    def data(self, index, role=Qt.ItemDataRole.DisplayRole) -> None:
        if role == Qt.ItemDataRole.DisplayRole and self.checkIndex(index):
            row = index.row()
            col = index.column()
            return self._data[row][col]
        return None

    def rowCount(self, parent=None) -> int:
        return len(self._data)

    # We use this method at least twice:
    # - when we populate the table for a first time
    # - when presets are changed and we want to update the preview, we call it directly from the dialog
    def refresh_data(self, ids: list[int]):
        self.beginResetModel()
        self._data.clear()

        # first we sort our presets so that children are before their parents
        # English::Phrasal_Verbs::A2'
        # English::Phrasal_Verbs
        sorted_presets = sorted(
            [{"index": i, "preset": p} for i, p in enumerate(cfg.presets)],
            key=lambda x: x["preset"].get("deck", "").count("::"),
            reverse=True,
        )

        for nid in ids:
            note = mw.col.get_note(nid)
            note_fields = note.keys()
            note_decks = find_decks(note)

            matched_presets = []

            for p in sorted_presets:
                if is_preset_valid(note_fields, note_decks, p["preset"]):
                    matched_presets.append(p)

            if not matched_presets:
                self._data.append(
                    [
                        str(nid),
                        f"Fields: {note_fields}",
                        f"Decks: {note_decks}",
                        "No presets found!",
                        "-99",
                    ]
                )
                continue

            print("\nmatched_presets:", matched_presets)

            processed = []

            for item in matched_presets:
                index = item["index"]
                preset = item["preset"]
                src = preset["source"]
                dst = preset["destination"]
                card = {"src": note[src], "dst": note[dst]}
                # if source is empty, or we already applied a preset
                # to the note = do nothing
                # the same source and a different destination = new preset
                if card["src"] and card not in processed:
                    if not (has_audio(card["dst"]) and cfg.preserve_audio):
                        result = sanitize_text(card["src"], cfg.regex_rules)
                        self._data.append(
                            [
                                str(nid),
                                card["src"],
                                result,
                                f"{preset['deck']} / {src}:{dst}",
                                index,
                            ]
                        )
                        # Keeping track what "cards" (src:dst pairs) have been processed
                        processed.append({"src": card["src"], "dst": card["dst"]})
        self.endResetModel()

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        self.layoutAboutToBeChanged.emit()
        self._data.sort(key=lambda x: str(x[column]), reverse=True)
        self.layoutChanged.emit()


class DictTableModel(GenericTable):
    def __init__(self, parent, data: list[dict[str, str]], headers: list[str]):
        super().__init__(parent, headers, data)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole) -> None:
        if not self.checkIndex(index):
            return None

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            row = index.row()
            column = self._headers[index.column()].lower()
            return self._data[row][column]
        # This is fallback value for all the roles that weren't specified
        return None

    def setData(self, index, value, role):
        if role == Qt.ItemDataRole.EditRole and self.checkIndex(index):
            row = index.row()
            column = self._headers[index.column()]
            self._data[row][column] = value
            print("\nThe table has been changed: ", self._data)
            # Transfer changes from our instance of ConfigManager() into the meta.json
            cfg.save()
            # Inform views that the changes took place; index, index means that only one cell was changed
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole])
            return True

        print("Nothing to change")
        return False

    def flags(self, index):
        return Qt.ItemFlag.ItemIsEditable | super().flags(index)

    def insertRows(self, row: int, count: int, parent: QModelIndex) -> bool:
        try:
            new_items = [dict.fromkeys(self._headers, "") for _ in range(count)]
            # Inform the View we are starting
            # if first = 1, count = 3, last = first + count - 1 = 3
            self.beginInsertRows(parent, row, row + count - 1)

            for i, item in enumerate(new_items):
                self._data.insert(row + i, item)

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
            del self._data[row : count + row]

            # write changes in meta.json
            cfg.save()

            return True

        except Exception as e:
            print(f"Failed to remove rows: {e}")
            return False

        # It will be called even if we get to the return statements
        finally:
            self.endRemoveRows()

    def reset_to_defaults(self, parameter: str):

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
            # self.something = default[parameter] makes a new reference and audio_preview_table becomes disconnected
            # => doesn't show the changes after resetting
            self._data.clear()
            self._data.extend(default[parameter])

            # we update our singleton and write the changes
            # our singleton has a setter that calls cfg.save()
            setattr(cfg, parameter, self._data)

        self.endResetModel()
