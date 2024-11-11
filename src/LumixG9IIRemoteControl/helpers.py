import socket

from PIL import Image, ImageDraw, ImageFont, ImageTk


def get_local_ip() -> str:
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except socket.gaierror as e:
        # gethostbyname fails due to DNS error
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        
        # doesn't even have to be reachable
        s.connect(('10.254.254.254', 1))
        local_ip = s.getsockname()[0]
        
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
