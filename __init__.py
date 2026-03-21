from aqt import (
    QAbstractItemModel,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QLineEdit,
    QSlider,
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
from .models import ModelAudioTbl, ModelRegexTbl


import os

from .config import cfg

from aqt.operations import QueryOp

import sys


sys.path.append(os.path.join(os.path.dirname(__file__), "designer"))
sys.path.append(os.path.dirname(__file__))


class Preview(QDialog):
    note_processed = pyqtSignal()

    def __init__(self, parent, ids: list[int]):
        print(f"\n{type(self).__name__} is opened")

        super().__init__(parent)

        self.ui = dialog.Ui_Dialog()
        self.ui.setupUi(self)

        self.voices_list = self._get_voices()

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

        self.preview_model = ModelAudioTbl(ids, self)
        self.ui.tbl_audio_gen.setModel(self.preview_model)

        self.cancel_event = Event()
        qconnect(self.ui.btn_generate.clicked, self._start_task)
        qconnect(self.ui.btn_cancel.clicked, self._on_cancel)
        qconnect(self.ui.btn_settings.clicked, self._open_settings)

        self.ui.tbl_audio_gen.horizontalHeader().setStretchLastSection(True)
        self.ui.tbl_audio_gen.setColumnWidth(1, 200)
        self.ui.tbl_audio_gen.setColumnWidth(2, 200)

        # The progress bar
        self._set_up_progress()
        # Connect the signal that we pass to our background function to the slot
        self.note_processed.connect(self.move_progress)

        # It's either this or using exec() instead or open()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        # hook up the model to an instance of the dialog so that
        # when the dialog dies the model dies with it
        self.regex_model = ModelRegexTbl(self)

        ############################## Settings ##############################

        self.ui.tabSettings.setMinimumHeight(280)
        # "hiding" the settings part
        self.ui.splitter.setSizes([1, 0])

        ######## Chatterbox ##############################

        # Emotion (exaggeration): 0.25-2.0
        self.ui.sb_emotion.setSingleStep(0.05)
        self.ui.sb_emotion.setMinimum(0.25)
        self.ui.sb_emotion.setMaximum(2.00)
        self.ui.sb_emotion.setValue(cfg.exaggeration)
        self.ui.sb_emotion.valueChanged.connect(self._update_exaggeration)

        self.ui.sld_emotion.setSingleStep(1)
        self.ui.sld_emotion.setMinimum(25)
        self.ui.sld_emotion.setMaximum(200)
        self.ui.sld_emotion.setValue(int(cfg.exaggeration * 100))
        self.ui.sld_emotion.sliderReleased.connect(self._update_exaggeration)

        self._sync_slider_to_spinbox(self.ui.sld_emotion, self.ui.sb_emotion)

        # Pace control(cfg_weight): 0.0-1.0
        self.ui.sb_pace.setSingleStep(0.05)
        self.ui.sb_pace.setMinimum(0.00)
        self.ui.sb_pace.setMaximum(1.00)
        self.ui.sb_pace.setValue(cfg.cfg_weight)
        self.ui.sb_pace.valueChanged.connect(self._update_cfg_weight)

        self.ui.sld_pace.setSingleStep(1)
        self.ui.sld_pace.setMinimum(0)
        self.ui.sld_pace.setMaximum(100)
        self.ui.sld_pace.setValue(int(cfg.cfg_weight * 100))
        self.ui.sld_pace.sliderReleased.connect(self._update_cfg_weight)

        self._sync_slider_to_spinbox(self.ui.sld_pace, self.ui.sb_pace)

        # Sample randomness (temperature): 0.05 - 5.00
        self.ui.sb_temp.setSingleStep(0.05)
        self.ui.sb_temp.setMinimum(0.05)
        self.ui.sb_temp.setMaximum(5.00)
        self.ui.sb_temp.setValue(cfg.temp)
        self.ui.sb_temp.valueChanged.connect(self._update_temp)

        self.ui.sld_temp.setSingleStep(1)
        self.ui.sld_temp.setMinimum(5)
        self.ui.sld_temp.setMaximum(500)
        self.ui.sld_temp.setValue(int(cfg.temp * 100))
        self.ui.sld_temp.sliderReleased.connect(self._update_temp)

        self._sync_slider_to_spinbox(self.ui.sld_temp, self.ui.sb_temp)

        ######## Presets ##############################
        ### Fallback preset
        self.ui.le_source.setText(cfg.fallback_src)
        self.ui.le_dest.setText(cfg.fallback_dst)

        self.ui.le_source.editingFinished.connect(
            lambda: self._set_fallback(self.ui.le_source, "fallback_src")
        )

        self.ui.le_dest.editingFinished.connect(
            lambda: self._set_fallback(self.ui.le_dest, "fallback_dst")
        )

        # We need to repopulate the combobox before declaring the currentTextChanged signal
        # otherwise it will constantly rewrite the cfg.value
        if self.voices_list == []:
            self.ui.cb_voice.addItems(["Default"])
            self._set_combobox(self.ui.cb_voice, "Default")
        else:
            self.ui.cb_voice.addItems(self.voices_list)
            self.ui.cb_voice.setCurrentText(cfg.fallback_voice)
            self._set_combobox(self.ui.cb_voice, cfg.fallback_voice)
            print("Fallback voice", cfg.fallback_voice)

        self.ui.cb_voice.currentTextChanged.connect(
            lambda text: setattr(cfg, "fallback_voice", text)
        )

        self.ui.cb_lang.currentTextChanged.connect(
            lambda text: setattr(cfg, "fallback_lang", text)
        )
        self.ui.cb_lang.setCurrentText(cfg.fallback_lang)

        print(f"\n{type(self).__name__} children: ", len(parent.findChildren(Preview)))

        ######## Text Processing ##############################

        # the table view will call the data() method of the model
        self.ui.tbl_regex.setModel(self.regex_model)
        self.ui.tbl_regex.resizeColumnsToContents()
        self.ui.tbl_regex.horizontalHeader().setStretchLastSection(True)

        # we can trigger the update just by getting the table focus
        self.regex_model.dataChanged.connect(
            lambda: self.preview_model.refresh_data(self.note_ids)
        )
        self.regex_model.layoutChanged.connect(
            lambda: self.preview_model.refresh_data(self.note_ids)
        )

        qconnect(self.ui.btn_regex_add.clicked, self._regex_add)
        qconnect(self.ui.btn_regex_remove.clicked, self._regex_remove)
        qconnect(self.ui.btn_regex_restore.clicked, self._regex_reset)

        ######## Virtual Environment ##############################

        qconnect(self.ui.btn_set_virt_env.clicked, self._select_virt_env)
        self.ui.le_set_virt_env.setText(cfg.virt_env)
        self.ui.le_set_virt_env.setReadOnly(True)

        qconnect(self.ui.btn_set_model.clicked, self._select_model)
        self.ui.le_set_model.setText(cfg.model_path)
        self.ui.le_set_model.setReadOnly(True)

        # ROCm. HSA_OVERRIDE
        if sys.platform == "linux":
            self._toggle_hsa_settings(True)
            self.ui.le_set_hsa.setText(cfg.hsa_version)
            # 0 - number permitted, but not required
            # 9 - number required
            self.ui.le_set_hsa.setInputMask("09.9.9")
            self.ui.ck_set_hsa.setChecked(cfg.hsa_enabled)
            qconnect(self.ui.le_set_hsa.editingFinished, self._set_hsa_version)
            qconnect(self.ui.ck_set_hsa.clicked, self._change_hsa_status)
        else:
            # Windows or OSx don't have full ROCm support as far as I know
            self._toggle_hsa_settings(False)
            self.ui.hor_layout_hsa.setEnabled(False)

    ############################## Dialog methods ##############################

    def _set_fallback(self, widget: QLineEdit, attr_name: str):
        text = widget.text()
        print(f"Saving {widget}: {text}")
        setattr(cfg, attr_name, text)
        self.preview_model.refresh_data(self.note_ids)
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

        note_id = self.note_ids[self.tracking]

        print(
            f"\n✓ Processing {note_id}: {self.tracking + 1} out of {len(self.note_ids)}"
        )

        generate = QueryOp(
            parent=self,
            op=lambda col: generate_audio_batch(
                col,
                self.note_ids[self.tracking],
                self.cancel_event,
                processed=self.note_processed.emit,
            ),
            success=self._generate_success,
        )

        generate.failure(self._generate_failure).run_in_background()

    def _generate_next(self):
        if self.tracking < len(self.note_ids):
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
        elif return_code is None:
            print("\n⚠ Skipping: Note contains missing or invalid fields.")
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
        self.ui.prg_audio_preview.setMaximum(len(self.note_ids))

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

        if row >= self.preview_model.rowCount():
            return

        index = self.preview_model.index(row, 3)
        current_status = self.preview_model.data(index, Qt.ItemDataRole.DisplayRole)
        new_status = "Done" if current_status in ("OK", "Done") else "Skipped"

        self.preview_model.setData(index, new_status, Qt.ItemDataRole.EditRole)

        self.tracking += 1

        self.ui.tbl_audio_gen.selectRow(self.tracking)
        self.ui.prg_audio_preview.setValue(self.tracking)

    ############################## Settings methods ##############################

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

    @staticmethod
    def _set_combobox(combobox: QComboBox, value: str):
        """
        Sets the combobox to a specific text value if it exists, otherwise defaults to the first item.

        :param combobox: The QComboBox widget to update.
        :param value: The string value to search for in the list.
        """
        index = combobox.findText(value)

        print(f"value: {value}, index: {index}")

        if index >= 0:
            combobox.setCurrentIndex(index)
        else:
            combobox.setCurrentIndex(0)

    @staticmethod
    def _get_voices() -> list[str]:
        """
        Scans user_files for *.mp3, *.ogg and *.wav files.

        :return: Names of discovered audio files.
        """
        path = os.path.join(os.path.dirname(__file__), "user_files")
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

    def _toggle_hsa_settings(self, state: bool):
        self.ui.hor_layout_hsa.setEnabled(state)
        self.ui.ck_set_hsa.setVisible(state)
        self.ui.le_set_hsa.setVisible(state)
        self.ui.lb_set_hsa.setVisible(state)

    # spinboxes already have converted float numbers, so it's easier to use them
    def _update_exaggeration(self):
        cfg.exaggeration = round(self.ui.sb_emotion.value(), 2)

    def _update_cfg_weight(self):
        cfg.cfg_weight = round(self.ui.sb_pace.value(), 2)

    def _update_temp(self):
        cfg.temp = round(self.ui.sb_temp.value(), 2)

    @staticmethod
    def _sync_slider_to_spinbox(
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

    def _regex_add(self):
        new_row_idx = self.regex_model.rowCount()
        print("\nNumber of rows: ", new_row_idx)
        if self.regex_model.insertRow(new_row_idx):
            index = self.regex_model.index(new_row_idx, 0)
            print("index: ", index)

            # moves the "selection highlight" (the blue box or dotted outline).
            self.ui.tbl_regex.setCurrentIndex(index)
            self.ui.tbl_regex.edit(index)

    def _regex_remove(self):
        # contains indexes for every selected cell therefore in a 2x3 table
        # selection = 6 even though selected rows = 2
        selection = self.ui.tbl_regex.selectedIndexes()

        # selection = 6, but rows only 2 => if we filter out all the duplicates,
        # we get the indexes of selected rows. set comprehension does exactly that
        rows = {i.row() for i in selection}

        print("\n_regex_remove.clicked")

        # every time we remove an item from a list, its indexes shift.
        # we will get "list assignment index out of range" errors
        # unless we remove elements from the bottom first
        for i in sorted(rows, reverse=True):
            print(f"\nselected: {len(rows)}, row: {i}")
            self.regex_model.removeRow(i)
        self.regex_model.layoutChanged.emit()

    def _regex_reset(self):
        self.regex_model.reset_to_defaults()
        self.regex_model.layoutChanged.emit()

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
