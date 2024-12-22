import logging
import struct
from typing import Tuple

logging.basicConfig()
logger = logging.getLogger()


def hash_wifi(req_acc_g_str: str) -> Tuple[str, str]:
    req_acc_g_bytes = bytes.fromhex(req_acc_g_str)
    req_acc_g_int = struct.unpack("<I", req_acc_g_bytes)[0]

    value = bytearray(36)
    for i, x in enumerate(
        [
            892617780,
            808663348,
            808529965,
            808529200,
            942485552,
            758198320,
            809579056,
            842018864,
            942748980,
        ]
    ):
        value[i * 4 : (i + 4) * 4] = struct.pack(">I", req_acc_g_int ^ x)

    value2 = struct.pack(">I", req_acc_g_int ^ 4281684038)

    # logger.warning("0x" + "".join([f"{x:02x}" for x in value]))
    # logger.warning("0x" + "".join([f"{x:02x}" for x in value2]))

    return "".join([f"{x:02x}" for x in value]), "".join([f"{x:02x}" for x in value2])


def dummy():
    req_acc_g_bytes = bytearray.fromhex(req_acc_g)
    req_acc_g_int = struct.unpack("<I", req_acc_g_bytes)[0]

    value_bytes = bytearray.fromhex(value)
    value_ints = struct.unpack(">9I", value_bytes)
    print([req_acc_g_int ^ x for x in value_ints])

    value2_bytes = bytearray.fromhex(value2)
    value_2_int = struct.unpack(">I", value2_bytes)[0]

    print(req_acc_g_int ^ value_2_int)


if __name__ == "__main__":

    req_acc_g = "34de8bd1"
    value = "e4bf9a00e1b8e700e1baee19e1baf304e9a6ee04fcbaee04e1caec04e3bbee04e9baeb00"
    value2 = "2ebe8e72"
    # dummy()
    print(hash_wifi(req_acc_g))

    req_acc_g = "3f8fce23"
    value = "16facb0b13fdb60b13ffbf1213ffa20f1be3bf0f0effbf0f138fbd0f11febf0f1bffba0b"
    value2 = "dcfbdf79"
    # dummy()
    print(hash_wifi(req_acc_g))

    req_acc_g = "1b7e9dd0"
    value = "e5a93a2fe0ae472fe0ac4e36e0ac532be8b04e2bfdac4e2be0dc4c2be2ad4e2be8ac4b2f"
    value2 = "2fa82e5d"
    # dummy()
    print(hash_wifi(req_acc_g))

    req_acc_g = "5316eeda"
    value = "efda5267eadd2f67eadf267eeadf3b63e2c32663f7df2663eaaf2463e8de2663e2df2367"
    value2 = "25db4615"
    # dummy()
    print(hash_wifi(req_acc_g))

    req_acc_g = "5cf9fd8f"
    value = "bac9bd68bfcec068bfccc971bfccd46cb7d0c96ca2ccc96cbfbccb6cbdcdc96cb7cccc68"
    value2 = "70c8a91a"
    # dummy()
    print(hash_wifi(req_acc_g))

    req_acc_g = "6b839c92"
    value = "a7a8c75fa2afba5fa2adb346a2adae5baab1b35bbfadb35ba2ddb15ba0acb35baaadb65f"
    value2 = "6da9d32d"
    # dummy()
    print(hash_wifi(req_acc_g))
