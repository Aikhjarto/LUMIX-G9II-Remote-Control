import threading
import traceback

import bleak
import zmq
from qtpy import QtCore, QtGui
from qtpy.QtCore import Signal, Slot
from qtpy.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import LumixG9IIRemoteControl.LumixG9IIBluetoothControl

from ..configure_logging import logger
from ..QtGUI.NoRaise import NoRaiseMixin


class ZMQReceiver(QtCore.QObject):
    dataChanged = Signal(object)

    def start(self):
        threading.Thread(target=self._execute, daemon=True).start()

    def _execute(self):
        context = zmq.Context()
        consumer_receiver = context.socket(zmq.PAIR)
        consumer_receiver.bind("tcp://*:5558")
        while True:
            obj = consumer_receiver.recv_pyobj()
            self.dataChanged.emit(obj)


class CameraBluetoothControlWidget(QWidget, NoRaiseMixin):

    cameraBluetoothNotification = Signal(object)
    cameraBluetoothConnected = Signal()
    cameraBluetoothDisconnected = Signal()
    cameraConnectionStateChanged = Signal(bool)

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.error_message = QMessageBox()

        self.g9bt = (
            LumixG9IIRemoteControl.LumixG9IIBluetoothControl.LumixG9IIBluetoothControl(
                auto_connect=True,
                notification_callback=self._bluetooth_notification_emitter,
            )
        )

        lv = QVBoxLayout()
        self.bluetooth_connection_status_label = QLabel("Waiting for Bluetooth")
        lv.addWidget(self.bluetooth_connection_status_label)

        self.capture_button = QPushButton("Capture")
        self.capture_button.setDisabled(True)
        self.capture_button.pressed.connect(self.capture)
        lv.addWidget(self.capture_button)

        self.toggle_video_button = QPushButton("Toggle Video Rec.")
        self.toggle_video_button.setDisabled(True)
        self.toggle_video_button.pressed.connect(self.toggle_video)
        lv.addWidget(self.toggle_video_button)

        self.send_gps_postion_button = QPushButton("Send GPS")
        self.send_gps_postion_button.setDisabled(True)
        self.send_gps_postion_button.setCheckable(True)
        self.send_gps_postion_button.pressed.connect(
            self._send_gps_position_button_pressed
        )
        lv.addWidget(self.send_gps_postion_button)

        # start an accesspoint
        self.start_accesspoint_button = QPushButton("Start Accesspoint")
        self.start_accesspoint_button.setDisabled(True)
        self.start_accesspoint_button.pressed.connect(self._start_accesspoint)
        lv.addWidget(self.start_accesspoint_button)

        # connect to an accesspoint
        self.essid = QLineEdit()
        self.essid.setPlaceholderText("ESSID")
        self.connect_to_accesspoint_button = QPushButton("Connect Accesspoint")
        self.connect_to_accesspoint_button.setDisabled(True)
        self.connect_to_accesspoint_button.pressed.connect(self._connect_to_accesspoint)
        lh = QHBoxLayout()
        lh.addWidget(self.essid)
        lh.addWidget(self.connect_to_accesspoint_button)
        lv.addLayout(lh)

        self.setLayout(lv)

        zmq_receiver = ZMQReceiver(self)
        zmq_receiver.dataChanged.connect(self._zmq_consumer_function)
        zmq_receiver.start()

    def _no_raise(func):
        def no_raise(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.exception(e)
                args[0].error_message.critical(
                    args[0],
                    "G9II Error",
                    "\n".join(traceback.format_exception_only(e)),
                )

        return no_raise

    @Slot(object)
    def _zmq_consumer_function(self, event):
        logger.info(event)
        try:
            self.bluetooth_connection_status_label.setText(str(self.g9bt))
            if event["type"] == "connection_status":
                is_logged_in = event["data"] == "logged_in"
                if is_logged_in:
                    self.cameraBluetoothConnected.emit()
                else:
                    self.cameraBluetoothDisconnected.emit()

                self.capture_button.setEnabled(is_logged_in)
                self.toggle_video_button.setEnabled(is_logged_in)
                self.send_gps_postion_button.setEnabled(is_logged_in)
                self.start_accesspoint_button.setEnabled(is_logged_in)
                self.connect_to_accesspoint_button.setEnabled(is_logged_in)
                self.cameraConnectionStateChanged.emit(bool(event["data"]))
            else:
                logger.error("Unknown message, %s", event)

        except Exception as e:
            logger.exception(e)

    @_no_raise
    def _connect_to_accesspoint(self):
        self.g9bt.connect_to_accesspoint(str(self.essid.text()))

    @_no_raise
    def _start_accesspoint(self):
        self.g9bt.activate_accesspoint()

    def _bluetooth_notification_emitter(
        self, characteristic: bleak.BleakGATTCharacteristic, data: bytearray
    ):
        self.bluetooth_connection_status_label.setText(str(self.g9bt))
        self.cameraBluetoothNotification.emit((characteristic, data))

    @_no_raise
    def capture(self):
        self.g9bt.capture()

    @_no_raise
    def toggle_video(self):
        self.g9bt.toggle_video()

    @_no_raise
    def _send_gps_position_button_pressed(self):
        self.g9bt.send_gps_data = self.send_gps_postion_button.isChecked()
