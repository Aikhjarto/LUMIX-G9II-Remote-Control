import argparse
import datetime
import io
import logging
import threading
import tkinter as tk
import traceback

import zmq
from PIL import Image, ImageDraw, ImageFont, ImageTk

from LumixG9IIRemoteControl.StreamReceiver import asyncio_main_thread_function

from .helpers import get_local_ip

logging.basicConfig()
logger = logging.getLogger()
logger.setLevel("DEBUG")


class StreamViewerWidget(tk.Frame):
    def __init__(self, master: tk.Tk = None):
        super().__init__(master)
        self.master = master
        master.minsize(width=640, height=480)
        master.title("StreamViewer")
        self.pack()

        self.text_label = tk.Label(master, text=datetime.datetime.now().isoformat())
        self.text_label.pack()

        # https://web.archive.org/web/20201111190625/http://effbot.org/pyfaq/why-do-my-tkinter-images-not-appear.htm
        # Refereces to image buffers must be held manually, as tk.Label does not do it
        self.image = Image.new("RGB", (640, 480), color="magenta")
        draw = ImageDraw.Draw(self.image)
        font = ImageFont.truetype("DejaVuSans.ttf", 23)
        draw.text(
            (320, 240),
            "Waiting for camera to send stream",
            (255, 255, 255),
            align="center",
            anchor="mm",
            font=font,
        )
        self.photo_image = ImageTk.PhotoImage(self.image)
        self.img_label = tk.Label(master, image=self.photo_image)
        self.img_label.pack()

        self.shutter_button = tk.Button(
            master, text="capture", command=self._capture_event
        )
        self.shutter_button.pack(side="right")

        self._zmq_context = zmq.Context()
        self._zmq_socket = self._zmq_context.socket(zmq.PAIR)
        self._zmq_socket.bind("tcp://*:5556")
        self._zmq_thd = threading.Thread(
            target=self._zmq_consumer_function, daemon=True
        )
        self._zmq_thd.start()

        # Note: Single button click always initiates drag
        self.img_label.bind("<ButtonPress-1>", self._on_button_press)
        self.img_label.bind("<B1-Motion>", self._on_drag)
        self.img_label.bind("<ButtonRelease-1>", self._on_button_release)

    def _on_button_press(self, event):
        x = max(0, min(1000, int(1000 * event.x / self.img_label.winfo_width())))
        y = max(0, min(1000, int(1000 * event.y / self.img_label.winfo_height())))
        self._last_button_press_coordinates = (x, y)
        self._drag_start_was_sent = False

    def _send_pyobj(self, obj):
        # like send_pyobj, but does not block when receiver is not present
        try:
            self._zmq_socket.send_pyobj(obj, zmq.NOBLOCK)
        except zmq.error.Again as e:
            pass

    def _zmq_consumer_function(self):
        while True:
            try:
                event = self._zmq_socket.recv_pyobj()
                logger.info('%s %s', event, event['data']['cammode'])
                print(dict(self.shutter_button))
                if event['type'] == "state_dict":                    
                    if event['data']['cammode'] == 'play':
                        if self.shutter_button['state'] == tk.NORMAL:
                            self.shutter_button['state'] = tk.DISABLED
                    else:
                        self.shutter_button['state'] = tk.NORMAL
            except Exception as e:
                logger.error(traceback.format_exception(e))


    def _capture_event(self):
        self._send_pyobj({"capture": "start"})

    def _on_drag(self, event):
        if not self._drag_start_was_sent:
            # send self._last_button_press_coordinates as drag start
            self._send_pyobj(
                {
                    "streamviewer_event": "drag_start",
                    "x": self._last_button_press_coordinates[0],
                    "y": self._last_button_press_coordinates[1],
                }
            )
            logger.debug(
                "Drag start: %s/%s",
                self._last_button_press_coordinates[0],
                self._last_button_press_coordinates[1],
            )
            self._drag_start_was_sent = True

        # send current drag position
        x = max(0, min(1000, int(1000 * event.x / self.img_label.winfo_width())))
        y = max(0, min(1000, int(1000 * event.y / self.img_label.winfo_height())))
        self._send_pyobj(
            {
                "streamviewer_event": "drag_continue",
                "x": x,
                "y": y,
            }
        )

        logger.debug("Drag current position: %s/%s", x, y)

    def _on_button_release(self, event):
        x = max(0, min(1000, int(1000 * event.x / self.img_label.winfo_width())))
        y = max(0, min(1000, int(1000 * event.y / self.img_label.winfo_height())))
        if self._drag_start_was_sent:
            # sent drag stop
            self._send_pyobj(
                {
                    "streamviewer_event": "drag_stop",
                    "x": x,
                    "y": y,
                }
            )
            logger.debug("Drag stop: %s/%s", x, y)
        else:
            self._send_pyobj(
                {
                    "streamviewer_event": "click",
                    "x": x,
                    "y": y,
                }
            )
            logger.debug("Click: %s/%s", x, y)

        self._drag_start_was_sent = False

    def update_stream_image(self, timestamp: datetime.datetime, image_data: bytes):
        iso_timestamp_string = timestamp.isoformat()
        self.text_label.configure(text=iso_timestamp_string)

        # don't remove reference to old image bevore setting new,
        # as it would result in flickerung
        img = Image.open(io.BytesIO(image_data))
        logging.debug(
            "Receive image of size %s bytes and %s pixels", len(image_data), img.size
        )
        aaa = ImageTk.PhotoImage(img)
        self.img_label.configure(image=aaa)
        self.photo_image = aaa


def run_blocking(port=49152):
    local_addr = (get_local_ip(), port)

    root = tk.Tk()

    # sampling terminal even when window is not in focus to catch CTRL+C
    def check():
        root.after(500, check)

    root.after(500, check)

    window = StreamViewerWidget(root)

    thd = threading.Thread(
        target=asyncio_main_thread_function,
        args=(
            local_addr,
            window.update_stream_image,
        ),
        daemon=True,
    )
    thd.start()

    window.mainloop()


def setup_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", "-p", type=int, default=49152)
    return parser


if __name__ == "__main__":
    args = setup_parser().parse_args()
    run_blocking(args.port)
