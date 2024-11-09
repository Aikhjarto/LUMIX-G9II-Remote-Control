import argparse
import asyncio
import datetime
import io
import logging
import subprocess
import traceback
from typing import Any, Callable, Tuple

from PIL import Image

from .helpers import get_local_ip

logging.basicConfig()
logger = logging.getLogger()
logger.setLevel("INFO")


class ClientProtocol(asyncio.DatagramProtocol):
    def __init__(
        self,
        on_con_lost: asyncio.Future[Any],
        callback: Callable[[datetime.datetime, bytes], None],
    ):
        self.on_con_lost = on_con_lost
        self.callback = callback
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr):
        logger.info("Received from %s, %d", addr, len(data))
        # search for JPG or JFIF header
        start_idx = data.find(b"\xFF\xD8\xFF")
        if start_idx < 0:
            logger.error("Could not find JPG/JFIF header in received data")
            return
        else:
            try:
                self.callback(datetime.datetime.now(), data[start_idx:])

            except Exception as e:
                traceback.print_exception(e)

    def error_received(self, exc):
        print("Error received:", exc)

    def connection_lost(self, exc):
        print("Connection closed")
        self.on_con_lost.set_result(True)


async def async_asyncio_thread(
    local_addr: Tuple[str, int],
    callback: Callable[[datetime.datetime, bytes], None],
):
    logger.info("Waiting for start of stream on %s", local_addr)
    asyncio_loop = asyncio.get_running_loop()
    on_con_lost = asyncio_loop.create_future()
    transport, protocol = await asyncio_loop.create_datagram_endpoint(
        lambda: ClientProtocol(on_con_lost, callback), local_addr=local_addr
    )

    try:
        await on_con_lost
    finally:
        transport.close()


def asyncio_main_thread_function(*args, **kwargs):
    """A blocking non-asyncio function that schedules receiving events"""
    asyncio.run(async_asyncio_thread(*args, **kwargs))


def dummy_consumer(timestamp: datetime.datetime, image_data: bytes):
    image = Image.open(io.BytesIO(image_data))
    print(f"{timestamp.isoformat()}: {image.size}")


def write_jpgs_consumer(timestamp: datetime.datetime, image_data: bytes):
    with open(f"{timestamp.timestamp():0.6f}.jpg", "wb") as f:
        f.write(image_data)


class FFMpegWriter:
    def __init__(self):

        self.process = subprocess.Popen(
            [
                "/usr/bin/ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-f",
                "image2pipe",
                "-s",
                "640x480",
                "-r",
                "30",
                "-i",
                "pipe:0",
                "-video_size",
                "640x480",
                "-c:v",
                "libx264",
                "-an",
                f"{datetime.datetime.now().timestamp():0.9f}.mp4",
            ],
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def __call__(self, timestamp: datetime.datetime, image_data: bytes):
        self.process.stdin.write(image_data)


def setup_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", choices=["dummy", "jpgs", "video"])
    parser.add_argument("--port", "-p", type=int, default=49152)
    return parser


if __name__ == "__main__":
    args = setup_parser().parse_args()
    local_addr = (get_local_ip(), args.port)

    if args.destination == "dummy":
        asyncio_main_thread_function(local_addr, callback=dummy_consumer)
    elif args.destination == "jpgs":
        asyncio_main_thread_function(local_addr, callback=write_jpgs_consumer)
    elif args.destination == "video":
        asyncio_main_thread_function(local_addr, callback=FFMpegWriter())
