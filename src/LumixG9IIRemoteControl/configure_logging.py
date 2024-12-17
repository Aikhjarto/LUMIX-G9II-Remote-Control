import logging
import os
import time

logging.basicConfig()

formatter = logging.Formatter(
    fmt="%(asctime)s.%(msecs)03d %(levelname)-8s :: %(message)s'",
    datefmt="%Y-%m-%d,%H:%M:%S",
)

logfilename = f"LumixG9IIRemoteControl{int(time.time())}.log"
if os.path.islink("LumixG9IIRemoteControl.log"):
    os.unlink("LumixG9IIRemoteControl.log")
os.symlink(logfilename, "LumixG9IIRemoteControl.log")

fh = logging.FileHandler(logfilename)
fh.setLevel(logging.INFO)
fh.setFormatter(formatter)


logger = logging.getLogger()
logger.addHandler(fh)
logger.setLevel(logging.INFO)
