import asyncio
import logging
import os
import pprint
import re
import struct
import time
import traceback
from typing import Dict, List, Tuple

import bleak
import bleak.backends
import bleak.backends.device
import bleak.backends.service
from bleak import BleakClient, BleakScanner, BLEDevice
from bleak.uuids import normalize_uuid_16, uuid16_dict
from typing_extensions import Buffer

logging.basicConfig()

formatter = logging.Formatter(
    fmt="%(asctime)s.%(msecs)03d %(levelname)-8s :: %(message)s",
    datefmt="%Y-%m-%d,%H:%M:%S",
)

logfilename = f"btlog_{int(time.time())}.log"
if os.path.islink("btlog.log"):
    os.unlink("btlog.log")
os.symlink(logfilename, "btlog.log")

fh = logging.FileHandler(logfilename)
fh.setLevel(logging.INFO)
fh.setFormatter(formatter)


logger = logging.getLogger()
logger.addHandler(fh)
logger.setLevel(logging.INFO)


def detection_callback(
    device: bleak.BLEDevice, advertisement_data: bleak.AdvertisementData
):
    logger.info("%s: %r", device.address, advertisement_data)
    pass


def device_filter(device: bleak.BLEDevice, advertisement_data: bleak.AdvertisementData):
    if advertisement_data and advertisement_data.local_name:
        if advertisement_data.local_name.startswith("G9M2"):
            logger.info("Device Filter %s: %r", device.address, advertisement_data)
            return True


def notification_handler(
    characteristic: bleak.BleakGATTCharacteristic, data: bytearray
):
    """Simple notification handler which prints the data received."""
    logger.info("Notification %s: %r", characteristic, data)


disconnected_event = asyncio.Event()


def hash_lumix_lab(value_7a_bytes: bytes) -> Tuple[bytearray, bytearray]:
    format = ">I"
    value_7a_int = struct.unpack(format, value_7a_bytes)[0]

    value_72 = bytearray(20)
    for i, x in enumerate(["831f7010", "4ecc7098", "b82b81f0", "aff90f2a", "ffffff88"]):
        value_72[i * 4 : (i + 4) * 4] = struct.pack(format, value_7a_int ^ int(x, 16))

    value_74 = bytearray(8)
    for i, x in enumerate(["35504603", "ffffff00"]):
        value_74[i * 4 : (i + 4) * 4] = struct.pack(format, value_7a_int ^ int(x, 16))

    logger.debug("0x" + "".join([f"{x:02x}" for x in value_72]))
    logger.debug("0x" + "".join([f"{x:02x}" for x in value_74]))

    return value_72, value_74


def hash_lumix_sync(value_2a_bytes: bytes) -> Tuple[bytearray, bytearray]:
    """
    Takes value of GATT handle 0x002a and calculates the result of the challenge response
    to be written to GATT handles 0x002c and 0x002e
    """

    assert len(value_2a_bytes) == 4

    format = ">I"
    value_2a_int = struct.unpack(format, value_2a_bytes)[0]

    val_2c = bytearray(20)
    for i, x in enumerate(["49454d10", "10000130", "02018000", "450200a0", "ffffff18"]):
        val_2c[i * 4 : (i + 4) * 4] = struct.pack(format, value_2a_int ^ int(x, 16))

    val_2e = bytearray(20)
    for i, x in enumerate(["35504603", "00000000", "00000000", "00000000", "ffffff00"]):
        val_2e[i * 4 : (i + 4) * 4] = struct.pack(format, value_2a_int ^ int(x, 16))

    logger.debug("0x" + "".join([f"{x:02x}" for x in val_2c]))
    logger.debug("0x" + "".join([f"{x:02x}" for x in val_2e]))
    return val_2c, val_2e


