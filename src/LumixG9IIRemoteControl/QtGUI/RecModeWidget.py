import logging
import pprint
import traceback
from typing import Dict

from qtpy import QtCore, QtGui
from qtpy.QtCore import QUrl, Signal, Slot
from qtpy.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from qtpy.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .LiveStreamWidget import LiveStreamWidget
from .RecordSettingsWidget import RecordSettingsWidget

logging.basicConfig()
logger = logging.getLogger()


class RecModeWidget(QWidget):

    cameraCommandRequest = Signal(dict)

    def __init__(self, g9ii, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.error_message = QMessageBox()

        self.livestream_button = QPushButton("LiveStream")
        self.livestream_button.setCheckable(True)
        self.livestream_button.clicked.connect(self._livestream_toggle)

        self.record_settings_widget = RecordSettingsWidget(g9ii)

        self.livestream_widget = LiveStreamWidget()
        self.livestream_widget.drag_start.connect(self._drag_start)
        self.livestream_widget.drag.connect(self._drag_continue)
        self.livestream_widget.drag_stop.connect(self._drag_stop)
        self.livestream_widget.click.connect(self._click)

        control_layout1 = QHBoxLayout()

        caputer_button = QPushButton("Capture")
        caputer_button.clicked.connect(
            lambda _: self.cameraCommandRequest.emit({"function": "capture"})
        )

        self.rec_button = QPushButton("Rec. Video")
        self.rec_button.setCheckable(True)
        self.rec_button.clicked.connect(self._rec_video_toggle)

        oneshot_af_button = QPushButton("Oneshot")
        oneshot_af_button.clicked.connect(
            lambda _: self.cameraCommandRequest.emit({"function": "oneshot_af"})
        )

        lcd_on_button = QPushButton("Screen on")
        lcd_on_button.clicked.connect(
            lambda _: self.cameraCommandRequest.emit({"function": "lcd_on"})
        )

        self.touchcapt_ctrl_button = QPushButton("Touch: Aperture")
        self.touchcapt_ctrl_button.setCheckable(True)
        self.touchcapt_ctrl_button.clicked.connect(self._touchcapt_toggle)

        self.touchae_ctrl_button = QPushButton("Touch: AE")
        self.touchae_ctrl_button.setCheckable(True)
        self.touchae_ctrl_button.clicked.connect(self._touchae_toggle)

        control_layout1 = QHBoxLayout()
        control_layout1.addWidget(caputer_button)
        control_layout1.addWidget(self.rec_button)
        control_layout1.addWidget(oneshot_af_button)

        touch_layout = QGridLayout()
        touch_layout.addWidget(self.livestream_button, 0, 0)
        touch_layout.addWidget(lcd_on_button, 0, 1)
        touch_layout.addWidget(self.touchcapt_ctrl_button, 1, 0)
        touch_layout.addWidget(self.touchae_ctrl_button, 1, 1)

        move_focus_wide_fast = QPushButton("f<<")
        move_focus_wide_fast.setToolTip("Move focus wide fast")
        move_focus_wide_fast.clicked.connect(
            lambda _: self.cameraCommandRequest.emit(
                {"function": "move_focus", "args": ("wide-fast",)}
            )
        )
        move_focus_wide_normal = QPushButton("f<")
        move_focus_wide_fast.setToolTip("Move focus wide")
        move_focus_wide_normal.clicked.connect(
            lambda _: self.cameraCommandRequest.emit(
                {"function": "move_focus", "args": ("wide-normal",)}
            )
        )

        move_focus_tele_fast = QPushButton(">>f")
        move_focus_wide_fast.setToolTip("Move focus tele fast")
        move_focus_tele_fast.clicked.connect(
            lambda _: self.cameraCommandRequest.emit(
                {"function": "move_focus", "args": ("tele-fast",)}
            )
        )
        move_focus_tele_normal = QPushButton(">f")
        move_focus_wide_fast.setToolTip("Move focus tele")
        move_focus_tele_normal.clicked.connect(
            lambda _: self.cameraCommandRequest.emit(
                {"function": "move_focus", "args": ("tele-normal",)}
            )
        )

        focus_layout = QGridLayout()
        focus_layout.addWidget(move_focus_wide_fast, 0, 0)
        focus_layout.addWidget(move_focus_wide_normal, 0, 1)
        focus_layout.addWidget(move_focus_tele_normal, 1, 1)
        focus_layout.addWidget(move_focus_tele_fast, 1, 0)

        self.lens_info_label = QLabel()
        control_layout2 = QHBoxLayout()
        control_layout2.addLayout(focus_layout)
        control_layout2.addLayout(touch_layout)

        control_layout2.addWidget(self.lens_info_label)

        control_layout = QVBoxLayout()
        control_layout.addLayout(control_layout1)
        control_layout.addLayout(control_layout2)

        livestream_layout = QVBoxLayout()
        livestream_layout.addLayout(control_layout)
        livestream_layout.addWidget(self.livestream_widget)

        layout = QHBoxLayout()
        layout.addLayout(livestream_layout)
        layout.addWidget(self.record_settings_widget)

        self.setLayout(layout)

    def _no_raise(func):
        def no_raise(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                args[0].error_message.critical(
                    args[0],
                    "Error",
                    "\n".join(traceback.format_exception_only(e)),
                )

                traceback.print_exception(e)

        return no_raise

    @_no_raise
    def _livestream_toggle(self, *args):
        if self.livestream_button.isChecked():
            print("Start stream")
            self.cameraCommandRequest.emit({"function": "start_stream"})
            # return self.camera_widget.g9ii.start_stream()
        else:
            print("stop stream")
            self.cameraCommandRequest.emit({"function": "stop_stream"})
            # return self.camera_widget.g9ii.stop_stream()

    def _touchcapt_toggle(self, *args):
        checked = self.touchcapt_ctrl_button.isChecked()
        self.touchae_ctrl_button.setEnabled(not checked)
        if checked:
            self.cameraCommandRequest.emit(
                {"function": "touchcapt_ctrl", "args": ("on",)}
            )
        else:
            self.cameraCommandRequest.emit(
                {"function": "touchcapt_ctrl", "args": ("off",)}
            )

    def _touchae_toggle(self, *args):
        checked = self.touchae_ctrl_button.isChecked()
        self.touchcapt_ctrl_button.setEnabled(not checked)
        if checked:
            self.cameraCommandRequest.emit(
                {"function": "touchae_ctrl", "args": ("enable",)}
            )
        else:
            self.cameraCommandRequest.emit(
                {"function": "touchae_ctrl", "args": ("off",)}
            )

    def _rec_video_toggle(self, *args):
        if self.rec_button.isChecked():
            self.cameraCommandRequest.emit({"function": "video_recstart"})
            # return self.camera_widget.g9ii.video_recstart()
        else:
            self.cameraCommandRequest.emit({"function": "video_recstop"})
            # return self.camera_widget.g9ii.video_recstop()

    @_no_raise
    def _drag_start(self, pos: QtCore.QPoint):
        self.cameraCommandRequest.emit(
            {"function": "send_touch_drag", "args": ("start", pos.x(), pos.y())}
        )
        # return self.camera_widget.g9ii.send_touch_drag("start", pos.x(), pos.y())

    @_no_raise
    def _drag_stop(self, pos: QtCore.QPoint):
        self.cameraCommandRequest.emit(
            {"function": "send_touch_drag", "args": ("stop", pos.x(), pos.y())}
        )
        # return self.camera_widget.g9ii.send_touch_drag("stop", pos.x(), pos.y())

    @_no_raise
    def _drag_continue(self, pos: QtCore.QPoint):
        self.cameraCommandRequest.emit(
            {"function": "send_touch_drag", "args": ("continue", pos.x(), pos.y())}
        )

    @_no_raise
    def _click(self, pos: QtCore.QPoint):
        self.cameraCommandRequest.emit(
            {"function": "send_touch_coordinate", "args": (pos.x(), pos.y())}
        )
        # return self.camera_widget.g9ii.send_touch_coordinate(pos.x(), pos.y())

    @Slot(dict)
    def apply_lens_data(self, data: Dict[str, str]):
        self.lens_info_label.setText(pprint.pformat(data))
