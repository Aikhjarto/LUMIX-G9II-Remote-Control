import asyncio
import logging
import pprint
import time
import traceback
from typing import Dict, List, Tuple

import bleak
import bleak.backends
from bleak import BleakClient, BleakScanner, BLEDevice
from bleak.uuids import normalize_uuid_16, uuid16_dict
from typing_extensions import Buffer

logging.basicConfig()
logger = logging.getLogger()
logger.setLevel("DEBUG")
uuid16_lookup = {v: normalize_uuid_16(k) for k, v in uuid16_dict.items()}


# https://github.com/hbldh/bleak/blob/master/examples/detection_callback.py


def detection_callback(
    device: bleak.BLEDevice, advertisement_data: bleak.AdvertisementData
):
    # logger.warning("%s: %r", device.address, advertisement_data)
    pass


def device_filter(device: bleak.BLEDevice, advertisement_data: bleak.AdvertisementData):
    if advertisement_data and advertisement_data.local_name:
        if advertisement_data.local_name.startswith("G9M2"):
            logger.warning("Device Filter %s: %r", device.address, advertisement_data)
            return True


def notification_handler(
    characteristic: bleak.BleakGATTCharacteristic, data: bytearray
):
    """Simple notification handler which prints the data received."""
    logger.warning("%s: %r", characteristic.description, data)


