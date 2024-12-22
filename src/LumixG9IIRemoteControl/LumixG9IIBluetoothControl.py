import asyncio
import logging
import os
import pprint
import re
import struct
import sys
import threading
import time
import traceback
from typing import Dict, List, Literal, Tuple

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


logger = logging.getLogger(__name__)
logger.addHandler(fh)
logger.setLevel(logging.INFO)


def detection_callback(
    device: bleak.BLEDevice, advertisement_data: bleak.AdvertisementData
):
    logger.debug("%s: %r", device.address, advertisement_data)


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

    def __init__(self, auto_connect=False, send_gps_data=False):
        self._device: bleak.backends.device.BLEDevice = None
        self._client: BleakClient = None
        self._service_collection: bleak.backends.service.BleakGATTServiceCollection = (
            None
        )
        self._logged_in: bool = False

        self.gps_packet_header = 0x5486AF20

        self.auto_connect = auto_connect
        # TODO: run self.connect in background
        self._connect_lock = threading.Lock()
        self._loop_lock = threading.Lock()
        self._loop = asyncio.new_event_loop()

        self._send_gps_data = send_gps_data

        # if self.auto_connect:
        # try:
        #     self._loop = asyncio.get_running_loop()
        # except RuntimeError:
        #     self._loop = asyncio.new_event_loop()
        # self._task = self._loop.create_task(self.autoconnect_periodic_coroutine())
        # asyncio.to_thread(self._task)
        # if auto_connect:
        self._auto_connect_thread_handle = threading.Thread(
            target=self._autoconnect_thread_function, daemon=True
        )
        self._auto_connect_thread_handle.start()

        self._gps_thread_handle = threading.Thread(
            target=self.gps_thread_function, daemon=True
        )
        self._gps_thread_handle.start()

        # self.autoconnect_task = asyncio.create_task(self.autoconnect_periodic_coroutine())

    async def autoconnect_periodic_coroutine(self):
        while True:
            await self.connect()
            await asyncio.sleep(2)

    def gps_thread_function(self):
        if hasattr(sys, "getandroidapilevel"):
            # we are on android, so start GPS
            import android

            droid = android.Android()
            droid.startLocating()

            last_time = time.time()
            while True:
                event = droid.eventWaitFor("location", 10000)
                try:
                    provider = event.result["data"]["gps"]["provider"]
                    if provider == "gps":
                        lat = str(event["data"]["gps"]["latitude"])
                        lon = str(event["data"]["gps"]["longitude"])
                        logger.debug("lat: %s lng: %s", lat, lon)
                        self.ensure_connected()
                        self._loop.run_forever(self.send_gps_location(lat, lon))
                        time.sleep(max(0, (5 - time.time() - last_time)))
                        last_time = time.time()
                    else:
                        continue
                except KeyError as e:
                    logger.exception(e)

        else:
            # location via IP adress
            import geocoder
            import geocoder.api

            last_time = time.time()
            while True:
                if self._logged_in and self._send_gps_data:
                    try:
                        a = geocoder.arcgis("me")
                        location = geocoder.api.location(a)
                        logger.debug(
                            "lat: %s lng: %s", location.latitude, location.longitude
                        )
                        with self._loop_lock:
                            self._loop.run_until_complete(
                                self.send_gps_location(
                                    location.latitude, location.longitude
                                )
                            )
                    except Exception as e:
                        logger.error(
                            "Geocoder could not get location, but got %s", location
                        )
                        logger.exception(e)

                time.sleep(max(0, (10 - (time.time() - last_time))))
                last_time = time.time()

    def _autoconnect_thread_function(self):

        while True:
            try:
                self.ensure_connected()
                # self._loop.run_until_complete(self.connect())
                # if not self._service_collection:
                # asyncio.run_coroutine_threadsafe(self.connect(), self._loop)
                # with self._loop_lock:
                # self._loop.run_until_complete(self.connect())
                # asyncio.Task(self.connect())
                # try:
                #     self._loop = asyncio.get_running_loop()
                # except RuntimeError:
                #     self._loop = asyncio.new_event_loop()
                # # asyncio.Task(self.connect())
                # task = self._loop.create_task(self.connect())
                # self._loop.run_until_complete(task)
                # loop.call_soon_threadsafe(self.connect())
                # self._future = asyncio.run_coroutine_threadsafe(self.connect(), self._loop)
                # logger.info('%s', self._future.result())
                # asyncio.run(self.connect())
                # del loop
                time.sleep(10)
                # TODO: better than polling every 10 seconds would be using the disconnect callback
                # loop.call_later(disconnected_event.wait())
                # loop.run_in_executor
            except Exception as e:
                logger.exception(e)

    async def _send_gps_location_task(self):
        if hasattr(sys, "getandroidapilevel"):
            # we are on android, so start GPS
            import android

            droid = android.Android()
            droid.startLocating()

            last_time = time.time()
            while True:
                event = droid.eventWaitFor("location", 10000)
                try:
                    provider = event.result["data"]["gps"]["provider"]
                    if provider == "gps":
                        lat = str(event["data"]["gps"]["latitude"])
                        lon = str(event["data"]["gps"]["longitude"])
                        logger.debug("lat: %s lng: %s", lat, lon)
                        await self.send_gps_location(lat, lon)
                        await asyncio.sleep(max(0, (5 - time.time() - last_time)))
                        last_time = time.time()
                    else:
                        continue
                except KeyError as e:
                    logger.exception(e)

        else:
            # location via IP adress
            import geocoder

            last_time = time.time()
            while True:
                try:
                    location = geocoder.ip("me")
                    lat, lon = location.latlng
                    logger.debug("lat: %s lng: %s", lat, lon)
                    await self.send_gps_location(lat, lon)
                    await asyncio.sleep(max(0, (5 - time.time() - last_time)))
                    last_time = time.time()
                except Exception as e:
                    logger.exception(e)

    async def find_device(self, timeout=30):

        logger.info("Searching for Bluetooth devices %s", device_filter)
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
        self._logged_in = False
        self._device = None
        self._client = None
        self._service_collection = None
        for task in asyncio.all_tasks(self._loop):
            task.cancel()
        # TODO stop futures too to avoid 'RuntimeError: Event loop stopped before Future completed.'
        self._loop.stop()

        disconnected_event.set()

    def ensure_connected(self, **kwargs):
        logger.debug("ensure_connected")
        if not self._service_collection:
            with self._loop_lock:
                self._loop.run_until_complete(self.connect(**kwargs))

    @property
    def is_connected(self):
        return bool(self._service_collection)

    @property
    def is_logged_in(self):
        return self._logged_in

    async def connect(
        self, connect_timeout=20, service_discovery_timeout=30, as_lumix_sync=False
    ):
        with self._connect_lock:
            self._service_collection: (
                bleak.backends.service.BleakGATTServiceCollection
            ) = None

            while not self._service_collection:
                if not self._device:
                    try:
                        await self.find_device()
                    except RuntimeError as e:
                        logger.exception(e)
                        continue

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
            for (
                key,
                characteristic,
            ) in self._service_collection.characteristics.items():
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
                    await self._client.start_notify(
                        characteristic, notification_handler
                    )
                    logger.info(
                        f"Notification {idx}/{len(notify_characteristics)-1} started for {characteristic}"
                    )
                except Exception as e:
                    logger.exception(
                        f"{idx}/{len(notify_characteristics)-1} notify: {e} for {characteristic}"
                    )

            # login
            if as_lumix_sync:
                ret = await self.read_handles_coro([0x002A], auto_connect=False)
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
                await self.write_handles_coro(lumix_sync_write)

                ret = await self.read_handles_coro([0x0036], auto_connect=False)
                self.camera_name = decode_nullterminated_bytes(ret[0x0036])

                ret = await self.read_handles_coro([0x0038], auto_connect=False)
                # five times 0x002a

            else:
                ret = await self.read_handles_coro([0x007A], auto_connect=False)
                logger.debug("%s", ret)
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

                ret = await self.write_handles_coro(
                    [(0x0072, value72)], response=False, auto_connect=False
                )
                ret = await self.write_handles_coro(
                    [(0x0070, b"LUMIX LUT Creators APP 1.2.1\0\0\0\0")],
                    response=False,
                )
                ret = await self.write_handles_coro(
                    [(0x0074, value74)], response=False, auto_connect=False
                )

                # Notifications 8c, 88, and 9c come here with values 1,2, and 1
                ret = await self.read_handles_coro(
                    [
                        0x0076,
                    ],
                    auto_connect=False,
                )
                self.camera_name = decode_nullterminated_bytes(ret[0x0076])

                # Notification 0x0046 with value 0x01

                ret = await self.read_handles_coro([0x0078], auto_connect=False)
                # 14 times value of 0x007A

        self._logged_in = True
        logger.info("Finished login")

    def disconnect(self):
        self._loop.run_until_complete(self._client.disconnect())

    def read_handles(self, lst: List[int]) -> Dict[int, bytearray]:
        with self._loop_lock:
            return self._loop.run_until_complete(
                self.read_handles_coro(lst, auto_connect=self.auto_connect)
            )

    async def read_handles_coro(
        self, lst: List[int], auto_connect=False
    ) -> Dict[int, bytearray]:
        if auto_connect:
            self.ensure_connected()

        d = dict()
        i = 0
        while i < len(lst):
            logger.info(f"Reading %d/%d: 0x{lst[i]:04x}", i, len(lst))
            if self.auto_connect:
                self.ensure_connected()
            handle = lst[i]
            char = self._service_collection.characteristics[handle - 1]
            try:
                d[handle] = await self._client.read_gatt_char(char)
            except EOFError as e:
                logger.exception(e)
            else:
                logger.info("Read %s", d)
                i += 1
        return d

    def write_handles(
        self, lst: List[Tuple[int, Buffer]], response: bool = True
    ) -> Dict[int, bytearray]:
        with self._loop_lock:
            return self._loop.run_until_complete(
                self.write_handles_coro(
                    lst, response=response, auto_connect=self.auto_connect
                )
            )

    async def write_handles_coro(
        self,
        lst: List[Tuple[int, Buffer]],
        response: bool = True,
        auto_connect=False,
    ) -> Dict[int, bytearray]:

        d = dict()
        i = 0
        logger.info("Writing %s", lst)
        while i < len(lst):
            logger.info(f"Writing %d/%d: 0x{lst[i][0]:04x}", i, len(lst))
            if auto_connect:
                self.ensure_connected()
            handle, data = lst[i]
            char = self._service_collection.characteristics[handle - 1]
            logger.info("Write %s %s", "0x" + f"{handle:04x}", data)
            try:
                d[i] = await self._client.write_gatt_char(char, data, response=response)
            except EOFError as e:
                # this comes when disconnect event comes during write_gatt_char
                logger.exception(e)
                self._service_collection = None
            else:
                i += 1
            if response:
                logger.info("Write Response %s", d)

        return d

    def capture(self):
        lumix_sync_write = [
            (0x0068, b"\x01"),  # notification 0x006a with value 0x00 comes here
            (0x0068, b"\x02"),  # notification 0x006a with value 0x00 comes here
            (0x0068, b"\x04"),
            (0x0068, b"\x05"),
        ]
        # TODO execution time depends on how long camera takes to focus
        # 0x04 is shutter press
        # 0x05 is shutter release

        self.write_handles(lumix_sync_write)

    def read_TODO(self):
        return self.read_handles(
            (0x005C, 0x0078, 0x009A, 0x009E, 0x00A4, 0x00A8, 0x00AA)
        )

    def shutter_press(self):
        self.write_handles([(0x0068, b"\x04")])

    def shutter_release(self):
        self.write_handles([(0x0068, b"\x05")])

    def toggle_video(self):

        lumix_sync_write_toggle_record = [
            (0x0068, b"\x06"),
            (0x0068, b"\x07"),
        ]
        self.write_handles(lumix_sync_write_toggle_record)

    def get_camera_name(self) -> str:
        # e.g. G9M2-E77E48
        ret = self.read_handles(
            [
                0x0076,
            ]
        )
        return decode_nullterminated_bytes(ret[0x0076])

    def get_camera_model(self) -> str:
        # e.g DC-G9M2
        ret = self.read_handles(
            [
                0x0094,
            ]
        )
        return decode_nullterminated_bytes(ret[0x0094])

    def get_lens(self):
        with self._loop_lock:
            ret = self._loop.run_until_complete(
                self.read_handles_coro(
                    [
                        0x0098,
                    ]
                )
            )
        return decode_nullterminated_bytes(ret[0x0098])

    def get_memory_card_status(self) -> Dict[Literal["SD1", "SD2", "SSD"], int]:
        # returns 'SD1,1,SD2,0,SSD,0'
        ret = self.read_handles(
            [
                0x0086,
            ]
        )
        data_csv = decode_nullterminated_bytes(ret[0x0086])
        data_lst = data_csv.split(",")
        return dict(zip(data_lst[0::2], data_lst[1::2]))

    def get_0x005c(self):
        # 0200000000000000
        ret = self.read_handles(
            [
                0x005C,
            ]
        )
        return ret

    def get_0x0078(self):
        # 14 times value of 0x007A
        ret = self.read_handles(
            [
                0x0078,
            ]
        )
        return ret

    def get_0x009a(self) -> str:
        # b'5376\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        # This is the same string as the second to last value in LumixG9IIWiFiControl.get_lens()
        ret = self.read_handles(
            [
                0x009A,
            ]
        )
        return decode_nullterminated_bytes(ret[0x009A])

    def get_0x09e(self):
        # b'\x02\x00\x00\x00\x00\x00\x00\x00'
        ret = self.read_handles(
            [
                0x009E,
            ]
        )
        return ret

    def get_0x00a2(self):
        # 2500000000000000

        ret = self.read_handles(
            [
                0x00A2,
            ]
        )
        return ret

    def get_0x00a4(self):
        # b'73:07:C8:E6:C1:32:C2:01:56:8C:51:E0:A6:DA:58:D8:F2:F2:4C:53:21:67:4B:C9:0C:A6:24:87:5D:CF:A2:11'
        # b'73:2D:F9:B7:75:DD:7E:28:3D:EF:FD:A0:20:DB:32:0A:79:30:D9:37:3B:9A:F8:A6:2A:D5:85:7A:7B:11:73:35'

        # Value='36463a44443a30313a43453a33443a32413a34363a30433a45443a33463a33303a35333a31383a38393a34303a42373a45463a44323a4444'
        # Value='6F:DD:01:CE:3D:2A:46:0C:ED:3F:30:53:18:89:40:B7:EF:D2:DD'

        ret = self.read_handles(
            [
                0x00A4,
            ]
        )
        return ret

    def get_0x0aa(self):
        # b'\x02\x00\x00\x00\x00\x00\x00\x00'
        ret = self.read_handles(
            [
                0x00AA,
            ]
        )
        return ret

    def get_0x00a8(self):
        # b'\x02\x00\x00\x00\x00\x00\x00\x00'
        ret = self.read_handles(
            [
                0x00A8,
            ]
        )
        return ret

    def get_firmware_version(self) -> str:
        # e.g '2.26'
        # Same as ns2:X_FirmVersion in ddd.xml
        ret = self.read_handles(
            [
                0x0096,
            ]
        )
        return decode_nullterminated_bytes(ret[0x0096])

    def enable_accesspoint(self):
        self.write_handles([(0x007C, b"\x01")])

    def activate_accesspoint(self):
        self.write_handles([(0x004A, 0x01), (0x0030, 0x05)])
        # notification 0x0088 with value 02 and 0x0032 with value 00 come here

    def connect_to_accesspoint(self, essid: str):
        data = bytearray(32)
        essid_bytes = essid.encode()
        assert len(essid_bytes) < len(data)
        data[0 : len(essid_bytes)] = essid_bytes
        self.write_handles([(0x004E, data), (0x004A, 0x03)])

        # notification 0x004c with value 00 comes here when using lumix sync

        self.write_handles([(0x004A, 0x02), (0x0030, 0x03)])

        # notification 0x0088 with value 02 and 0x0032 with value 00 come here

    async def wifi5GHz(self, status: bool):
        if status:
            value = b"\x02"
        else:
            value = b"\x01"
        self.write_handles_coro([0x00A0, value], response=False)

    def write_0x007c(self):
        # Maybe Lumix Lab's Command for enable Accesspoint mode
        self.write_handles([(0x007C, b"\x01")])
        # values 0, 1, and 2 can bet set. value 3 and 4 causes write command to hang 

        # Maybe those notifications are abount disconnected clients
        # INFO:LumixG9IIRemoteControl.LumixG9IIBluetoothControl:Notification dcba3a74-80bc-4919-8ef4-0c9f99cc20dd (Handle: 109): Unknown: bytearray(b'\x01')
        # INFO:LumixG9IIRemoteControl.LumixG9IIBluetoothControl:Notification 16726c35-52ef-4d00-868d-099549a90d9b (Handle: 155): Unknown: bytearray(b'\x02')
        # INFO:LumixG9IIRemoteControl.LumixG9IIBluetoothControl:Notification 16726c35-52ef-4d00-868d-099549a90d9b (Handle: 155): Unknown: bytearray(b'\x01')
        # INFO:LumixG9IIRemoteControl.LumixG9IIBluetoothControl:Notification dcba3a74-80bc-4919-8ef4-0c9f99cc20dd (Handle: 109): Unknown: bytearray(b'\x03')

    def write_0x0090(self):
        # Lumix Lab writes to 0x0090 values like
        # Value: e8070c10082a32003c00
        # Value: e8070c10082c24003c00
        # Value: e8070c10090a18003c00
        # Value: e8070c10090c11003c00
        # which suspiciesly look like 0x0040 writes by lumix sync
        raise NotImplementedError

    def write_0x0044(self):
        # Lumix Sync Write to 0x044 values like
        # Value: e8070c0d0713153c0000
        # Value: e8070c0d08060f3c0000
        # Value: e8070c0d080a183c0000
        # Value: e8070c0d080c213c0000
        # Value: e8070c0f11030f3c0000
        # Value: e8070c160e2b1b3c0000
        # Value: e8070c160e2b1b3c0000
        # Value: e8070c160e1b153c0000
        # after which, it requests a new challenge response
        raise NotImplementedError

    def write_0x008e(self):
        # Lumix Lab writes to 0x008e values like 0x02
        raise NotImplementedError

    async def send_gps_location(self, lon_deg, lat_deg):
        # Lumix syncwrites continously (several times per second) 0x003e, with 16 bytes
        # maybe keep-alive pattern or GPS data
        # Excample value
        # 23af8654_cfd2d11c_9df39508_99014100
        # 37a38654_91d7d11c_f5ee9508_9e014100
        # First byte (23) is incremented by one every 10-th cycle
        # Fifth byte is incremented by small values every 10-th cycle
        # 9-th byte is noisy
        # 13-th byte is noisy

        # print(struct.unpack('<iiii', data))
        # # (1418112864, 483513018, 144045045, 4260249)
        # #print(struct.unpack('>8H', data))
        # _, lon_deg, lat_deg, _ = struct.unpack('<iiii', data)
        # lon_deg = lon_deg/10000000
        # lat_deg = lat_deg/10000000

        self.gps_packet_header += 1
        data = (
            self.gps_packet_header,
            int(lon_deg * 10000000),
            int(lat_deg * 10000000),
            4260249,
        )
        await self.write_handles_coro([(0x003E, struct.pack("<iiii", *data))])

    async def auto_clock_sync(self, status):
        raise NotImplementedError
        self.write_handles_coro([0x0090, 0xE8070C1009361B003C00])
        # 7-th of 10 bytes change

        # notification 92 and 46 with value 1 come here

        # every four seconds write to 0x008a values like
        # 0x58BB8A54_3FD4D11C_72EF9508_7C014100
        # 0x5CBB8A54_3FD4D11C_71EF9508_7C014100
        # 0x60BB8A54_3FD4D11C_71EF9508_7C014100
        # 0x66BB8A54_41D4D11C_76EF9508_7C014100
        # 0x6ABB8A54_41D4D11C_76EF9508_7C014100
        # 0x01BD8A54_89DBD11C_11F69508_B1014100
        # 0x0FBD8A54_29D4D11C_E8F49508_9A014100
        # 0x14BD8A54_58D4D11C_CBF49508_98014100
        # 0x15BD8A54_54D4D11C_CFF49508_98014100


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
    # IPython.embed()
