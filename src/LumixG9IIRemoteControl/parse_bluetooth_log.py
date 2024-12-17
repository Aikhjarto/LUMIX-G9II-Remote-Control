import os
import struct
from typing import Dict, Literal, Union

import scapy.all
from scapy.layers.bluetooth import (
    ATT_Read_Blob_Request,
    ATT_Read_Blob_Response,
    ATT_Read_Request,
    ATT_Read_Response,
    ATT_Write_Command,
    ATT_Write_Request,
)


def parse_file():
    # filename = os.path.join(
    #     os.path.dirname(__file__), "../../Dumps/Bluetooth/btdump.pcapng"
    # )

    filename = os.path.join(
        os.path.dirname(__file__),
        "../../Dumps/Bluetooth/btdump_lumix_lab_connects.pcapng",
    )

    a = []
    lst = []
    lst_68 = []
    lst_lumix_lab = []
    with scapy.all.PcapNgReader(filename) as pcap_reader:
        d_login_lumix_sync = None
        d_login_lumix_lab = None
        d_68 = None
        last_read_request_handle: int = -1
        for pkt in pcap_reader:
            if (
                pkt.haslayer(ATT_Read_Response)
                or pkt.haslayer(ATT_Write_Request)
                or pkt.haslayer(ATT_Read_Request)
                or pkt.haslayer(ATT_Write_Command)
            ):
                a.append(pkt)

            if pkt.haslayer(ATT_Write_Request):
                fields = pkt.getlayer(ATT_Write_Request).fields
                data = pkt.getlayer(ATT_Write_Request).fields["data"]
                if fields["gatt_handle"] == 0x003E:
                    pass
                    # print('ATT_Write_Request %s:', pkt.getlayer(ATT_Write_Request).fields, len(data))
                    # print(struct.unpack('<iiii', data))
                    # # (1418112864, 483513018, 144045045, 4260249)
                    # #print(struct.unpack('>8H', data))
                    # _, lon_deg, lat_deg, _ = struct.unpack('<iiii', data)
                    # lon_deg = lon_deg/10000000
                    # lat_deg = lat_deg/10000000
                else:
                    print(
                        "ATT_Write_Request %s:",
                        pkt.getlayer(ATT_Write_Request).fields,
                        len(data),
                    )
                    lst_68.append(pkt.getlayer(ATT_Write_Request).fields)

            if pkt.haslayer(ATT_Read_Blob_Request):
                print(
                    pkt.getlayer(ATT_Read_Blob_Request).__repr__(),
                    pkt.getlayer(ATT_Read_Blob_Request).fields,
                )

            if pkt.haslayer(ATT_Read_Blob_Response):
                print(
                    pkt.getlayer(ATT_Read_Blob_Response).__repr__(),
                    pkt.getlayer(ATT_Read_Blob_Response).fields,
                )

            if pkt.haslayer(ATT_Read_Request):
                last_read_request_handle = pkt.getlayer(ATT_Read_Request).fields[
                    "gatt_handle"
                ]
                if last_read_request_handle == 0x0042:
                    d_login_lumix_sync = {}
                if last_read_request_handle == 0x007A:
                    d_login_lumix_lab = {}
                print(
                    "ATT_Read_Request %s:",
                    f"0x{pkt.getlayer(ATT_Read_Request).fields['gatt_handle']:04x}",
                )

            if isinstance(d_login_lumix_sync, dict):
                if pkt.haslayer(ATT_Read_Response):
                    d_login_lumix_sync[last_read_request_handle] = pkt.getlayer(
                        ATT_Read_Response
                    ).fields["value"]
                    print(
                        "ATT_Read_Response %s:",
                        "0x"
                        + "".join(
                            [
                                f"{x:2x}"
                                for x in (
                                    pkt.getlayer(ATT_Read_Response).fields["value"]
                                )
                            ]
                        ),
                    )

                if pkt.haslayer(ATT_Write_Request):
                    fields = pkt.getlayer(ATT_Write_Request).fields
                    d_login_lumix_sync[fields["gatt_handle"]] = fields["data"]

                if 44 in d_login_lumix_sync and 46 in d_login_lumix_sync:
                    lst.append(d_login_lumix_sync)
                    d_login_lumix_sync = None

            if isinstance(d_login_lumix_lab, dict):
                if pkt.haslayer(ATT_Read_Response):

                    d_login_lumix_lab[last_read_request_handle] = pkt.getlayer(
                        ATT_Read_Response
                    ).fields["value"]

                if pkt.haslayer(ATT_Write_Command):
                    fields = pkt.getlayer(ATT_Write_Command).fields

                    d_login_lumix_lab[fields["gatt_handle"]] = fields["data"]

                if (
                    0x007A in d_login_lumix_lab
                    and 0x0072 in d_login_lumix_lab
                    and 0x0074 in d_login_lumix_lab
                ):
                    lst_lumix_lab.append(d_login_lumix_lab)
                    d_login_lumix_lab = None

    return a, lst, lst_68, lst_lumix_lab


