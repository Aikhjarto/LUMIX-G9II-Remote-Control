import datetime
import logging
import signal
import sys
from typing import Tuple

import PIL
import PIL.Image
import PIL.ImageQt
from qtpy import QtCore, QtGui, QtNetwork
from qtpy.QtCore import QTimer, Signal, Slot
from qtpy.QtWidgets import QApplication, QLabel

from ..helpers import get_waiting_for_stream_image

logging.basicConfig()
logger = logging.getLogger()


class LiveStreamWidget(QLabel):

    drag_start = Signal(QtCore.QPoint, name="drag_start")
    drag = Signal(QtCore.QPoint, name="drag")
    drag_stop = Signal(QtCore.QPoint, name="drag_stop")
    click = Signal(QtCore.QPoint, name="click")
    cameraCommandRequest = Signal(dict)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        image = get_waiting_for_stream_image()
        image = PIL.ImageQt.ImageQt(image)
        self.image = image  # store handle, otherwise segfault

        # pixmap = QtGui.QPixmap()
        # pixmap.fromImage(self.image)
        self.setPixmap(QtGui.QPixmap.fromImage(image))

        self._last_button_press_coordinates: Tuple[int, int] = None

        self.udp_thread = QtCore.QThread(self)
        self.udp_socket = QtNetwork.QUdpSocket(self)
        self.udp_socket.bind(QtNetwork.QHostAddress.Any, 49152)
        self.udp_socket.readyRead.connect(self.readPendingDatagrams)

    @Slot()
    def readPendingDatagrams(self):
        while self.udp_socket.hasPendingDatagrams():
            (data, sender, senderPort) = self.udp_socket.readDatagram(
                self.udp_socket.pendingDatagramSize()
            )
            self.update_image(datetime.datetime.now(), bytes(data))

    def _event_to_x_y(self, event: QtGui.QMouseEvent):
        x = max(0, min(1000, int(1000 * event.position().x() / self.width())))
        y = max(0, min(1000, int(1000 * event.position().y() / self.height())))
        return x, y

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        event.accept()
        # print('press', event.position())
        self._last_button_press_coordinates = self._event_to_x_y(event)
        self._drag_start_was_sent = False

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        event.accept()
        # print('move', event.position())
        if not self._drag_start_was_sent:
            # print("drag start", self._last_button_press_coordinates)
            self.drag_start.emit(QtCore.QPoint(*self._last_button_press_coordinates))
            self.cameraCommandRequest.emit(
                {
                    "function": "send_touch_drag",
                    "args": ("start", *self._last_button_press_coordinates),
                }
            )
            self._drag_start_was_sent = True
        # print("drag", self._event_to_x_y(event))
        self.drag.emit(QtCore.QPoint(*self._event_to_x_y(event)))

        self.cameraCommandRequest.emit(
            {
                "function": "send_touch_drag",
                "args": ("continue", *self._event_to_x_y(event)),
            }
        )

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        event.accept()
        # print("release", event.position())
        if self._drag_start_was_sent:
            # sent drag stop
            # print("drag stop", self._event_to_x_y(event))
            self.drag_stop.emit(QtCore.QPoint(*self._event_to_x_y(event)))
            self.cameraCommandRequest.emit(
                {
                    "function": "send_touch_drag",
                    "args": ("stop", *self._event_to_x_y(event)),
                }
            )
        else:
            # print("click", self._event_to_x_y(event))
            self.click.emit(QtCore.QPoint(*self._event_to_x_y(event)))

            self.cameraCommandRequest.emit(
                {"function": "send_touch_coordinate", "args": self._event_to_x_y(event)}
            )

    def update_image(self, timestamp: datetime.datetime, data: bytes):
        start_idx = data.find(b"\xFF\xD8\xFF")
        if start_idx < 0:
            logger.error("Could not find JPG/JFIF header in received data")
            return
        image_data = data[start_idx:]
        logger.debug("received livestream frame of size %d bytes", len(image_data))
        pixmap = QtGui.QPixmap()
        pixmap.loadFromData(image_data)
        self.setPixmap(pixmap)


if __name__ == "__main__":

    def sigint_handler(*args, **kwargs):
        QApplication.quit()

    signal.signal(signal.SIGINT, sigint_handler)
    app = QApplication(sys.argv)

    mw = LiveStreamWidget()
    mw.show()
    timer = QTimer()
    timer.start(200)
    timer.timeout.connect(lambda: None)  # Let the interpreter run periodically

    app.exec()
