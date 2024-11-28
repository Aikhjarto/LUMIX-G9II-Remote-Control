import logging
import threading
import traceback
import xml.etree.ElementTree
from typing import Dict

import zmq
from qtpy import QtCore, QtGui
from qtpy.QtCore import Signal, Slot
from qtpy.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import LumixG9IIRemoteControl.LumixG9IIRemoteControl
from LumixG9IIRemoteControl.LumixG9IIRemoteControl import (
    didl_object_list_to_resource,
    find_lumix_camera_via_sspd,
)
from LumixG9IIRemoteControl.QtGUI.NoRaise import NoRaiseMixin

logging.basicConfig()
logger = logging.getLogger()


class ZMQReceiver(QtCore.QObject):
    dataChanged = Signal(object)

    def start(self):
        threading.Thread(target=self._execute, daemon=True).start()

    def _execute(self):
        context = zmq.Context()
        consumer_receiver = context.socket(zmq.PAIR)
        consumer_receiver.bind("tcp://*:5556")
        while True:
            obj = consumer_receiver.recv_pyobj()
            self.dataChanged.emit(obj)


class CameraWidget(QWidget, NoRaiseMixin):

    cameraStateChanged = Signal(dict)
    cameraAllmenuChanged = Signal(xml.etree.ElementTree.ElementTree)
    cameraCurmenuChanged = Signal(xml.etree.ElementTree.ElementTree)
    cameraEvent = Signal(object)
    cameraConnected = Signal(dict)
    cameraDisconnected = Signal()
    cameraItemsChanged = Signal(list)
    cameraModeChanged = Signal(str)
    cameraConnectionStateChanged = Signal(str)
    cameraSettingsChanged = Signal(list)
    lensChanged = Signal(dict)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        find_camera_button = QPushButton("Find camera")
        connect_button = QPushButton("Connect")
        connect_button.setCheckable(True)
        self.connect_button = connect_button

        edit = QLineEdit()
        edit.setPlaceholderText("mlbel")
        edit.returnPressed.connect(lambda: self.connect_button.setEnabled(True))
        find_camera_button.clicked.connect(
            lambda x, val=edit: self._find_camera(x, val)
        )
        connect_button.clicked.connect(lambda x, val=edit: self._connect(x, val))

        self.play_rec_mode_button = QPushButton("Play/Rec")
        self.play_rec_mode_button.setEnabled(False)
        self.play_rec_mode_button.setCheckable(True)
        self.play_rec_mode_button.clicked.connect(self._play_rec_toggle)

        lv = QVBoxLayout()
        lh = QHBoxLayout()
        lh.addWidget(QLabel("Camera:"))
        lh.addWidget(edit)
        lv.addLayout(lh)

        lh = QHBoxLayout()
        lh.addWidget(find_camera_button)
        lh.addWidget(connect_button)
        lv.addLayout(lh)
        lv.addWidget(self.play_rec_mode_button)

        self.setLayout(lv)

        self.g9ii = LumixG9IIRemoteControl.LumixG9IIRemoteControl.LumixG9IIRemoteControl(
            # host='mlbel',
            # auto_connect=True
        )
        # g9ii._allmenu_tree = defusedxml.ElementTree.parse("../Dumps/allmenu.xml")
        # g9ii._curmenu_tree = defusedxml.ElementTree.parse("../Dumps/curmenu.xml")
        # g9ii.set_local_language()

        self._lens_dict_cache = {}
        zmq_receiver = ZMQReceiver(self)
        zmq_receiver.dataChanged.connect(self._zmq_consumer_function)
        zmq_receiver.start()

        self.error_message = QMessageBox()

        self._old_cammode = None

        # livestream_widget.setEnabled(False)
        # self._apply_allmenu_xml(defusedxml.ElementTree.parse("../Dumps/allmenu.xml"))
        # self._apply_curmenu_xml(defusedxml.ElementTree.parse("../Dumps/curmenu.xml"))

    def _no_raise(func):
        def no_raise(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                args[0].error_message.critical(
                    args[0],
                    "G9II Error",
                    "\n".join(traceback.format_exception_only(e)),
                )

                traceback.print_exception(e)

        return no_raise

    def _connect(self, value: bool, line_edit: QLineEdit):

        if line_edit.isModified():
            host_name = line_edit.text()
        else:
            host_name = line_edit.placeholderText()

        if value:
            try:
                self.g9ii.connect(host=host_name)
            except Exception as e:
                self.error_message.critical(
                    self,
                    "G9II Error",
                    "\n".join(traceback.format_exception_only(e)),
                )
                self.connect_button.setChecked(False)
            self.play_rec_mode_button.setEnabled(True)
            self.cameraConnected.emit(
                {"host": self.g9ii.host, "headers": self.g9ii._headers}
            )
            self.cameraConnectionStateChanged.emit("connected")

        else:
            self.g9ii.disconnect()
            self.play_rec_mode_button.setEnabled(False)
            self.cameraDisconnected.emit()
            self.cameraConnectionStateChanged.emit("disconnected")
            # self.play_rec_mode_button.setEnabled(False)

    def _find_camera(self, status: bool, line_edit: QLineEdit):
        try:
            camera_hostname = find_lumix_camera_via_sspd()
        except RuntimeError as e:
            traceback.print_exception(e)
            line_edit.setPlaceholderText("no camera found")
            line_edit.setText(None)
            self.error_message.critical(
                self,
                "G9II Error",
                "\n".join(traceback.format_exception_only(e)),
            )
        else:
            line_edit.setText(camera_hostname)
            line_edit.setModified(True)
            self.connect_button.setEnabled(True)

    @Slot(dict)
    def run_camcgi_from_dict(self, data: Dict):
        self.g9ii._run_camcgi_from_dict(data)

    @Slot(object)
    def _zmq_consumer_function(self, event):
        try:
            if event["type"] == "state_dict":
                self.cameraStateChanged.emit(event["data"])
                if event["data"]["cammode"] != self._old_cammode:
                    self.cameraModeChanged.emit(event["data"]["cammode"])
                    self._old_cammode != event["data"]["cammode"]

            elif event["type"] == "allmenu_etree":
                self.cameraAllmenuChanged.emit(event["data"])

            elif event["type"] == "curmenu_etree":
                self.cameraCurmenuChanged.emit(event["data"])

            elif event["type"] == "camera_event":
                self.cameraEvent.emit(event["data"])

            elif event["type"] == "setsettings":
                self.cameraSettingsChanged.emit(event["data"])

            elif event["type"] == "lens_dict":
                # many events with same data, thus implement diff with cached version
                if self._lens_dict_cache != event["data"]:
                    self._lens_dict_cache = event["data"]
                    self.lensChanged.emit(event["data"])

            elif event["type"] == "exception":
                self.error_message.critical(
                    self,
                    "Error from Camera",
                    "\n".join(traceback.format_exception_only(event["data"])),
                )
            else:
                logger.error("Unknown message, %s", event)

        except Exception as e:
            logger.error("%s", traceback.format_exception(e))

    @_no_raise
    def _play_rec_toggle(self, *args):
        self.setStatusTip("Waiting for camera")
        if self.play_rec_mode_button.isChecked():
            self.g9ii.set_recmode()
        else:
            self.g9ii.set_playmode()
        # todo freeze until new mode is set in camera (signal cameraModeChanged is emitted)

        # self.setEnabled(False)

    @Slot(dict)
    def execute_camera_command(self, d):
        logger.info("execute_camera_command: %s", d)
        function = getattr(self.g9ii, d["function"])
        if callable(function):
            if "args" in d:
                function(*d["args"])
            else:
                function()

    def query_all_items(self, d):
        QApplication.sendEvent(self, QtGui.QStatusTipEvent(f"Query Items {d}"))
        logger.info("query_all_items: %s", d)

        data = self.g9ii.query_all_items_on_sdcard(**d)
        # data = self.g9ii.query_items_on_sdcard(*args, **kwargs)
        data2 = didl_object_list_to_resource(data)
        self.cameraItemsChanged.emit(data2)