class LumixG9IIBluetoothControl:

    def __init__(self, auto_connect=False):
        self._device: bleak.backends.device.BLEDevice = None
        self._client: BleakClient = None
        self._service_collection: bleak.backends.service.BleakGATTServiceCollection = (
            None
        )
        self.auto_connect = auto_connect
        # if auto_connect:
        #     asyncio.create_task(self.autoconnect())

    async def autoconnect(self):
        while True:
            try:
                await self.find_device()
                await self.connect()
                await disconnected_event.wait()
            except bleak.BleakError as e:
                logger.exception(e)

    async def find_device(self, timeout=30):

        self._device = await BleakScanner.find_device_by_filter(
            device_filter, timeout=timeout, detection_callback=detection_callback
        )
        if self._device is None:
            logger.error("could not find device")
            raise RuntimeError("could not find device")
        else:
            logger.info("Found device %r", self._device)

    def disconnected_callback(self, client):
        logger.info("Disconnected callback called!")
        # delete handles which are only valid during a connection
        self._device = None
        self._service_collection = None
        disconnected_event.set()

    async def connect(
        self, connect_timeout=20, service_discovery_timeout=30, as_lumix_sync=False
    ):

        self._service_collection: bleak.backends.service.BleakGATTServiceCollection = (
            None
        )
        while not self._service_collection:
            if not self._device:
                await self.find_device()

            self._client = BleakClient(
                self._device,
                disconnected_callback=self.disconnected_callback,
                timeout=connect_timeout,
            )
            logger.info("Connecting to device %s", self._device)
            await self._client.disconnect()
            try:
                await self._client.connect()
            except bleak.exc.BleakDeviceNotFoundError:
                self._device = None
                continue
            except bleak.exc.BleakError as e:
                logger.exception(e)
                logger.error("e.args: %s", e.args)
                if re.match("^device (.*) not found$", e.args[0]):
                    self._device = None
                continue
            except TimeoutError:
                continue

            logger.info(
                "Connected %s, %r. Wait for up to %s seconds for service collection to be populated.",
                self._client.is_connected,
                self._client,
                service_discovery_timeout,
            )

            # wait for service collection to be populated
            time_start = time.time()
            while (
                self._client.is_connected
                and not self._service_collection
                and time.time() - time_start < service_discovery_timeout
            ):
                time.sleep(1)
                try:
                    self._service_collection: bleak.BleakGATTServiceCollection = (
                        self._client.services
                    )
                except (
                    bleak.BleakError,
                    asyncio.exceptions.CancelledError,
                    TimeoutError,
                    TypeError,
                ) as e:
                    logger.exception(e)
                    if not self._client.is_connected:
                        raise RuntimeError

        logger.info("Connected %s, %r", self._client.is_connected, self._client)

        readable_characteristics = []
        notify_characteristics = []
        writable_characteristics = []
        indicate_characteristics = []
        for key, characteristic in self._service_collection.characteristics.items():
            characteristic: bleak.BleakGATTCharacteristic
            logger.debug(
                "Characteristic %s",
                pprint.pformat(
                    {
                        "handle_int": characteristic.handle,
                        "handle_hex": f"0x{characteristic.handle:04x}",
                        "descriptors": characteristic.descriptors,
                        "description": characteristic.description,
                        "service_uuid": characteristic.service_uuid,
                        "uuid": characteristic.uuid,
                        "properties": characteristic.properties,
                    }
                ),
            )

            if "read" in characteristic.properties:
                readable_characteristics.append(characteristic)

            if "notify" in characteristic.properties:
                notify_characteristics.append(characteristic)

            if "write" in characteristic.properties:
                writable_characteristics.append(characteristic)

            if "indicate" in characteristic.properties:
                indicate_characteristics.append(characteristic)

        # setup notifications
        for idx, characteristic in enumerate(notify_characteristics):
            if characteristic.handle in (0x039, 0x003F, 0x045, 0x069):
                # some services are announces by the camera, but they cannot be connected to
                logger.info(
                    f"Notification {idx}/{len(notify_characteristics)-1} skipped for {characteristic}"
                )
                continue
            try:
                await self._client.start_notify(characteristic, notification_handler)
                logger.info(
                    f"Notification {idx}/{len(notify_characteristics)-1} started for {characteristic}"
                )
            except Exception as e:
                logger.exception(
                    f"{idx}/{len(notify_characteristics)-1} notify: {e} for {characteristic}"
                )

        # login
        if as_lumix_sync:
            ret = await self.read_list([0x002A])
            ret_int = struct.unpack("I", ret[0x002A])[0]
            logger.info(f"0x{ret_int:08x}")

            value2c, value2e = hash_lumix_sync(ret[0x002A])
            logger.info(
                "Calculated value for 0x002C 0x"
                + "".join([f"{x:02x}" for x in value2c])
            )
            logger.info(
                "Calculated value for 0x002E 0x"
                + "".join([f"{x:02x}" for x in value2e])
            )

            lumix_sync_write = [
                (0x002C, value2c),
                (0x002E, value2e),
            ]
            await self.write_list(lumix_sync_write)

            ret = await self.read_list([0x0036])

            ret = await self.read_list([0x0038])

        else:
            ret = await self.read_list([0x007A])
            ret_int = struct.unpack("I", ret[0x007A])[0]
            logger.debug(f"0x007A: 0x{ret_int:08x}")

            value72, value74 = hash_lumix_lab(ret[0x007A])
            logger.debug(
                "Calculated value for 0x0072 0x"
                + "".join([f"{x:02x}" for x in value72])
            )
            logger.debug(
                "Calculated value for 0x0074 0x"
                + "".join([f"{x:02x}" for x in value74])
            )

            ret = await self.write_list([(0x0072, value72)], response=False)
            ret = await self.write_list(
                [(0x0070, b"LUMIX LUT Creators APP 1.2.1\0\0\0\0")], response=False
            )
            ret = await self.write_list([(0x0074, value74)], response=False)

            # Notifications 8c, 88, and 9c come here with values 1,2, and 1

            ret = await self.camera_name()

            # Notification 0x0046 with value 0x01

            ret = await self.read_list([0x0078])
            # 14 times value of 0x007A

    async def read_list(self, lst: List[int]) -> Dict[int, bytearray]:
        if self.auto_connect and (
            (not self._client) or (not self._client.is_connected)
        ):
            await self.connect()
        d = dict()
        for i in lst:
            char = self._service_collection.characteristics[i - 1]
            d[i] = await self._client.read_gatt_char(char)
            logger.info("Read %s", d)
        return d

    async def wifi5GHz(self, status: bool):
        if status:
            value = b"\x02"
        else:
            value = b"\x01"
        self.write_list([0x00A0, value], response=False)

    async def write_list(
        self, lst: List[Tuple[int, Buffer]], response: bool = True
    ) -> Dict[int, bytearray]:
        if self.auto_connect and (
            (not self._client) or (not self._client.is_connected)
        ):
            await self.connect()
        d = dict()
        for i, data in lst:
            char = self._service_collection.characteristics[i - 1]
            logger.info("Write %s %s", i, data)
            d[i] = await self._client.write_gatt_char(char, data, response=response)
            logger.info("Write Response %s", d)
        return d

    async def capture(self):
        lumix_sync_write = [
            (0x0068, b"\x01"),
            (0x0068, b"\x02"),
            (0x0068, b"\x04"),
            (0x0068, b"\x05"),
        ]
        # TODO number of 0x04 and 0x05 sent depends on how long
        # camera needs to focus.
        # 0x04 is shutter press
        # 0x05 is shutter release

        await self.write_list(lumix_sync_write)

    async def read_TODO(self):
        return await self.read_list(
            (0x0078, 0x096, 0x009A, 0x009E, 0x00A4, 0x00A8, 0x00AA)
        )

    async def shutter_press(self):
        await self.write_list([(0x0068, b"\x04")])

    async def shutter_release(self):
        await self.write_list([(0x0068, b"\x05")])

    async def toggle_video(self):

        lumix_sync_write_toggle_record = [
            (0x0068, b"\x06"),
            (0x0068, b"\x07"),
        ]
        await self.write_list(lumix_sync_write_toggle_record)

    async def start_wifi(self):
        await self.write_list(
            [
                (0x004A, 0x01),
            ]
        )
        # write 0x01 to 0x004a maybe connects to wifi

    async def camera_name(self):
        # e.g. G9M2-E77E48
        ret = await self.read_list(
            [
                0x0076,
            ]
        )
        return decode_nullterminated_bytes(ret[0x0076])

    async def get_camera_model(self):
        # e.g DC-G9M2
        ret = await self.read_list(
            [
                0x0094,
            ]
        )
        return decode_nullterminated_bytes(ret[0x0096])

    async def get_0x078(self):
        ret = await self.read_list(
            [
                0x0078,
            ]
        )
        return ret

    async def get_0x09a(self):
        # b'5376\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        ret = await self.read_list(
            [
                0x009A,
            ]
        )
        return ret

    async def get_0x09e(self):
        # b'\x02\x00\x00\x00\x00\x00\x00\x00'
        ret = await self.read_list(
            [
                0x009E,
            ]
        )
        return ret

    async def get_0x0a4(self):
        # b'73:07:C8:E6:C1:32:C2:01:56:8C:51:E0:A6:DA:58:D8:F2:F2:4C:53:21:67:4B:C9:0C:A6:24:87:5D:CF:A2:11'
        ret = await self.read_list(
            [
                0x00A4,
            ]
        )
        return ret

    async def get_0x0aa(self):
        # b'\x02\x00\x00\x00\x00\x00\x00\x00'
        ret = await self.read_list(
            [
                0x00AA,
            ]
        )
        return ret

    async def get_0x0a8(self):
        # b'\x02\x00\x00\x00\x00\x00\x00\x00'
        ret = await self.read_list(
            [
                0x00A8,
            ]
        )
        return ret

    async def get_0x096(self):
        # e.g 2.26
        ret = await self.read_list(
            [
                0x0096,
            ]
        )
        return decode_nullterminated_bytes(ret[0x0096])

    async def get_lens(self):
        ret = await self.read_list(
            [
                0x0098,
            ]
        )
        return decode_nullterminated_bytes(ret[0x0098])

    async def memory_card_status(self):
        # returns 'SD1,1,SD2,0,SSD,0'
        ret = await self.read_list(
            [
                0x0086,
            ]
        )
        return decode_nullterminated_bytes(ret[0x0086])

    async def auto_clock_sync(self, status):
        raise NotImplementedError
        self.write_list([0x0090, 0xE8070C1009361B003C00])
        # 7-th of 10 bytes change

        # notification 92 and 46 with value 1 come here

        # every four seconds write to 0x008a values like
        0x58BB8A54_3FD4D11C_72EF9508_7C014100
        0x5CBB8A54_3FD4D11C_71EF9508_7C014100
        0x60BB8A54_3FD4D11C_71EF9508_7C014100
        0x66BB8A54_41D4D11C_76EF9508_7C014100
        0x6ABB8A54_41D4D11C_76EF9508_7C014100
        0x01BD8A54_89DBD11C_11F69508_B1014100
        0x0FBD8A54_29D4D11C_E8F49508_9A014100
        0x14BD8A54_58D4D11C_CBF49508_98014100
        0x15BD8A54_54D4D11C_CFF49508_98014100


def decode_nullterminated_bytes(data: bytes):
    return data.decode().split("\0")[0]


if __name__ == "__main__":
    import IPython
    from traitlets.config import Config

    # from traitlets.config.application import Application
    # Application.instance().shell.enable_gui('asyncio')
    # loop = asyncio.get_event_loop()

    c = Config()
    c.InteractiveShellApp.exec_lines = [
        "from LumixG9IIRemoteControl.LumixG9IIBluetoothControl import LumixG9IIBluetoothControl",
        "g9 = LumixG9IIBluetoothControl(auto_connect = True)",
    ]
    c.InteractiveShellApp.hide_initial_ns = False
    IPython.start_ipython(argv=[], local_ns=locals(), config=c)
