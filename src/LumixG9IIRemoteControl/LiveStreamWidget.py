import asyncio
import datetime
import signal
import sys
from typing import Tuple

import PIL
import PIL.Image
import PIL.ImageQt
import qasync
from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import QTimer
from PyQt6.QtCore import pyqtSignal as Signal
from PyQt6.QtWidgets import QApplication, QLabel

from .helpers import get_local_ip, get_waiting_for_stream_image
from .StreamReceiver import async_asyncio_thread


class LiveStreamWidget(QLabel):

    drag_start = Signal(QtCore.QPoint, name="drag_start")
    drag = Signal(QtCore.QPoint, name="drag")
    drag_stop = Signal(QtCore.QPoint, name="drag_stop")
    click = Signal(QtCore.QPoint, name="click")

    def __init__(
        self,
    ):
        super().__init__()

        image = get_waiting_for_stream_image()
        image = PIL.ImageQt.ImageQt(image)
        self.image = image  # store handle, otherwise segfault

        pixmap = QtGui.QPixmap()
        pixmap.fromImage(self.image)
        self.setPixmap(QtGui.QPixmap.fromImage(image))

        self._last_button_press_coordinates: Tuple[int, int] = None

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
            self._drag_start_was_sent = True
        # print("drag", self._event_to_x_y(event))
        self.drag.emit(QtCore.QPoint(*self._event_to_x_y(event)))

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        event.accept()
        # print("release", event.position())
        if self._drag_start_was_sent:
            # sent drag stop
            # print("drag stop", self._event_to_x_y(event))
            self.drag_stop.emit(QtCore.QPoint(*self._event_to_x_y(event)))
        else:
            # print("click", self._event_to_x_y(event))
            self.click.emit(QtCore.QPoint(*self._event_to_x_y(event)))

    def update_image(self, timestamp: datetime.datetime, image_data: bytes):
        print(timestamp)
        pixmap = QtGui.QPixmap()
        pixmap.loadFromData(image_data)
        self.setPixmap(pixmap)


if __name__ == "__main__":

    def sigint_handler(*args, **kwargs):
        QApplication.quit()

    signal.signal(signal.SIGINT, sigint_handler)
    app = QApplication(sys.argv)
    event_loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(event_loop)

    mw = LiveStreamWidget()
    mw.show()
    timer = QTimer()
    timer.start(200)
    timer.timeout.connect(lambda: None)  # Let the interpreter run periodically

    event_loop.create_task(
        async_asyncio_thread((get_local_ip(), 49152), mw.update_image)
    )

    app_close_event = asyncio.Event()
    app.aboutToQuit.connect(app_close_event.set)
    with event_loop:
        event_loop.run_until_complete(app_close_event.wait())
