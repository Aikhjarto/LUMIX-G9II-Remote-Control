import logging

logging.basicConfig()

formatter = logging.Formatter(
    fmt="%(asctime)s.%(msecs)03d %(levelname)-8s :: %(message)s'",
    datefmt="%Y-%m-%d,%H:%M:%S",
)

fh = logging.FileHandler("LumixG9IIRemoteControl.log")
fh.setLevel(logging.INFO)
fh.setFormatter(formatter)


logger = logging.getLogger()
logger.addHandler(fh)
logger.setLevel(logging.INFO)
