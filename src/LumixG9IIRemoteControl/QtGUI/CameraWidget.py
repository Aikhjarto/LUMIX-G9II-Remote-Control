import logging
import threading
import traceback
import xml.etree.ElementTree
from typing import Dict

import zmq
from PySide6 import QtCore
from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import LumixG9IIRemoteControl.LumixG9IIRemoteControl
from LumixG9IIRemoteControl.LumixG9IIRemoteControl import find_lumix_camera_via_sspd
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        find_camera_button = QPushButton("Find camera")
        connect_button = QPushButton("Connect")
        connect_button.setCheckable(True)
        connect_button.setDisabled(True)
        self.connect_button = connect_button

        edit = QLineEdit()
        edit.setPlaceholderText("mlbel")
        edit.returnPressed.connect(lambda: self.connect_button.setEnabled(True))
        find_camera_button.clicked.connect(
            lambda x, val=edit: self._find_camera(x, val)
        )
        connect_button.clicked.connect(lambda x, val=edit: self._connect(x, val))

        lv = QVBoxLayout()
        lh = QHBoxLayout()
        lh.addWidget(QLabel("Camera:"))
        lh.addWidget(edit)
        lv.addLayout(lh)

        lh = QHBoxLayout()
        lh.addWidget(find_camera_button)
        lh.addWidget(connect_button)
        lv.addLayout(lh)
        self.setLayout(lv)

        self.g9ii = LumixG9IIRemoteControl.LumixG9IIRemoteControl.LumixG9IIRemoteControl(
            # host='mlbel',
            # auto_connect=True
        )
        # g9ii._allmenu_tree = defusedxml.ElementTree.parse("../Dumps/allmenu.xml")
        # g9ii._curmenu_tree = defusedxml.ElementTree.parse("../Dumps/curmenu.xml")
        # g9ii.set_local_language()

        zmq_receiver = ZMQReceiver(self)
        zmq_receiver.dataChanged.connect(self._zmq_consumer_function)
        zmq_receiver.start()

        # livestream_widget.setEnabled(False)
        # self._apply_allmenu_xml(defusedxml.ElementTree.parse("../Dumps/allmenu.xml"))
        # self._apply_curmenu_xml(defusedxml.ElementTree.parse("../Dumps/curmenu.xml"))

    def _no_raise(func):
        def no_raise(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                traceback.print_exception(e)

        return no_raise

    @_no_raise
    def _connect(self, value: bool, line_edit: QLineEdit):

        if line_edit.isModified():
            host_name = line_edit.text()
        else:
            host_name = line_edit.placeholderText()

        if value:
            self.g9ii.connect(host=host_name)
            # self.play_rec_mode_button.setEnabled(True)

        else:
            self.g9ii.disconnect()
            # self.play_rec_mode_button.setEnabled(False)

    @_no_raise
    def _find_camera(self, status: bool, line_edit: QLineEdit):
        try:
            camera_hostname = find_lumix_camera_via_sspd()
        except RuntimeError as e:
            traceback.print_exception(e)
            line_edit.setPlaceholderText("no camera found")
            line_edit.setText(None)
            self.connect_button.setDisabled(True)
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
                # self.status_widget.setText(pprint.pformat(event["data"]))
                # if event["data"]["cammode"] == "play":
                #     self.shutter_button.setEnabled(False)
                #     self.rec_button.setEnabled(False)
                #     self.livestream_button.setEnabled(False)
                # else:
                #     self.shutter_button.setEnabled(True)
                #     self.rec_button.setEnabled(True)
                #     self.livestream_button.setEnabled(True)

            elif event["type"] == "allmenu_etree":
                self.cameraAllmenuChanged.emit(event["data"])
                # self.record_settings_widget.apply_allmenu_xml(event["data"])

            elif event["type"] == "curmenu_etree":
                self.cameraCurmenuChanged.emit(event["data"])
                # self.record_settings_widget.apply_curmenu_xml(event["data"])

            elif event["type"] == "camera_event":
                self.cameraEvent.emit(event["data"])
                print(event)

        except Exception as e:
            logger.error("%s", traceback.format_exception(e))
