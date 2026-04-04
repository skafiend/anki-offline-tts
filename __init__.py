from aqt import (
    QAbstractItemModel,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QLineEdit,
    QSlider,
    QSpinBox,
    QStringListModel,
    mw,
    qconnect,
    gui_hooks,
)
from aqt.qt import Qt, QDialog, QAction, QMessageBox, pyqtSlot, pyqtSignal, sip
from aqt.browser.browser import Browser
from aqt.utils import showCritical
from aqt.sound import mpvManager
from threading import Event
from .designer import dialog
from .utils import generate_audio_batch
from .models import DictTableModel, ModelAudioTable

import shutil

import os

from .config import ConfigManager, cfg

from aqt.operations import QueryOp

import sys


user_files = os.path.join(os.path.dirname(__file__), "user_files")


class Preview(QDialog):
    note_processed = pyqtSignal()

    def __init__(self, parent, ids: list[int]):
        print(f"\n{type(self).__name__} is opened")

        super().__init__(parent)

        self.ui = dialog.Ui_Dialog()
        self.ui.setupUi(self)

        ## Flags
        # True when a task is running in the subprocess
        self.is_running = False
        # True if the settings tab is visible, False otherwise
        self.settings_visible = False
        # True if audio was generated for all notes in the preview
        self.is_finished = False

        ############################## Audio preview ##############################

        self.note_ids = ids
        self.ui.btn_cancel.setEnabled(False)

        self.mdl_preview = ModelAudioTable(
            self, ids, ["Note ID", "Text Before", "Processed Text", "Status", "Preset"]
        )
        self.ui.tbl_audio_gen.setModel(self.mdl_preview)
        # number of records in preview = number of records to process
        self.records = self.mdl_preview.rowCount()

        self.cancel_event = Event()
        qconnect(self.ui.btn_generate.clicked, self._start_task)
        qconnect(self.ui.btn_cancel.clicked, self._on_cancel)
        qconnect(self.ui.btn_settings.clicked, self._open_settings)

        self.ui.tbl_audio_gen.horizontalHeader().setStretchLastSection(True)
        self.ui.tbl_audio_gen.setColumnWidth(1, 280)
        self.ui.tbl_audio_gen.setColumnWidth(2, 280)
        self.ui.tbl_audio_gen.setColumnHidden(4, True)

        # The progress bar
        self._set_up_progress()
        # Connect the signal that we pass to our background function to the slot
        self.note_processed.connect(self.move_progress)

        # It's either this or using exec() instead or open()
        # Makes Qt delete this widget when the widget has accepted the close event (see QWidget::closeEvent()).
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        ############################## Settings ##############################

        self.ui.tabSettings.setMinimumHeight(280)
        # "hiding" the settings part
        self.ui.splitter.setSizes([1, 0])

        ######## Chatterbox ##############################

        self.ui.btn_voice_add.clicked.connect(self._add_voices)
        self.ui.btn_voice_remove.clicked.connect(self._remove_voices)

        # Exaggeration: 0.25 - 2.0
        self._configure_slider(
            self.ui.sb_emotion,
            self.ui.sld_emotion,
            0.25,
            2.00,
            0.05,
            "exaggeration",
            100.0,
        )

        # Pace control (cfg_weight): 0.0 - 1.0
        self._configure_slider(
            self.ui.sb_pace,
            self.ui.sld_pace,
            0.00,
            1.00,
            0.05,
            "cfg_weight",
            100.0,
        )

        # Sample randomness (temperature): 0.05 - 5.00
        self._configure_slider(
            self.ui.sb_temp,
            self.ui.sld_temp,
            0.05,
            5.00,
            0.05,
            "temp",
            100.0,
        )

        ######## Text Processing ##############################

        # hook up the model to an instance of the dialog so that
        # when the dialog dies the model dies with it
        self.mdl_regex = DictTableModel(
            self, cfg.regex_rules, ["pattern", "replace", "comment"]
        )

        # the table view will call the data() method of the model
        self.ui.tbl_regex.setModel(self.mdl_regex)

        self.ui.tbl_regex.resizeColumnsToContents()
        self.ui.tbl_regex.horizontalHeader().setStretchLastSection(True)

        self.mdl_regex.dataChanged.connect(
            lambda: self.mdl_preview.refresh_data(self.note_ids)
        )
        self.mdl_regex.layoutChanged.connect(
            lambda: self.mdl_preview.refresh_data(self.note_ids)
        )

        qconnect(
            self.ui.btn_regex_add.clicked,
            lambda: self._add_row_to_table(self.mdl_regex, self.ui.tbl_regex),
        )
        qconnect(
            self.ui.btn_regex_remove.clicked,
            lambda: self._remove_selected_rows(self.mdl_regex, self.ui.tbl_regex),
        )
        qconnect(self.ui.btn_regex_restore.clicked, self._regex_restore)

        ######## Virtual Environment ##############################

        qconnect(self.ui.btn_set_virt_env.clicked, self._select_virt_env)
        self.ui.le_set_virt_env.setText(cfg.virt_env)
        self.ui.le_set_virt_env.setReadOnly(True)

        qconnect(self.ui.btn_set_model.clicked, self._select_model)
        self.ui.le_set_model.setText(cfg.model_path)
        self.ui.le_set_model.setReadOnly(True)

        # ROCm. HSA_OVERRIDE
        if sys.platform == "linux":
            self._hsa_visibility(True)
            self.ui.le_set_hsa.setText(cfg.hsa_version)
            # 0 - number permitted, but not required
            # 9 - number required
            self.ui.le_set_hsa.setInputMask("09.9.9")
            self.ui.ck_set_hsa.setChecked(cfg.hsa_enabled)
            qconnect(self.ui.le_set_hsa.editingFinished, self._set_hsa_version)
            qconnect(self.ui.ck_set_hsa.clicked, self._change_hsa_status)
        else:
            # Windows or OSx don't have full ROCm support as far as I know
            self._hsa_visibility(False)
            self.ui.hor_layout_hsa.setEnabled(False)

        # How many children check
        print(f"\n{type(self).__name__} children: ", len(parent.findChildren(Preview)))

        ######## Presets ##############################
        self.mdl_presets = DictTableModel(
            self, cfg.presets, ["source", "destination", "voice", "language", "mode"]
        )
        self.ui.tbl_presets.setModel(self.mdl_presets)
        self.ui.tbl_presets.resizeColumnsToContents()
        self.ui.tbl_presets.horizontalHeader().setStretchLastSection(True)

        self.ui.tbl_presets.setColumnWidth(0, 150)
        self.ui.tbl_presets.setColumnWidth(1, 150)
        self.ui.tbl_presets.setColumnWidth(2, 150)
        self.ui.tbl_presets.setColumnWidth(3, 100)

        self.mdl_presets.dataChanged.connect(
            lambda: self.mdl_preview.refresh_data(self.note_ids)
        )
        self.mdl_presets.layoutChanged.connect(
            lambda: self.mdl_preview.refresh_data(self.note_ids)
        )

        qconnect(
            self.ui.btn_preset_add.clicked,
            lambda: self._add_row_to_table(self.mdl_presets, self.ui.tbl_presets),
        )
        qconnect(
            self.ui.btn_preset_remove.clicked,
            lambda: self._remove_selected_rows(self.mdl_presets, self.ui.tbl_presets),
        )
        qconnect(self.ui.btn_preset_restore.clicked, self._preset_restore)

    def _setup_voice_combo(self):
        # Disable signals to avoid triggering this
        # self.ui.cb_voice.currentTextChanged.connect
        self.ui.cb_voice.blockSignals(True)
        voices_list = self._get_voices()
        # Start with Default, then add other voices if they exist
        items = ["Default"] + (voices_list if voices_list else [])

        self.ui.cb_voice.clear()
        self.ui.cb_voice.addItems(items)
        self.ui.cb_voice.blockSignals(False)

        # Set selection: use fallback if list isn't empty, otherwise Default
        selection = cfg.fallback_voice if voices_list else "Default"
        self.ui.cb_voice.setCurrentText(selection)

    @staticmethod
    def _get_voices() -> list[str]:
        """
        Scans user_files for *.mp3, *.ogg and *.wav files.
        :return: Names of discovered audio files.
        """
        path = user_files
        voices = []
        with os.scandir(path) as it:
            for entry in it:
                if (
                    not entry.name.startswith(".")
                    and entry.is_file()
                    and entry.name.lower().endswith((".mp3", ".ogg", ".wav"))
                ):
                    voices.append(entry.name)
        return voices

    ############################## Dialog ##############################

    def closeEvent(self, event: Event):
        if self.is_running:
            reply = QMessageBox.question(
                self,
                "Operation in Progress",
                "Audio generation is still running. Do you want to interrupt it and close?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                print("Interrupting operation...")
                self._on_cancel()
                # events are accepted by default, unless it's stated otherwise
                # so even if we don't call event.accept() explicitly
                # the dialog will be closed
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    # This method triggers when we press Esc
    def reject(self):
        self.close()  # This part triggers closeEvent

    def _set_lineedit(self, widget: QLineEdit, attr_name: str):
        text = widget.text()
        print(f"Saving {widget}: {text}")
        setattr(cfg, attr_name, text)
        self.mdl_preview.refresh_data(self.note_ids)
        # Remove focus after pressing enter
        widget.clearFocus()

    def _toggle_ui_busy(self, busy: bool):
        """Enables/disables UI elements based on processing state."""
        if not sip.isdeleted(self):
            self.ui.btn_generate.setEnabled(not busy)
            self.ui.btn_cancel.setEnabled(busy)
            self.ui.tabSettings.setDisabled(busy)

    def _start_task(self):
        # If we want to regenerate notes again
        # the progress should be reset
        if self.is_finished:
            self.tracking = 0
            self._set_up_progress()

        self._toggle_ui_busy(True)
        self.cancel_event.clear()
        self._generate_audio()

    def _generate_audio(self):
        # Get the 'Model Indexes' (the pointers to the cells)
        id_idx = self.mdl_preview.index(self.tracking, 0)
        print("id_idx", id_idx)
        preset_idx = self.mdl_preview.index(self.tracking, 4)

        # Extract the actual Data from those cells
        note_id = int(self.mdl_preview.data(id_idx, Qt.ItemDataRole.DisplayRole))
        note_preset = int(
            self.mdl_preview.data(preset_idx, Qt.ItemDataRole.DisplayRole)
        )
        note = mw.col.get_note(note_id)

        if note_preset >= 0:
            preset = cfg.presets[note_preset]

            print(
                f"\n✓ Processing {note_id}: {self.tracking + 1} out of {self.records}"
            )
            generate = QueryOp(
                parent=self,
                op=lambda col: generate_audio_batch(
                    col,
                    note,
                    self.cancel_event,
                    preset,
                    processed=self.note_processed.emit,
                ),
                success=self._generate_success,
            )

            generate.failure(self._generate_failure).run_in_background()
        else:
            print(f"\n✓ {note_id}: No valid preset index found. Skipping...")
            self.note_processed.emit()
            self._generate_next()

    def _generate_next(self):
        if self.tracking < self.records:
            self.is_running = True
            self.ui.tbl_audio_gen.selectRow(self.tracking)
            self._generate_audio()
        else:
            print("\n✓ We're done. No notes to process!")
            self.is_finished = True
            self.is_running = False
            self._toggle_ui_busy(False)

    def _generate_success(self, return_code: int) -> None:
        if return_code == 0:
            print("\n✓ Audio generation successful.")
            self._generate_next()
        else:
            self.is_finished = False
            self.is_running = False
            self._toggle_ui_busy(False)
            print("\n✖ Background task terminated unexpectedly.")

    def _generate_failure(self, result: Exception | int):
        self.is_running = False
        self._toggle_ui_busy(False)

        if isinstance(result, Exception):
            showCritical(f"\n✖ Generation failed: {str(result)}")

    def _on_cancel(self):
        print("\n✖ Terminating background operations...")
        self.ui.tabSettings.setDisabled(False)
        self.cancel_event.set()

    def _set_up_progress(self):
        self.ui.prg_audio_preview.setMinimum(0)
        self.ui.prg_audio_preview.setMaximum(self.records)

        self.ui.prg_audio_preview.setValue(0)

        # %p - is replaced by the percentage completed.
        # %v - is replaced by the current value.
        # %m - is replaced by the total number of steps.
        self.message = "%p% - Completed: %v out of %m"
        self.ui.prg_audio_preview.setFormat(self.message)

        # Track where we are, in case cancel is pressed
        self.tracking = 0

    @pyqtSlot()
    def move_progress(self):
        row = self.tracking

        if row >= self.records:
            return

        index = self.mdl_preview.index(row, 3)
        current_status = self.mdl_preview.data(index, Qt.ItemDataRole.DisplayRole)
        new_status = "Done" if current_status in ("OK", "Done") else "Skipped"

        self.mdl_preview.setData(index, new_status, Qt.ItemDataRole.EditRole)

        self.tracking += 1

        self.ui.tbl_audio_gen.selectRow(self.tracking)
        self.ui.prg_audio_preview.setValue(self.tracking)

    ############################## Settings ##############################

    def _open_settings(self):
        if self.settings_visible:
            # "hide" the settings part
            self.ui.splitter.setSizes([300, 0])
            self.settings_visible = False
        else:
            # "show" the settings part
            # the minimum height of the settings widget determines
            # how much space does it take, so we can pass just 1 to make it fully visible
            self.ui.splitter.setSizes([300, 1])
            self.settings_visible = True

    ######### Chatterbox ################################################

    def _add_voices(self):
        dialog = QFileDialog(self)
        dialog.setWindowTitle("Add new voices")
        dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        dialog.setNameFilter("Audio (*.mp3 *.wav *.ogg)")

        # Change the "Open" button text to "Add"
        dialog.setLabelText(QFileDialog.DialogLabel.Accept, "Add")

        if dialog.exec():
            source_paths = dialog.selectedFiles()

            try:
                for path in source_paths:
                    filename = os.path.basename(path)
                    target_file = os.path.join(user_files, filename)

                    shutil.copyfile(path, target_file)
                    print(f"Added: {filename}")
            except FileNotFoundError as e:
                print(e)
            except shutil.SameFileError as e:
                print(f"Source and destination are the same file: {e}")
            finally:
                self._setup_voice_combo()

    def _remove_voices(self):
        dialog = QFileDialog(self)
        dialog.setWindowTitle("Delete voices")
        dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        dialog.setDirectory(user_files)
        dialog.setNameFilter("Audio (*.mp3 *.wav *.ogg)")

        # Change the "Open" button text to "Add"
        dialog.setLabelText(QFileDialog.DialogLabel.Accept, "Delete")

        if dialog.exec():
            file_paths = dialog.selectedFiles()

            try:
                for path in file_paths:
                    os.remove(path)
                    print(f"Removed: {os.path.basename(path)}")
            except Exception as e:
                print(f"Error deleting file: {e}")
            finally:
                # update values in combobox
                self._setup_voice_combo()

    def _configure_slider(
        self,
        spinbox: QDoubleSpinBox,
        slider: QSlider,
        minimum: float,
        maximum: float,
        step: float,
        parameter: str,
        factor: float,
    ):
        """
        Synchronizes a QSpinBox and QSlider to control a shared configuration parameter.

        Args:
            spinbox: The spinbox widget for precise input.
            slider: The slider widget for coarse visual input.
            minimum: The lower bound for the parameter value.
            maximum: The upper bound for the parameter value.
            step: The incremental change allowed for the value.
            parameter: The attribute name in 'cfg' to be updated.
            factor: A multiplier (e.g., 100) to map float values to the slider's integer range.
        """
        current = getattr(cfg, parameter)
        spinbox.setSingleStep(step)
        spinbox.setMinimum(minimum)
        spinbox.setMaximum(maximum)
        spinbox.setValue(current)

        slider.setSingleStep(int(step * factor))
        slider.setMinimum(int(minimum * factor))
        slider.setMaximum(int(maximum * factor))
        slider.setValue(int(current * factor))

        spinbox.valueChanged.connect(
            lambda: setattr(cfg, parameter, round(spinbox.value(), 2))
        )

        slider.sliderReleased.connect(
            lambda: setattr(cfg, parameter, round(spinbox.value(), 2))
        )

        self._link_slider_to_spinbox(slider, spinbox)

    @staticmethod
    def _link_slider_to_spinbox(
        slider: QSlider, spinbox: QDoubleSpinBox, factor: float = 100.0
    ):
        """Links an integer slider and a double spinbox with a scaling factor."""

        def update_spin(val):
            # both widgets emit valueChanged() whether the user set it or the code, so
            # we disable signals to avoid extraneous calls
            spinbox.blockSignals(True)
            spinbox.setValue(val / factor)
            print("spin is updating:", spinbox.value())
            spinbox.blockSignals(False)

        def update_slider(val):
            slider.blockSignals(True)
            slider.setValue(int(val * factor))
            print("slider is updating:", slider.value())
            slider.blockSignals(False)

        slider.valueChanged.connect(update_spin)
        spinbox.valueChanged.connect(update_slider)

    ######### Edit tables ################################################
    def _add_row_to_table(self, model, table_view):
        new_row_idx = model.rowCount()

        if model.insertRow(new_row_idx):
            index = model.index(new_row_idx, 0)
            table_view.setCurrentIndex(index)
            table_view.edit(index)

    def _remove_selected_rows(self, model, table_view):
        # contains indexes for every selected cell therefore in a 2x3 table
        # selection = 6 even though selected rows = 2
        selection = table_view.selectedIndexes()

        # selection = 6, but rows only 2 => if we filter out all the duplicates,
        # we get the indexes of selected rows. set comprehension does exactly that
        rows = {i.row() for i in selection}

        # every time we remove an item from a list, its indexes shift.
        # we will get "list assignment index out of range" errors
        # unless we remove elements from the bottom first
        for i in sorted(rows, reverse=True):
            model.removeRow(i)

        # Notify the view that the layout has changed
        model.layoutChanged.emit()

    def _regex_restore(self):
        self.mdl_regex.reset_to_defaults("regex_rules")
        self.mdl_regex.layoutChanged.emit()

    def _preset_restore(self):
        self.mdl_presets.reset_to_defaults("presets")
        self.mdl_presets.layoutChanged.emit()

    ######### Virtual Environment ################################################

    def _select_model(self):
        model_path = QFileDialog.getExistingDirectory(self)
        if model_path != "":
            print("Model path: ", model_path)
            self.ui.le_set_model.setText(model_path)
            cfg.model_path = model_path
        else:
            print("Nothing is selected.")
        pass

    def _select_virt_env(self):

        # QFileDialog returns a tuple:
        # tts_python: ('<path>', 'All Files (*)')
        virt_env = QFileDialog.getOpenFileName(self)

        if virt_env != ("", ""):
            print("Path to python executable: ", virt_env)
            self.ui.le_set_virt_env.setText(virt_env[0])
            cfg.virt_env = virt_env[0]
        else:
            print("Nothing is selected.")

    def _hsa_visibility(self, state: bool):
        self.ui.hor_layout_hsa.setEnabled(state)
        self.ui.ck_set_hsa.setVisible(state)
        self.ui.le_set_hsa.setVisible(state)
        self.ui.lb_set_hsa.setVisible(state)

    def _change_hsa_status(self):
        if self.ui.ck_set_hsa.isChecked():
            print("HSA support enabled")
            cfg.hsa_enabled = True
        else:
            print("HSA support disabled")
            cfg.hsa_enabled = False

    def _set_hsa_version(self):
        version = self.ui.le_set_hsa.text()
        print(f"Saving a HSA variable: {version}")
        cfg.hsa_version = version
        self.ui.le_set_hsa.clearFocus()


def open_generate_dlg(browser: Browser):
    action = QAction("Chatterbox: Generate Audio", mw)

    def on_click():
        ids = browser.selected_notes()

        if not ids:
            showCritical("Select at least one note to proceed!")
            return

        # Save and
        browser.editor.saveNow(lambda: browser.form.searchEdit.setFocus())
        Preview(browser, ids).open()

    qconnect(action.triggered, on_click)
    browser.form.menuEdit.addAction(action)
    print("\nChatterbox: Chatterbox added to the menuEdit")


gui_hooks.browser_menus_did_init.append(open_generate_dlg)