async def scan_main():
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
        logger.warning("could not find device")
        return
    else:
        logger.warning("Found device %r", device)

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
    # pprint.pprint(dir(client))
    # pprint.pprint(dir(client._backend))
    # breakpoint()
    N = 10
    try:
        N = N - 1
        await client.connect()

        # wait for service collection to be populated
        time_start = time.time()
        while True:
            try:
                service_collection: bleak.BleakGATTServiceCollection = client.services
            except (
                bleak.BleakError,
                asyncio.exceptions.CancelledError,
                TimeoutError,
                TypeError,
            ) as e:
                raise e  # debug
                if not client.is_connected:
                    raise RuntimeError
                if time.time() - time_start < 10:
                    # traceback.print_exception(e)
                    pass
            finally:
                if service_collection:
                    break

                if time.time() - time_start > 10:
                    raise e

                time.sleep(2)

    except (
        bleak.exc.BleakError,
        TimeoutError,
        RuntimeError,
        asyncio.CancelledError,
    ) as e:
        # raise e  # debug
        if N > 0:
            await client.disconnect()
            time.sleep(2)
            traceback.print_exception(e)
        else:
            raise e

    logger.warning("Connected %s, %r", client.is_connected, client)

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
        print("services:")
        pprint.pprint(service_collection.services)
        print("characteristics:")
        pprint.pprint(service_collection.characteristics)
    except UnboundLocalError as e:
        traceback.print_exception(e)
        # TODO why even get here with service_collection not defined
        breakpoint()

    # print("descriptors:")
    # pprint.pprint(service_collection.descriptors)

    readable_characteristics = []
    notify_characteristics = []
    for key, characteristic in service_collection.characteristics.items():
        characteristic: bleak.BleakGATTCharacteristic
        # pprint.pprint(
        #     {
        #         "key": key,
        #         "str": str(characteristic),
        #         "descriptors": characteristic.descriptors,
        #         "description": characteristic.description,
        #         "service_uuid": characteristic.service_uuid,
        #         "uuid": characteristic.uuid,
        #         "properties": characteristic.properties,
        #     }
        # )

        if "read" in characteristic.properties:
            readable_characteristics.append(characteristic)

        if "notify" in characteristic.properties:
            notify_characteristics.append(characteristic)

    # setup notifications
    for idx, characteristic in enumerate(notify_characteristics):
        try:
            await client.start_notify(characteristic, notification_handler)
            print(f"{idx}/{len(notify_characteristics)-1} {characteristic}")
        except Exception as e:
            print(f"{idx}/{len(notify_characteristics)-1} notfiy: {e}")

    # # read descriptors
    # for key, descriptor in service_collection.descriptors.items():
    #     pprint.pprint({'key': key,
    #                    'uuid': descriptor.uuid,
    #                    'handle': descriptor.handle,
    #                    'description': descriptor.description,
    #                    'characteristic_uuid': descriptor.characteristic_uuid,
    #                    'characteristic_handle':descriptor.characteristic_handle,
    #                    })
    #     try:
    #         ret = await client.read_gatt_descriptor(key)
    #         print(f"{key} {descriptor} {ret}")
    #     except Exception as e:
    #         print(f"{key} {descriptor} {e}")

    async def read_list(lst: List[int]) -> Dict[int, bytearray]:
        d = dict()
        for i in lst:
            char = service_collection.characteristics[i - 1]
            d[i] = await client.read_gatt_char(char)
        return d

    async def write_list(lst: List[Tuple[int, Buffer]]) -> Dict[int, bytearray]:
        d = dict()
        for i, data in lst:
            char = service_collection.characteristics[i - 1]
            d[i] = await client.write_gatt_char(char, data, response=True)
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
    # pprint.pprint(ret)

    lumix_sync_reads = [
        0x002A,
    ]
    # Note return value is always different, example read 0x22408d11
    ret = await read_list(lumix_sync_reads)
    pprint.pprint(["0x" + "".join([hex(x) for x in lumix_sync_reads]), ret])

    lumix_sync_write = [
        (0x002C, b"\x6B\x05\xC0"),
        (0x002E, b"\x17\x10\xCB"),
    ]
    await write_list(lumix_sync_write)

    print("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    # TODO device disconnects here after a few seconds, probably sending wrong values
    await asyncio.sleep(30)
    print("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    # again lumix_sync_attribute_no_found_reads
    lumix_sync_reads = [
        0x007A,
    ]
    ret = await read_list(lumix_sync_reads)
    pprint.pprint(["0x" + "".join([hex(x) for x in lumix_sync_reads]), ret])

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
    pprint.pprint(["0x" + "".join([hex(x) for x in lumix_sync_reads]), ret])

    # notification: 0x008c, 88,88,9c with values 1,2,4,1
    lumix_sync_reads = [
        0x076,
        0x078,
    ]
    ret = await read_list(lumix_sync_reads)
    pprint.pprint(["0x" + "".join([hex(x) for x in lumix_sync_reads]), ret])

    # blob_read 0x076 offset 56

    lumix_sync_reads = [0x009E, 0x00A2, 0x00A4]
    ret = await read_list(lumix_sync_reads)
    pprint.pprint(["0x" + "".join([hex(x) for x in lumix_sync_reads]), ret])

    # blob_read 0x00a4 offset 56

    lumix_sync_reads = [0x0094, 0x0096, 0x0098]
    ret = await read_list(lumix_sync_reads)
    pprint.pprint(["0x" + "".join([hex(x) for x in lumix_sync_reads]), ret])

    # blob_read 0x0098 offset 56

    lumix_sync_reads = [0x009A, 0x00A8, 0x00AA, 0x0096]
    ret = await read_list(lumix_sync_reads)
    pprint.pprint(["0x" + "".join([hex(x) for x in lumix_sync_reads]), ret])

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

    # ret = await client.read_gatt_char(0x007A - 1)
    # print(f"0x007a: {ret}")

    # for idx, characteristic in enumerate(readable_characteristics):
    #     print(f'{idx}/{len(readable_characteristics)-1}')
    #     ret = await client.read_gatt_char(characteristic.handle-1)
    #     print("0x"+''.join([f'{x:x}' for x in ret]))

    # ret = await client.read_gatt_char(0x007a-1)
    # print(f"0x007a: {ret}")
    # TODO: camera remains in "Connecting to Bluetooth / Wi-Fi" state with a waiting circle here.
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
    asyncio.run(scan_main())
