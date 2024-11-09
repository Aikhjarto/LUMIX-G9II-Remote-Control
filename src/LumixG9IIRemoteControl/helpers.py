import socket

from PIL import Image, ImageDraw, ImageFont, ImageTk


def get_local_ip() -> str:
    local_ip = socket.gethostbyname(socket.gethostname())
    if local_ip.startswith("127."):
        local_ip = socket.gethostbyname(socket.getfqdn())
        if local_ip.startswith("127."):
            raise "cannot determine ip"
    return local_ip


def get_waiting_for_stream_image() -> Image:
    image = Image.new("RGB", (640, 480), color="magenta")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("DejaVuSans.ttf", 23)
    draw.text(
        (320, 240),
        "Waiting for camera to send stream",
        (255, 255, 255),
        align="center",
        anchor="mm",
        font=font,
    )
    return image
