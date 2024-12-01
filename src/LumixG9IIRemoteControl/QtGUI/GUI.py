import logging
import pprint
import signal
import sys
import traceback
from typing import Dict

import qtconsole
from qtpy import QtCore, QtGui
from qtpy.QtCore import Qt, QTimer, Signal, Slot
from qtpy.QtWidgets import (
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
    QSizePolicy,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .CameraWidget import CameraWidget
from .console import EmbedIPythonWidget
from .PlayModeWidget import PlayModeWidget
from .RecModeWidget import RecModeWidget

logging.basicConfig()
logger = logging.getLogger()
logger.setLevel("INFO")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.setWindowTitle("Lumix G9II Remote Control")

        self.error_message = QMessageBox()

        self.play_mode_widget = PlayModeWidget()
        self.play_mode_widget.show()

        self.status_widget = QLabel(text="Camera not connected")
        self.camera_widget = CameraWidget()

        self.rec_mode_widget = RecModeWidget(self.camera_widget.g9ii)
        self.rec_mode_widget.cameraCommandRequest.connect(
            self.camera_widget.execute_camera_command
        )

        self.camera_widget.cameraItemsChanged.connect(
            self.play_mode_widget.play_mode_table_widget.new_resource_list
        )

        self.play_mode_widget.imageListRequest.connect(
            self.camera_widget.query_all_items
        )
        self.camera_widget.cameraConnected.connect(
            self.play_mode_widget.play_mode_table_widget.update_connection_state
        )

        self.camera_widget.cameraStateChanged.connect(
            lambda x: self.status_widget.setText(pprint.pformat(x))
        )

        self.camera_widget.lensChanged.connect(self.rec_mode_widget.apply_lens_data)

        self.camera_widget.cameraAllmenuChanged.connect(
            self.rec_mode_widget.record_settings_widget.apply_allmenu_xml
        )
        self.camera_widget.cameraCurmenuChanged.connect(
            self.rec_mode_widget.record_settings_widget.apply_curmenu_xml
        )

        self.camera_widget.cameraSettingsChanged.connect(
            self.rec_mode_widget.record_settings_widget.apply_current_settings
        )

        self.rec_mode_widget.record_settings_widget.requestCamCgiCall.connect(
            self.camera_widget.run_camcgi_from_dict
        )

        self.camera_widget.cameraModeChanged.connect(self._cammode_changed)

        layout = QVBoxLayout()
        layout.addWidget(self.camera_widget)

        button = QPushButton("Quit")
        button.clicked.connect(self._quit)
        layout.addWidget(button)

        scroll = QScrollArea()
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.status_widget)
        layout.addWidget(scroll, stretch=0)

        control_widget = QWidget()
        control_widget.setLayout(layout)
        control_widget.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum
        )

        layout = QHBoxLayout()
        layout.addWidget(control_widget)
        layout.addWidget(self.rec_mode_widget)
        layout.addWidget(self.play_mode_widget)

        self.rec_mode_widget.setVisible(False)
        self.play_mode_widget.setVisible(False)

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

    @Slot(str)
    def _cammode_changed(self, mode: str):

        # self.setEnabled(True)
        self.status_bar.showMessage(f"Camera Mode changed to {mode}")
        self.rec_mode_widget.setVisible(mode == "rec")
        self.play_mode_widget.setVisible(mode == "play")

    # noinspection PyUnusedLocal
    @staticmethod
    def _quit(*args):
        QApplication.quit()


def main():

    # noinspection PyUnusedLocal
    def sigint_handler(*args, **kwargs):
        QApplication.quit()

    signal.signal(signal.SIGINT, sigint_handler)
    app = QApplication(sys.argv)

    mw = MainWindow()

    qtconsole = EmbedIPythonWidget()
    qtconsole.update_console_namespace(
        "LumixG9IIRemoteControl.QtGUI.GUI", type(mw).__name__, "mw"
    )

    timer = QTimer()
    timer.start(200)
    timer.timeout.connect(lambda: None)  # Let the interpreter run periodically

    qtconsole.show()
    mw.show()

    app.exec()


if __name__ == "__main__":
    main()