def dummy_lumix_lab(d: Dict[Union[0x007A, 0x0072, 0x0074], bytes]):
    format = ">I"
    # breakpoint()
    value_7a = struct.unpack(format, d[0x7A])[0]
    values_72 = [
        struct.unpack(format, d[0x72][i * 4 : (i + 1) * 4])[0]
        for i in range(len(d[0x72]) // 4)
    ]
    values_74 = [
        struct.unpack(format, d[0x74][i * 4 : (i + 1) * 4])[0]
        for i in range(len(d[0x74]) // 4)
    ]

    # print("0x" + "_".join([f"{x:08b}" for x in d[42]]))
    # print("0x" + "_".join([f"{x:08b}" for x in d[44]]))
    # print("0x" + "_".join([f"{x:08b}" for x in d[46]]))

    print("0x007A 0x" + "".join([f"{x:02x}" for x in d[0x7A]]))
    print("0x0072 0x" + "".join([f"{x:02x}" for x in d[0x72]]))
    print("0x0074 0x" + "".join([f"{x:02x}" for x in d[0x74]]))

    # print("0x002C:", [f"{x:08x}" for x in values_2c])
    # print("0x002E:", [f"{x:08x}" for x in values_2e])
    # print("0x002C-0x002A:", [f"{(value - value_2a):08x}" for value in values_2c])
    # print("0x002E-0x002A:", [f"{(value - value_2a):08x}" for value in values_2e])
    # print("0x002C+0x002A:", [f"{(value - value_2a):08x}" for value in values_2c])
    # print("0x002E+0x002A:", [f"{(value - value_2a):08x}" for value in values_2e])
    print("0x0072^0x007A:", [f"{(value ^ value_7a):08x}" for value in values_72])
    print("0x0074^0x007A:", [f"{(value ^ value_7a):08x}" for value in values_74])
    # print(values_2c[-1] - values_2e[-1])  # this is +- 8 or 24


def dummy2(d: Dict[Union[42, 44, 46], bytes]):
    format = ">I"
    value_2a = struct.unpack(format, d[42])[0]
    values_2c = [struct.unpack(format, d[44][i * 4 : (i + 1) * 4])[0] for i in range(5)]
    values_2e = [struct.unpack(format, d[46][i * 4 : (i + 1) * 4])[0] for i in range(5)]

    # print("0x" + "_".join([f"{x:08b}" for x in d[42]]))
    # print("0x" + "_".join([f"{x:08b}" for x in d[44]]))
    # print("0x" + "_".join([f"{x:08b}" for x in d[46]]))

    print("0x002A 0x" + "".join([f"{x:02x}" for x in d[42]]))
    print("0x002C 0x" + "".join([f"{x:02x}" for x in d[44]]))
    print("0x002E 0x" + "".join([f"{x:02x}" for x in d[46]]))

    # print("0x002C:", [f"{x:08x}" for x in values_2c])
    # print("0x002E:", [f"{x:08x}" for x in values_2e])
    # print("0x002C-0x002A:", [f"{(value - value_2a):08x}" for value in values_2c])
    # print("0x002E-0x002A:", [f"{(value - value_2a):08x}" for value in values_2e])
    # print("0x002C+0x002A:", [f"{(value - value_2a):08x}" for value in values_2c])
    # print("0x002E+0x002A:", [f"{(value - value_2a):08x}" for value in values_2e])
    print("0x002C^0x002A:", [f"{(value ^ value_2a):08x}" for value in values_2c])
    print("0x002E^0x002A:", [f"{(value ^ value_2a):08x}" for value in values_2e])
    # print(values_2c[-1] - values_2e[-1])  # this is +- 8 or 24

    val_2c = bytearray(20)
    val_2e = bytearray(20)
    for i, x in enumerate(["49454d10", "10000130", "02018000", "450200a0", "ffffff18"]):
        val_2c[i * 4 : (i + 4) * 4] = struct.pack(format, value_2a ^ int(x, 16))

    for i, x in enumerate(["35504603", "00000000", "00000000", "00000000", "ffffff00"]):
        val_2e[i * 4 : (i + 4) * 4] = struct.pack(format, value_2a ^ int(x, 16))

    print("0x002C 0x" + "".join([f"{x:02x}" for x in val_2c]))
    print("0x002E 0x" + "".join([f"{x:02x}" for x in val_2e]))


def main_old():
    def dummy(Value_2a, Value_2c, Value_2e):
        print([f"{(value - Value_2a[0]):08x}" for value in Value_2c])
        print([f"{(value - Value_2a[0]):08x}" for value in Value_2e])

        Value_2a = (0x09E9C428,)
        Value_2c = (
            0x40AC8938,
            0x19E9C518,
            0x0BE84428,
            0x4CEBC488,
            0xF6163B30,
        )
        Value_2e = (
            0x3CB9822B,
            0x09E9C428,
            0x09E9C428,
            0x09E9C428,
            0xF6163B28,
        )
        dummy(Value_2a, Value_2c, Value_2e)

        Value_2a = (0x8F5AC278,)
        Value_2c = (
            0xC61F8F68,
            0x9F5AC348,
            0x8D5B4278,
            0xCA58C2D8,
            0x70A53D60,
        )
        Value_2e = (
            0xBA0A847B,
            0x8F5AC278,
            0x8F5AC278,
            0x8F5AC278,
            0x70A53D78,
        )
        dummy(Value_2a, Value_2c, Value_2e)

        Value_2a = (0x7F20674C,)
        Value_2c = (
            0x36652A5C,
            0x6F20667C,
            0x7D21E74C,
            0x3A2267EC,
            0x80DF9854,
        )
        Value_2e = (
            0x4A70214F,
            0x7F20674C,
            0x7F20674C,
            0x7F20674C,
            0x80DF984C,
        )
        dummy(Value_2a, Value_2c, Value_2e)

        Value_2a = (0xAECBF229,)
        Value_2c = (
            0xE78EBF39,
            0xBECBF319,
            0xACCA7229,
            0xEBC9F289,
            0x51340D31,
        )
        Value_2e = (
            0x9B9BB42A,
            0xAECBF229,
            0xAECBF229,
            0xAECBF229,
            0x51340D29,
        )
        dummy(Value_2a, Value_2c, Value_2e)

        Value_2a = (0x84BBFD60,)
        Value_2c = (
            0xCDFEB070,
            0x94BBFC50,
            0x86BA7D60,
            0xC1B9FDC0,
            0x7B440278,
        )
        Value_2e = (
            0xB1EBBB63,
            0x84BBFD60,
            0x84BBFD60,
            0x84BBFD60,
            0x7B440260,
        )
        dummy(Value_2a, Value_2c, Value_2e)

        Value_2a = (0x785F8078,)
        Value_2c = (
            0x311ACD68,
            0x685F8148,
            0x7A5E0078,
            0x3D5D80D8,
            0x87A07F60,
        )
        Value_2e = (
            0x4D0FC67B,
            0x785F8078,
            0x785F8078,
            0x785F8078,
            0x87A07F78,
        )
        dummy(Value_2a, Value_2c, Value_2e)


if __name__ == "__main__":

    a, lst, lst_68, lst_lumix_lab = parse_file()

    # for d in lst:
    # dummy2(d)
    # val_2c, val_2e = hash1(d[42])
    # print(d[44])
    # print(val_2c)
    # print(d[46])
    # print(val_2e)
    import pprint

    pprint.pprint(lst_lumix_lab)
    for d in lst_lumix_lab:
        dummy_lumix_lab(d)

    # pprint.pprint(lst_68)
    # for x in lst_68:
    #     if x["gatt_handle"] == 68:
    #         print(f"{x['gatt_handle']} 0x" + "".join([f"{y:02x}" for y in x["data"]]))
    #         print(struct.unpack(">HHHHH", x["data"]))
    #         # 0xe8070c0d_080a183c_0000
