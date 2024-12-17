import asyncio
import logging
import os
import pprint
import struct
import time
import traceback
from typing import Dict, List, Tuple

import bleak
import bleak.backends
import bleak.backends.service
from bleak import BleakClient, BleakScanner, BLEDevice
from bleak.uuids import normalize_uuid_16, uuid16_dict
from typing_extensions import Buffer

from LumixG9IIRemoteControl.LumixG9IIBluetoothControl import hash_lumix_sync

# https://www.bluetooth.com/specifications/assigned-numbers/


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

# uuid16_lookup = {v: normalize_uuid_16(k) for k, v in uuid16_dict.items()}


# https://github.com/hbldh/bleak/blob/master/examples/detection_callback.py


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
    logger.info("%s: %r", characteristic.description, data)


async def main():
    # print("scanning for 5 seconds, please wait...")

    disconnected_event = asyncio.Event()

    def disconnected_callback(client):
        logger.info("Disconnected callback called!")
        disconnected_event.set()

    # devices = await BleakScanner.discover(
    #     return_adv=True,
    #     detection_callback = detection_callback,
    #     disconnected_callback=disconnected_callback,
    # )

    # for d, a in devices.values():
    #     print(d, "-", a)
    #     # 52:30:70:FA:3C:82: G9M2-E77E48
    #     # AdvertisementData(local_name='G9M2-E77E48\n\x05', manufacturer_data={58: b'\x00\xcd\xf3\xe4\xb3\x8e'}, service_uuids=['054ac620-3214-11e6-ac0d-0002a5d5c51b'], rssi=-90)

    device = await BleakScanner.find_device_by_filter(
        device_filter, timeout=30, detection_callback=detection_callback
    )
    if device is None:
        logger.error("could not find device")
        raise RuntimeError("could not find device")
    else:
        logger.info("Found device %r", device)

    # async with BleakClient(
    #     device,
    #     disconnected_callback=disconnected_callback,
    #     timeout=20,
    # ) as client:
    client = BleakClient(
        device,
        disconnected_callback=disconnected_callback,
        timeout=20,
    )
    # logger.info('%s', pprint.pformat(dir(client))
    # logger.info('%s', pprint.pformat(dir(client._backend))
    # breakpoint()
    N = 10
    service_collection: bleak.backends.service.BleakGATTServiceCollection = None
    while not service_collection:
        await client.disconnect()
        await client.connect()
        logger.info("Connected %s, %r", client.is_connected, client)

        # wait for service collection to be populated
        time_start = time.time()
        while (
            client.is_connected
            and not service_collection
            and time.time() - time_start < 20
        ):
            time.sleep(1)
            try:
                service_collection: bleak.BleakGATTServiceCollection = client.services
            except (
                bleak.BleakError,
                asyncio.exceptions.CancelledError,
                TimeoutError,
                TypeError,
            ) as e:
                logger.exception(e)
                if not client.is_connected:
                    raise RuntimeError

    logger.info("Connected %s, %r", client.is_connected, client)

    # N = 10
    # while True:
    #     try:
    #         N -= 1
    #         service_collection: bleak.BleakGATTServiceCollection = client.services
    #         break
    #     except bleak.BleakError as e:
    #         traceback.print_exception(e)

    #         #if "bleak.exc.BleakError: Service Discovery has not been performed yet" occurs, waiting doe not
    #         if N > 0:
    #             # asyncio.sleep(2)
    #             time.sleep(3)
    #         else:
    #             raise e
    # logger.warning("Got Services")

    try:
        logger.info("services: %s", pprint.pformat(service_collection.services))
        logger.info(
            "characteristics: %s", pprint.pformat(service_collection.characteristics)
        )
    except UnboundLocalError as e:
        logger.exception(e)
        # TODO why even get here with service_collection not defined
        # breakpoint()

    # print("descriptors:")
    # logger.info('%s', pprint.pformat(service_collection.descriptors)

    for service in service_collection.services.values():
        service: bleak.backends.service.BleakGATTService

        logger.info(
            "Service %s",
            pprint.pformat(
                {
                    "handle_int": service.handle,
                    "handle_hex": f"0x{service.handle:04x}",
                    "uuid": service.uuid,
                    "description": service.description,
                }
            ),
        )

        for characteristic in service.characteristics:
            # for some reason, service.characteristics is empty
            # thus loop over service_collection.characteristics later
            characteristic: bleak.BleakGATTCharacteristic
            logger.info(
                "Service %s: Characteristic %s",
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

    readable_characteristics = []
    notify_characteristics = []
    writable_characteristics = []
    indicate_characteristics = []
    for key, characteristic in service_collection.characteristics.items():
        characteristic: bleak.BleakGATTCharacteristic
        logger.info(
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

        if "notify" in characteristic.properties:
            writable_characteristics.append(characteristic)

        if "indicate" in characteristic.properties:
            indicate_characteristics.append(characteristic)

    # setup notifications
    for idx, characteristic in enumerate(notify_characteristics):
        try:
            await client.start_notify(characteristic, notification_handler)
            logger.info(
                f"Notification {idx}/{len(notify_characteristics)-1} started for {characteristic}"
            )
        except Exception as e:
            logger.exception(
                f"{idx}/{len(notify_characteristics)-1} notify: {e} for {characteristic}"
            )

    # # read descriptors
    for key, descriptor in service_collection.descriptors.items():
        d = {
            "key": key,
            "uuid": descriptor.uuid,
            "handle_int": descriptor.handle,
            "handle_hex": f"{descriptor.handle:04x}",
            "description": descriptor.description,
            "characteristic_uuid": descriptor.characteristic_uuid,
            "characteristic_handle": descriptor.characteristic_handle,
        }
        try:
            ret = await client.read_gatt_descriptor(key)
            d["value"] = ret
        except Exception as e:
            logger.exception(e)

        logger.info(
            "Descriptor %s",
            pprint.pformat(d),
        )

    # for idx, characteristic in enumerate(readable_characteristics):
    #     ret = await client.read_gatt_char(characteristic.handle - 1)
    #     print(f"{idx}/{len(readable_characteristics)}, {characteristic}: {ret}")

    async def read_list(lst: List[int]) -> Dict[int, bytearray]:
        d = dict()
        for i in lst:
            char = service_collection.characteristics[i - 1]
            d[i] = await client.read_gatt_char(char)
            logger.info("Read %s", d)
        return d

    async def write_list(lst: List[Tuple[int, Buffer]]) -> Dict[int, bytearray]:
        d = dict()
        for i, data in lst:
            char = service_collection.characteristics[i - 1]
            logger.info("Write %s %s", i, data)
            d[i] = await client.write_gatt_char(char, data, response=True)
            logger.info("Write Response %s", d)
        return d

    lumix_sync_attribute_no_found_reads = [
        0x0001,
        0x0003,
        0x0004,
        0x0014,
        0x001A,
        0x001B,
        0x0028,
        0x003A,
        0x003B,
        0x003C,
        0x0040,
        0x0041,
        0x0042,
        0x0046,
        0x0047,
        0x0048,
        0x004E,
        0x004F,
        0x005C,
        0x005D,
        0x005E,
        0x0064,
        0x0065,
        0x0066,
        0x006A,
        0x006B,
        0x006C,
        0x00AA,
        0x00AB,
    ]

    # ret = await read_list(lumix_sync_attribute_no_found_reads)
    # logger.info('%s', pprint.pformat(ret)

    lumix_sync_reads = [
        0x002A,
    ]
    # Note return value is always different, example read 84bbfd60
    ret = await read_list(lumix_sync_reads)
    logger.info(
        "%s",
        pprint.pformat(["0x" + "".join([f"{x:04x}" for x in lumix_sync_reads]), ret]),
    )
    ret_int = struct.unpack("I", ret[0x002A])[0]
    logger.info(f"0x{ret_int:08x}")

    value2c, value2e = hash_lumix_sync(ret[0x002A])
    logger.info(
        "Calculated value for 0x002C 0x" + "".join([f"{x:02x}" for x in value2c])
    )
    logger.info(
        "Calculated value for 0x002E 0x" + "".join([f"{x:02x}" for x in value2e])
    )

    lumix_sync_write = [
        (0x002C, value2c),
        (0x002E, value2e),
    ]
    await write_list(lumix_sync_write)

    # maybe handle notification 0x0040 with value 1 comes here

    # read camera name as null-terminated string
    lumix_sync_reads = [
        0x0036,
    ]
    ret = await read_list(lumix_sync_reads)
    logger.info(
        "%s",
        pprint.pformat(["0x" + "".join([f"{x:04x}" for x in lumix_sync_reads]), ret]),
    )

    # lumix sync reads then 0x036 offset 22 to get buffer after string termination

    # lumix sync reads 0x0038, which is concatenation of trice of content of 0x002a
    lumix_sync_reads = [
        0x0038,
    ]

    ret = await read_list(lumix_sync_reads)
    logger.info(
        "%s",
        pprint.pformat(["0x" + "".join([f"{x:04x}" for x in lumix_sync_reads]), ret]),
    )

    # lumix sync reads 0x0038, at offsets 22,44, and 66

    # It then writes continously (several times per second) 0x003e, with 16 bytes
    # maybe keep-alive pattern or GPS data
    # Excample value
    # 23af8654_cfd2d11c_9df39508_99014100
    # 37a38654_91d7d11c_f5ee9508_9e014100
    # First byte (23) is incremented by one every 10-th cycle
    # Fifth byte is incremented by small values every 10-th cycle
    # 9-th byte is noisy
    # 13-th byte is noisy

    # Capture
    # await client.write_gatt_char(0x0068 - 1, 0x02, response=True)
    # await client.write_gatt_char(0x0068 - 1, 0x02, response=True)
    lumix_sync_write = [
        (0x0068, b"\x01"),
        (0x0068, b"\x02"),
        (0x0068, b"\x04"),
        (0x0068, b"\x05"),
        (0x0068, b"\x05"),
        (0x0068, b"\x06"),
        (0x0068, b"\x05"),
        (0x0068, b"\x05"),
        # (0x0068, bytes.fromhex("04")),
        # (0x0068, bytes.fromhex("05")),
    ]
    await write_list(lumix_sync_write)

    lumix_sync_write_toggle_record = [
        (0x0068, b"\x06"),
        (0x0068, b"\x07"),
    ]
    # Write to 0x0068 00 to 05 sometimes raises notification 0x006a with value 00

    # Take a picture via Lumix Sync sends 04 and 05 to 0x0068

    # again lumix_sync_attribute_no_found_reads
    lumix_sync_reads = [
        0x007A,
    ]
    ret = await read_list(lumix_sync_reads)
    # logger.info(
    #     "%s",
    #     pprint.pformat(["0x" + "".join([f"{x:04x}" for x in lumix_sync_reads]), ret]),
    # )

    lumix_sync_write = [
        (0x0072, 0xC0019D),
        (0x0070, 0x4C554D),
        (0x0074, 0x764EAB),
    ]
    await write_list(lumix_sync_write)

    lumix_sync_reads = [
        0x0076,
    ]
    ret = await read_list(lumix_sync_reads)
    logger.info(
        "%s",
        pprint.pformat(["0x" + "".join([f"{x:04x}" for x in lumix_sync_reads]), ret]),
    )

    # notification: 0x008c, 88,88,9c with values 1,2,4,1
    lumix_sync_reads = [
        0x076,
        0x078,
    ]
    ret = await read_list(lumix_sync_reads)
    logger.info(
        "%s",
        pprint.pformat(["0x" + "".join([f"{x:04x}" for x in lumix_sync_reads]), ret]),
    )

    # blob_read 0x076 offset 56

    lumix_sync_reads = [0x009E, 0x00A2, 0x00A4]
    ret = await read_list(lumix_sync_reads)
    logger.info(
        "%s",
        pprint.pformat(["0x" + "".join([f"{x:04x}" for x in lumix_sync_reads]), ret]),
    )

    # blob_read 0x00a4 offset 56

    lumix_sync_reads = [0x0094, 0x0096, 0x0098]
    ret = await read_list(lumix_sync_reads)
    logger.info(
        "%s",
        pprint.pformat(["0x" + "".join([f"{x:04x}" for x in lumix_sync_reads]), ret]),
    )

    # blob_read 0x0098 offset 56

    lumix_sync_reads = [0x009A, 0x00A8, 0x00AA, 0x0096]
    ret = await read_list(lumix_sync_reads)
    logger.info(
        "%s",
        pprint.pformat(["0x" + "".join([f"{x:04x}" for x in lumix_sync_reads]), ret]),
    )

    lumix_sync_write = [
        (0x0090, 0xE8070B),
    ]
    await write_list(lumix_sync_write)
    # notification 0x0092 value 1

    lumix_sync_write = [
        (0x008E, 0x7C6767),
    ]
    await write_list(lumix_sync_write)

    # notification 0x0046 and 0x008c value 1 and 2

    # write 0x01 to 0x004a maybe connects to wifi

    # ret = await client.read_gatt_char(0x007A - 1)
    # print(f"0x007a: {ret}")

    # for idx, characteristic in enumerate(readable_characteristics):
    #     print(f'{idx}/{len(readable_characteristics)-1}')
    #     ret = await client.read_gatt_char(characteristic.handle-1)
    #     print("0x"+''.join([f'{x:x}' for x in ret]))

    # Capture
    # await client.write_gatt_char(0x0068 - 1, 0x02, response=True)
    # await client.write_gatt_char(0x0068 - 1, 0x02, response=True)
    lumix_sync_write = [
        (0x0068, b"\x01"),
        (0x0068, b"\x02"),
        (0x0068, b"\x04"),
        (0x0068, b"\x05"),
        (0x0068, b"\x04"),
        (0x0068, b"\x05"),
        (0x0068, b"\x04"),
        (0x0068, b"\x05"),
    ]
    await write_list(lumix_sync_write)

    # ret = await client.read_gatt_char(0x007a-1)
    # print(f"0x007a: {ret}")
    # TODO: camera remains in "Connecting to Bluetooth / Wi-Fi" state with a waiting circle here.
    logger.info("wait for disconnect")
    await disconnected_event.wait()

    # for key in service_collection.characteristics:
    #     try:
    #         ret = await client.read_gatt_char(
    #             service_collection.characteristics[85]
    #         )
    #         print("read_gatt_char ", key, ": ", ret)
    #     except bleak.exc.BleakDBusError as e:
    #         print("read_gatt_char ", key, ": ", e)

    for idx, characteristic in enumerate(readable_characteristics):
        # TODO: ATT errors like 0x80 or 0x0e can occur, on which automatic disconnect happens
        # In wireshark logs, those error occur as well, but no disconnect happens.

        if not client.is_connected:
            N = 10
            try:
                N -= 1
                await client.connect(timeout=20)
                time.sleep(2)
            except (bleak.exc.BleakError, TimeoutError) as e:
                if N > 0:
                    traceback.print_exception(e)
                else:
                    raise e
        try:
            ret = await client.read_gatt_char(characteristic)
            print(f"{idx}/{len(readable_characteristics)}, {characteristic}: {ret}")
        except Exception as e:
            print(f"{idx}/{len(readable_characteristics)}, {characteristic} {e}")
            if client.is_connected:
                await client.disconnect()
    # await client.start_notify(, notification_handler)
    # logger.info("Sleeping until device disconnects...")
    # await disconnected_event.wait()
    # logger.info("Connected: %r", client.is_connected)


if __name__ == "__main__":
    asyncio.run(main())
