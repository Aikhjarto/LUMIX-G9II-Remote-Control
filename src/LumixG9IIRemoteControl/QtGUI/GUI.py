import logging
import pprint
import signal
import sys
import traceback
from typing import Dict

from PySide6 import QtCore, QtGui
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .CameraWidget import CameraWidget
from .LiveStreamWidget import LiveStreamWidget
from .RecordSettingsWidget import RecordSettingsWidget

logging.basicConfig()
logger = logging.getLogger()
logger.setLevel("INFO")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lumix G9II Remote Control")

        self.error_message = QMessageBox()

        self.livestream_widget = LiveStreamWidget()
        self.livestream_widget.drag_start.connect(self._drag_start)
        self.livestream_widget.drag.connect(self._drag_continue)
        self.livestream_widget.drag_stop.connect(self._drag_stop)
        self.livestream_widget.click.connect(self._click)

        self.status_widget = QLabel(text="Camera not connected")
        self.camera_widget = CameraWidget()
        self.record_settings_widget = RecordSettingsWidget(self.camera_widget.g9ii)
        self.camera_widget.cameraAllmenuChanged.connect(
            self.record_settings_widget.apply_allmenu_xml
        )
        self.camera_widget.cameraCurmenuChanged.connect(
            self.record_settings_widget.apply_curmenu_xml
        )
        self.camera_widget.cameraStateChanged.connect(
            lambda x: self.status_widget.setText(pprint.pformat(x))
        )
        self.record_settings_widget.requestCamCgiCall.connect(
            self.camera_widget.run_camcgi_from_dict
        )

        layout = QVBoxLayout()
        layout.addWidget(self.camera_widget)

        self.play_rec_mode_button = QPushButton("Play/Rec")
        self.play_rec_mode_button.setEnabled(True)
        self.play_rec_mode_button.setCheckable(True)
        self.play_rec_mode_button.clicked.connect(self._play_rec_toggle)
        layout.addWidget(self.play_rec_mode_button)

        self.shutter_button = QPushButton("Capture")
        self.shutter_button.setEnabled(True)
        self.shutter_button.clicked.connect(self._capture)
        layout.addWidget(self.shutter_button)

        self.rec_button = QPushButton("Rec. Video")
        self.rec_button.setEnabled(True)
        self.rec_button.setCheckable(True)
        self.rec_button.clicked.connect(self._rec_video)
        layout.addWidget(self.rec_button)

        self.livestream_button = QPushButton("LiveStream")
        self.livestream_button.setEnabled(True)
        self.livestream_button.setCheckable(True)
        self.livestream_button.clicked.connect(self._livestream_toggle)
        layout.addWidget(self.livestream_button)

        button = QPushButton("Screen on")
        button.clicked.connect(self._lcd_on)
        layout.addWidget(button)
        button = QPushButton("Quit")
        button.clicked.connect(self._quit)
        layout.addWidget(button)

        control_widget = QWidget()
        control_widget.setLayout(layout)

        layout = QHBoxLayout()
        layout.addWidget(control_widget, stretch=0)
        layout.addWidget(self.livestream_widget, stretch=0)
        layout.addWidget(self.record_settings_widget, stretch=0)

        scroll = QScrollArea()
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.status_widget)
        layout.addWidget(scroll, stretch=0)

        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

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
    def _play_rec_toggle(self, *args):
        if self.play_rec_mode_button.isChecked():
            return self.camera_widget.g9ii.set_recmode()
        else:
            return self.camera_widget.g9ii.set_playmode()

    @_no_raise
    def _livestream_toggle(self, *args):
        if self.livestream_button.isChecked():
            print("Start stream")
            return self.camera_widget.g9ii.start_stream()
        else:
            print("stop stream")
            return self.camera_widget.g9ii.stop_stream()

    @_no_raise
    def _rec_video(self, *args):
        if self.rec_button.isChecked():
            return self.camera_widget.g9ii.video_recstart()
        else:
            return self.camera_widget.g9ii.video_recstop()

    @_no_raise
    def _capture(self, *args):
        return self.camera_widget.g9ii.capture()

    @_no_raise
    def _drag_start(self, pos: QtCore.QPoint):
        return self.camera_widget.g9ii.send_touch_drag("start", pos.x(), pos.y())

    @_no_raise
    def _drag_stop(self, pos: QtCore.QPoint):
        return self.camera_widget.g9ii.send_touch_drag("stop", pos.x(), pos.y())

    @_no_raise
    def _drag_continue(self, pos: QtCore.QPoint):
        return self.camera_widget.g9ii.send_touch_drag("continue", pos.x(), pos.y())

    @_no_raise
    def _click(self, pos: QtCore.QPoint):
        return self.camera_widget.g9ii.send_touch_coordinate(pos.x(), pos.y())

    @_no_raise
    def _lcd_on(self, *args):
        return self.camera_widget.g9ii.lcd_on()

    def _quit(self, *args):
        QApplication.quit()


def main():

    def sigint_handler(*args, **kwargs):
        QApplication.quit()

    signal.signal(signal.SIGINT, sigint_handler)
    app = QApplication(sys.argv)

    mw = MainWindow()
    mw.show()

    timer = QTimer()
    timer.start(200)
    timer.timeout.connect(lambda: None)  # Let the interpreter run periodically

    app.exec()


if __name__ == "__main__":
    main()
