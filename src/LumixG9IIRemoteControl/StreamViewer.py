import argparse
import datetime
import io
import logging
import threading
import tkinter as tk

from PIL import Image, ImageDraw, ImageFont, ImageTk

from LumixG9IIRemoteControl.StreamReceiver import asyncio_main_thread_function

from .helpers import get_local_ip

logging.basicConfig()
logger = logging.getLogger()
logger.setLevel("INFO")


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

        # Note: Single button click always initiates drag
        self.img_label.bind("<ButtonPress-1>", self._on_button_press)
        self.img_label.bind("<B1-Motion>", self._on_drag)
        self.img_label.bind("<ButtonRelease-1>", self._on_button_release)

    def _on_button_press(self, event):
        self._last_button_press_coordinates = (event.x, event.y)
        self._drag_start_was_sent = False

    def _on_drag(self, event):
        if not self._drag_start_was_sent:
            # TODO: send self._last_button_press_coordinates as drag start
            logger.debug(
                "Drag start: %s/%s",
                self._last_button_press_coordinates[0],
                self._last_button_press_coordinates[1],
            )
            self._drag_start_was_sent = True

        # TODO: send current drag position
        logger.debug(
            "Drag current position: %s/%s",
            int(1000 * event.x / self.img_label.winfo_width()),
            int(1000 * event.y / self.img_label.winfo_height()),
        )

    def _on_button_release(self, event):
        if self._drag_start_was_sent:
            # TODO: sent drag stop
            logger.debug(
                "Drag stop: %s/%s",
                int(1000 * event.x / self.img_label.winfo_width()),
                int(1000 * event.y / self.img_label.winfo_height()),
            )
        else:
            # TODO send click
            logger.debug(
                "Click: %s/%s",
                int(1000 * event.x / self.img_label.winfo_width()),
                int(1000 * event.y / self.img_label.winfo_height()),
            )

        self._drag_start_was_sent = False

    def update_stream_image(self, timestamp: datetime.datetime, image_data: bytes):
        iso_timestamp_string = timestamp.isoformat()
        self.text_label.configure(text=iso_timestamp_string)

        # don't remove reference to old image bevore setting new,
        # as it would result in flickerung
        img = Image.open(io.BytesIO(image_data))
        logging.debug(
            "Receive image of size %s bytes and %s pixels", image_data, img.size
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
