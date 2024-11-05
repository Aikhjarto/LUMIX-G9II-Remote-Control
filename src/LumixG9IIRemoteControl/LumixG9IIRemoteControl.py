import argparse
import logging
import math
import pprint
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import xml.etree.ElementTree
from typing import Dict, List, Tuple, Union

import defusedxml.ElementTree
import requests
import upnpy.ssdp.SSDPDevice
import upnpy.utils
import zmq
from didl_lite import didl_lite

from LumixG9IIRemoteControl.helpers import get_local_ip
from LumixG9IIRemoteControl.http_event_consumer import HTTPRequestHandler, Server

logging.basicConfig()
logger = logging.getLogger()
logger.setLevel("INFO")


FocusSteps = ["wide-fast", "wide-normal", "tele-fast", "tele-normal"]


def find_lumix_camera_via_sspd(
    return_hostname=True,
) -> List[Union[str, upnpy.ssdp.SSDPDevice.SSDPDevice]]:
    upnp = upnpy.UPnP()
    devices = upnp.discover()
    hostnames = set()
    for device in devices:
        split = urllib.parse.urlsplit(
            upnpy.utils.parse_http_header(device.response, "Location")
        )
        if split.path == "/Lumix/Server0/ddd":
            if return_hostname:
                hostnames.add(split.hostname)
            else:
                hostnames.add(device)

    if len(hostnames) == 0:
        raise RuntimeError("No camera found")
    elif len(hostnames) == 1:
        return hostnames.pop()
    else:
        raise ValueError(f"Multiple candidates found: {hostnames}.")


class LumixG9IIRemoteControl:

    def __init__(
        self,
        local_device_name: str = "DummyDevice",
        number_retry_if_busy=10,
        host=None,
        auto_connect=False,
        min_drag_continue_interval=0.2,
    ):
        self._auto_connect = auto_connect
        self.host = host

        # Drag continue events can come from GUI more rapidly than Wi-Fi transport to 
        # camera permits. Thus set a minimum interval an discard intermediate 
        # coordinates.
        self.min_drag_continue_interval: float = float(min_drag_continue_interval)
        self._last_drag_continue_timestamp: float = None

        self._headers = {"User-Agent": "LUMIX Sync", "Connection": "Keep-Alive"}

        # caches for camera capabilities
        self._capability_tree: defusedxml.ElementTree = None
        self._allmenu_tree: defusedxml.ElementTree = None
        self._language_tree: defusedxml.ElementTree = None
        self._curmenu_tree: defusedxml.ElementTree = None
        self._external_teleconverter_tree: defusedxml.ElementTree = None
        self._touch_type_tree: defusedxml.ElementTree = None

        # static camera parameters
        self.device_info_dict: Dict[str, str] = {}

        # volatile camera parameters
        self.camera_state_dict: Dict[str, str] = {}
        self.lens_dict: Dict[str, str] = []
        self._lens_data: List[str] = []
        self.touch_type: List[str] = []

        self.local_device_name: str = local_device_name

        # Request state thread handles
        # camera hold connection as long as state is requested periodically
        self._request_lock = threading.Lock()
        self._keepalive: bool = True
        self._state_thread: threading.Thread = None

        # parameters for retry behaviour is err_busy is returned by camera
        self.number_retry_if_busy: int = number_retry_if_busy
        self.retry_busy_interval: float = 1

        # handle to GUI
        self._stream_viewer_subprocess: subprocess.Popen = None

        # handles to thread capturing camera events
        self._http_server: Server = None
        self._event_thread: threading.Thread = None

        self._zmq_context = zmq.Context()
        self._zmq_socket = self._zmq_context.socket(zmq.PAIR)
        self._zmq_socket.connect("tcp://localhost:5556")
        self._zmq_thd = threading.Thread(
            target=self._zmq_consumer_function, daemon=True
        )
        self._zmq_thd.start()

        if auto_connect:
            self.connect(host)

    def _zmq_consumer_function(self):
        while True:
            try:
                event = self._zmq_socket.recv_pyobj()
                # logger.info("Received via zmq: %s", event)
                if "streamviewer_event" in event:
                    event_type = event["streamviewer_event"]
                    x = event["x"]
                    y = event["y"]
                    if event_type == "click":
                        self.lcd_on()
                        self.send_touch_coordinate(x, y)
                    else:
                        # 'drag_start', 'drag_continue', 'drag_stop'
                        if event_type == "drag_start":
                            self._last_drag_continue_timestamp = time.time()
                        elif event_type == "drag_continue":
                            if (
                                time.time()
                                > self._last_drag_continue_timestamp
                                + self.min_drag_continue_interval
                            ):
                                self._last_drag_continue_timestamp = time.time()
                            else:
                                continue
                        logger.info("Received via zmq: %s", event)
                        value = event_type.split("_")[-1]
                        self.lcd_on()
                        self.send_touch_drag(value, x, y)
            except Exception as e:
                logger.error(traceback.format_exception(e))

    def __str__(self):
        try:
            return (
                f"{self.device_info_dict['manufacturer']} "
                f"{self.device_info_dict['modelName']} "
                f"{self.device_info_dict['modelNumber']} "
                f"{self.device_info_dict['friendlyName']} "
                f"{self.device_info_dict['serialNumber']} "
                f"{self.device_info_dict['UDN']}"
            )
        except KeyError:
            return type(self)

    def _requires_connected(func):
        def _decorated(*args, **kwargs):
            if "X-SESSION_ID" not in args[0]._headers:
                if not args[0]._auto_connect:
                    raise RuntimeError("Not connected to camera. Use connect() first")
                else:
                    args[0].connect(args[0].host)
            return func(*args, **kwargs)

        return _decorated

    def _requires_host(func):
        def _decorated(*args, **kwargs):
            if not args[0]._host:
                if not args[0]._auto_connect:
                    raise RuntimeError("Not connected to camera. Use connect() first")
                else:
                    logger.info("Camera hostname/IP not given. Searching for device")
                    args[0].host = find_lumix_camera_via_sspd()
            return func(*args, **kwargs)

        return _decorated

    @property
    def cached_properties(self):
        if self._http_server:
            return self._http_server.cached_properties

    @property
    def host(self):
        return self._host

    @host.setter
    def host(self, host):
        self._host = host
        self._cam_cgi = f"http://{self._host}/cam.cgi"
        return self._host

    def connect(self, host=None):
        """
        Parameters
        ----------
        host: str
            If connected directly, camera is accessible via IP 192.168.54.1
            If the device, where this program is running on and the camera are
            connected via the same router or accesspoint, the camera is accessible via
            the hostname "mlbel".
        """
        if self.host is None:
            if host is None:
                logger.info("Camera hostname/IP not given. Searching for device")
                host = find_lumix_camera_via_sspd()
            else:
                self.host = host

        with self._request_lock:
            self._get_device_info_via_ddd()

            ret = requests.get(
                self._cam_cgi,
                headers=self._headers,
                params={"mode": "accctrl", "type": "req_acc_g"},
            )
            self._check_ret_ok(ret)

            value = (
                "e4bf9a00e1b8e700e1baee19e1baf304e9a6"
                "ee04fcbaee04e1caec04e3bbee04e9baeb00"
            )
            value2 = "2ebe8e72"

            ret = requests.get(
                self._cam_cgi,
                headers=self._headers,
                params={
                    "mode": "accctrl",
                    "type": "req_acc_e",
                    "value": value,
                    "value2": value2,
                },
            )

            assert ret.ok
            data = ret.text.strip().split(",")
            assert data[1] == self.device_info_dict["friendlyName"]
            assert data[2] == "remote"
            assert data[3] == "open"

            ret = requests.get(
                self._cam_cgi,
                headers=self._headers,
                params={
                    "mode": "accctrl",
                    "type": "req_acc_e",
                    "value": value,
                    "value2": value2,
                },
            )
            data = self._check_ret_ok(ret)
            assert data[0] == self.device_info_dict["friendlyName"]
            assert data[1] == "remote"
            assert data[2] == "open"
            self._headers["X-SESSION_ID"] = data[3]

            ret = requests.get(
                self._cam_cgi,
                headers=self._headers,
                params={
                    "mode": "setsetting",
                    "type": "device_name",
                    "value": self.local_device_name,
                },
            )
            self._check_ret_ok(ret)

        self._state_thread = threading.Thread(
            target=self._get_state_thread, daemon=True
        )
        self._state_thread.start()

        self._get_capability()
        self._get_allmenu()
        self.get_lens()
        self.get_external_teleconverter()
        self.get_touch_type()
        self._get_curmenu()
        self.set_local_language()
        self._subscribe_to_camera_events()
        logger.info("Connected to %s", str(self))

    def disconnect(self):
        self._keepalive = False
        self._host = None
        self._cam_cgi = None
        if "X-SESSION_ID" in self._headers:
            del self._headers["X-SESSION_ID"]

    def _get_state_thread(self):
        while self._keepalive:
            time.sleep(2)
            with self._request_lock:
                logger.debug(
                    "update state and curmenu from camera %s",
                    self.device_info_dict["friendlyName"],
                )
                self.get_state()
                self._get_curmenu()

    @_requires_host
    def _get_device_info_via_ddd(self):
        ret = requests.get(f"http://{self._host}:60606/Lumix/Server0/ddd")
        assert ret.ok
        et = defusedxml.ElementTree.fromstring(ret.text)
        self.device_info_dict = {}

        for i in et.findall("{urn:schemas-upnp-org:device-1-0}device/*"):
            key = i.tag[i.tag.find("}") + 1 :]
            self.device_info_dict[key] = i.text

        return self.device_info_dict

    @_requires_connected
    def _get_capability(self):
        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={"mode": "getinfo", "type": "capability"},
        )
        self._capability_tree = self._check_ret_ok(ret)

    @_requires_connected
    def _get_allmenu(self):
        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={"mode": "getinfo", "type": "allmenu"},
        )
        self._allmenu_tree = self._check_ret_ok(ret)

    @_requires_connected
    def _get_curmenu(self):
        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={"mode": "getinfo", "type": "curmenu"},
        )
        self._curmenu_tree = self._check_ret_ok(ret)
        self._curmenu_list = [i.attrib for i in self._curmenu_tree[1][:]]

    @_requires_connected
    def get_state(self):
        ret = requests.get(
            self._cam_cgi, headers=self._headers, params={"mode": "getstate"}
        )
        et = self._check_ret_ok(ret)

        self.camera_state_dict = {}
        for i in et.find("state"):
            self.camera_state_dict[i.tag] = i.text

        return self.camera_state_dict

    @_requires_connected
    def get_lens(self):
        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={"mode": "getinfo", "type": "lens"},
        )
        data = self._check_ret_ok(ret)
        self._lens_data = data
        self.lens_dict = {
            "maximum_focal_length": data[6],
            "minmal_focal_length": data[7],
            "mount": data[12],
            "name": data[13],
            "manufactorer": data[14],
            "serial_number": data[15],
        }
        # TODO: decode other fields
        return data[1:]

    @_requires_connected
    def get_external_teleconverter(self):
        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={"mode": "getsetting", "type": "ex_tele_conv"},
        )
        self._external_teleconverter_tree = self._check_ret_ok(ret)
        return self._external_teleconverter_tree

    @_requires_connected
    def get_touch_type(self):
        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={"mode": "getsetting", "type": "touch_type"},
        )
        self.touch_type = self._check_ret_ok(ret)
        return self.touch_type

    @_requires_connected
    def send_touch_drag(self, value: str, x: int, y: int):
        params = {
            "mode": "camctrl",
            "type": "touch_trace",
            "value": value,
            "value2": f"{x:d}/{y:d}",
        }

        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params=params,
        )
        data = self._check_ret_ok(ret)
        logger.debug("drag %s move to coordinates %s", value, data)
        return data

    @_requires_connected
    def send_touch_trace(self, coordinate_list: List[Tuple[int, int]]):
        """
        Simulate moving one finger across the screen.
        """
        assert len(coordinate_list) > 1

        params = {"mode": "camctrl", "type": "touch_trace"}
        for idx, coordinates in enumerate(coordinate_list):
            if idx == 0:
                params["value"] = "start"
            elif idx == len(coordinate_list) - 1:
                params["value"] = "stop"
            else:
                params["value"] = "continue"
            params["value2"] = f"{coordinates[0]}/{coordinates[1]}"

            ret = requests.get(
                self._cam_cgi,
                headers=self._headers,
                params=params,
            )
            data = self._check_ret_ok(ret)
            time.sleep(0.2)
            # data is [0,0] for value start and stop
            # data is [557,469] representing the value that where actually set
            if 0 < idx < len(coordinate_list):
                logger.info("moved to coordinates %s", data)

    @_requires_connected
    def send_touch_coordinate(self, x: int, y: int):
        """
        Send a command emulation a touch with the finger on the camera's screen.
        The coordinates x and y can have values from 0 to 1000.

        Parameters
        ----------
        x: int
            x is measured from left to right
        y: int
            y is measured from top to bottom

        Notes
        -----
        It is not possible to touch the control elements on the right side with this
        function.
        """
        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={
                "mode": "camctrl",
                "type": "touch",
                "value": f"{x:d}/{y:d}",
                "value2": "on",
            },
        )
        self._check_ret_ok(ret)

    # def lcd_off(self):
    #     # TODO: throws err_param
    #     ret = requests.get(
    #         self._cam_cgi,
    #         headers=self._headers,
    #         params={"mode": "camcmd", "value": "lcd_off"},
    #     )
    #     self._check_ret_ok(ret)
    @_requires_connected
    def lcd_on(self):
        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={"mode": "camcmd", "value": "lcd_on"},
        )
        self._check_ret_ok(ret)

    @_requires_connected
    def menu_entry(self):
        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={"mode": "camcmd", "value": "menu_entry"},
        )
        self._check_ret_ok(ret)

    @_requires_connected
    def video_recstart(self):
        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={"mode": "camcmd", "value": "video_recstart"},
        )
        self._check_ret_ok(ret)

    @_requires_connected
    def video_recstop(self):
        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={"mode": "camcmd", "value": "video_recstop"},
        )
        self._check_ret_ok(ret)

    @_requires_connected
    def set_recmode(self):
        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={"mode": "camcmd", "value": "recmode"},
        )
        self._check_ret_ok(ret)

    @_requires_connected
    def set_playmode(self):
        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={"mode": "camcmd", "value": "playmode"},
        )
        self._check_ret_ok(ret)

    @_requires_connected
    def start_stream(self, port=49152, spawn_viewer=False):
        # TODO: maybe not working with all ports as some ports are used by other
        # protocols, like 50001, or 60606. However, command never fails. Thus,
        # find other ways to catch th error.

        # only works in recmode
        self.set_recmode()

        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={"mode": "startstream", "value": {port}},
        )
        self._check_ret_ok(ret)

        # TODO: stop stream when window is closed
        if spawn_viewer:
            if (
                self._stream_viewer_subprocess is None
                or self._stream_viewer_subprocess.poll() is not None
            ):
                self._stream_viewer_subprocess = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "LumixG9IIRemoteControl.StreamViewer",
                        "-p",
                        str(port),
                    ],
                )

    @_requires_connected
    def stop_stream(self):
        ret = requests.get(
            self._cam_cgi, headers=self._headers, params={"mode": "stopstream"}
        )
        self._check_ret_ok(ret)

    @_requires_connected
    def move_focus(self, step):
        """
        Move focus in predefined steps.

        Parameters
        ---------
        step: Union[Literal["wide-normal"],Literal["wide-fast"],Literal["tele-fast"],Literal["tele-normal"]]
        """

        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={"mode": "camctrl", "type": "focus", "value": step},
        )
        try:
            data = self._check_ret_ok(ret)
        except ValueError as e:
            traceback.print_exception(e)
            logger.error(f"{step} is not in {FocusSteps}")
            return
        logger.info("Focus values: %s", data)
        # ok,564,1024,0,0,1024,1000/295,500/537,300/779,0/0,0/0,0/0,0/0
        # TODO: decode all values. First value seems to be focus distance starting from zero
        return data

    @_requires_connected
    def capture(self):
        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={"mode": "camcmd", "value": "capture"},
        )
        self._check_ret_ok(ret)

    @_requires_connected
    def oneshot_af(self):
        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={"mode": "camcmd", "value": "oneshot_af"},
        )
        self._check_ret_ok(ret)

    @_requires_connected
    def touchcapt_ctrl(self, value):
        """
        value: Union["enable", "disable", "off"]
        """
        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={"mode": "camctrl", "type": "touchcapt_ctrl", "value": value},
        )
        self._check_ret_ok(ret)

    @_requires_connected
    def touchae_ctrl(self, value):
        """
        Send a send_touch_coordinate after touchae_ctrl('on') to move the auto exposure measurement
        to a certain point.

        Then send touchae_ctrl('off')
        Paramters
        ---------
        value: Union["on", "off"]


        """
        # TODO: when set to "on", Panasonic Lumix Sync also sends autoreviewunlock
        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={"mode": "camctrl", "type": "touchae_ctrl", "value": value},
        )
        self._check_ret_ok(ret)

    @_requires_connected
    def set_assistance_display(self, value, value2):
        """
        Only valid in manual focus mode, use value='current_auto' to engage this mode

        Parameters:
        -----------
        value: Union["current_auto", "pinp", "full", "off"]
        value2 : Union["mf_asst/0/0", "digital_scope/0/0"]
        """
        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={
                "mode": "camctrl",
                "type": "asst_disp",
                "value": value,
                "value2": value2,
            },
        )
        try:
            data = self._check_ret_ok(ret)
            # data: ok,off,300,619,471,600,300
            # off can be pinp or full
            # TODO check values and cache them
        except ValueError as e:
            traceback.print_exception(e)
            logger.error(f"{value} is not in ['current_auto', 'pinp', 'full', 'off']")

    @_requires_connected
    def capture_cancel(self):
        # TODO:: a long exposure cannot be canceld, but maybe a series or stepmotion capture can be canceld
        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={"mode": "camcmd", "value": "capture_cancel"},
        )
        self._check_ret_ok(ret)

    @_requires_connected
    def autoreviewunlock(self):
        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={"mode": "camcmd", "value": "autoreviewunlock"},
        )
        self._check_ret_ok(ret)

    @_requires_connected
    def autoreviewunlock(self):
        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={"mode": "camcmd", "value": "touchrelease"},
        )
        self._check_ret_ok(ret)

    @_requires_connected
    def get_content_info(self):
        """

        **current_position** does roughly match on-screen display when in play mode,
        but has a sligthy different start, depending on which direction was scrolled last.
        When scrolling upwards, current_position is one index higher than index on display.
        When scrolling downwards, current_position is three lower than index on display.
        Images in Picture Groups are counted as one picture with current_position, but indivdually
        with the index on the display.

        **total_content_number** does match on-screen disply when in play mode.

        **content_number** is less than total_content_number, maybe it counts raw and JPG as one,
        it seems, that current_position would wrap with content_number.


        Returns
        -------
        dict: {"current_position": 126, "total_content_number": 388, "content_number": 127}


        """
        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={"mode": "get_content_info"},
        )
        et = self._check_ret_ok(ret)
        d = {}
        for item in et:
            if item.tag != "result":
                d[item.tag] = int(item.text)
        return d

    def _check_ret_ok(
        self, ret: requests.Response, N=0
    ) -> Union[xml.etree.ElementTree.Element, List[str]]:
        assert ret.ok
        assert ret.headers["Server"] == "Panasonic"
        if (
            ret.headers["Content-Type"] == "text/xml"
            or ret.headers["Content-Type"] == "xml"
        ):
            et = defusedxml.ElementTree.fromstring(ret.text)
            state = et.find("result").text
            if state == "ok":
                return et
        elif ret.headers["Content-Type"] == "text/plain":
            data = ret.text.strip().split(",")
            state = data[0]
            if state == "ok":
                return data[1:]
        else:
            raise RuntimeError(f'Unexpected content type {ret.headers["Content-Type"]}')

        if state == "err_busy" and N < self.number_retry_if_busy:
            logger.warning(
                f"{ret.url} is busy, auto-retry {N+1}/{self.number_retry_if_busy} in 1 second"
            )
            time.sleep(self.retry_busy_interval)
            ret2 = ret.connection.send(ret.request)
            return self._check_ret_ok(ret2, N=N + 1)
        else:
            if state == "err_param":
                raise ValueError(f"{ret.url} resulted in {state}")
            elif state == "err_reject":
                raise KeyError(
                    f"{ret.url} resulted in {state}, "
                    "indicating that operation is not possible in current state of the camera"
                )
            else:
                raise RuntimeError(
                    f"{ret.url} resulted in {state}. Full error: {ret.text}"
                )

    def set_local_language(self, language_code=None):
        """
        Select the language for translating camera commands into a human-readable form.
        Used mainly by `print_set_setting_commands()`.
        """
        if language_code is None:
            language_code = self._allmenu_tree.find(
                "menuset/titlelist/language[@default='yes']"
            ).attrib["code"]

        self._language_tree = self._allmenu_tree.find(
            f"menuset/titlelist/language[@code='{language_code}']"
        )
        if self._language_tree is None:
            language_codes_available = [
                child.attrib["code"]
                for child in self._allmenu_tree.findall("./menuset/titlelist/language")
            ]
            logger.error(
                "language code '%s' is not in available codes '%s'",
                language_code,
                language_codes_available,
            )

    def get_localized_setting_name(self, title_id: str) -> str:
        """
        Translates the interal description of an item in allmenu.xml
        to a human-readable from.
        """

        item = self._language_tree.find(f"./title[@id='{title_id}']")
        if item is not None:
            return item.text
        else:
            return None

    def print_set_setting_commands(self):
        """
        Prints a list of options for the `set_setting()` functionality.
        """
        pprint.pprint(self.get_setsetting_commands())

    @_requires_connected
    def get_setsetting_commands(
        self,
    ) -> Dict[str, List[Union[Tuple[str,], Tuple[str, str]]]]:
        data = {}
        for item in self._allmenu_tree.findall("menuset//*[@cmd_mode='setsetting']"):
            cmd_type = item.attrib["cmd_type"]

            if cmd_type not in data:
                group_item = self._allmenu_tree.find(
                    f"menuset//*[@cmd_type='{cmd_type}']/../.."
                )
                if "title_id" in group_item.attrib:
                    group_title_id = group_item.attrib["title_id"]
                    name = self.get_localized_setting_name(group_title_id)
                else:
                    name = None
                data[cmd_type] = {"name": name, "values": []}

            # print(item.attrib)
            if "cmd_value2" in item.attrib:
                data[cmd_type]["values"].append(
                    (item.attrib["cmd_value"], item.attrib["cmd_value2"])
                )
            elif "cmd_value" in item.attrib:
                data[cmd_type]["values"].append((item.attrib["cmd_value"], None))
        return data

    @_requires_connected
    def set_setting(self, setting: str, value, value2=None):
        """
        Set a configureable camera item.

        To get a list of possiblities, use `print_set_setting_commands()`.

        Parameters
        ----------
        settings: str

        value: Any

        value2: Any

        Notes
        -----
        Not all settings are valid in all states of the camera.
        """

        params = {"mode": "setsetting", "type": setting, "value": value}
        if value2 is not None:
            params["value2"] = value2
        ret = requests.get(self._cam_cgi, headers=self._headers, params=params)
        self._check_ret_ok(ret)

    @_requires_connected
    def get_setting(self, setting) -> dict:
        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={"mode": "getsetting", "type": setting},
        )
        return self._check_ret_ok(ret)[1].attrib

    @_requires_connected
    def select_sd_card(self, value):
        return self.set_setting("current_sd", value=f"sd{value:d}")

    @_requires_connected
    def get_settings(self) -> Dict[str, str]:
        data = {}
        lst = list(self.get_setsetting_commands().keys())
        settings_not_in_get_set_settings = [
            "play_sort_mode",
            "qmenu_disp_style",
            "photostyle2",
        ]
        "play_sort_mode can be file_no or date"
        lst.extend(settings_not_in_get_set_settings)

        for setsetting_cmd in lst:
            try:
                data.update(self.get_setting(setsetting_cmd))
            except RuntimeError:
                logger.error("Could not read %s", setsetting_cmd)
        return data

    def print_current_settings(self):
        data = self.get_settings()
        pprint.pprint(data)

    @_requires_host
    def _subscribe_to_camera_events(self):
        request = requests.Request(
            method="SUBSCRIBE",
            url=f"http://{self._host}:60606/Server0/CMS_event",
            headers={
                "User-Agent": "Panasonic Android/1 DM-CP",
                "CALLBACK": f"<http://{get_local_ip()}:49153/Camera/event>",
                "NT": "upnp:event",
                "TIMOEUT": "Second-300",
            },
        )
        prepared_request = request.prepare()
        session = requests.Session()
        ret = session.send(prepared_request)
        assert ret.ok

        if self._event_thread is None:
            self._event_thread = threading.Thread(
                target=self._run_event_capture_server_blocking,
                args=(49153,),
                daemon=True,
            )
            self._event_thread.start()

    @_requires_connected
    def raw_img_send_enable(self):
        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={"mode": "setsetting", "type": "raw_img_send", "value": "enable"},
        )
        self._check_ret_ok(ret)

    def get_capability(self):
        # TODO analyze whats in there (it is the same in rec and play mode)
        ret = requests.get(
            self._cam_cgi,
            headers=self._headers,
            params={"mode": "getinfo", "type": "capability"},
        )
        return self._check_ret_ok(ret)

    def _camera_event_callback(self, data: Tuple[str, str]):
        """
        SourceProtocolInfo is 'http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_LRG;DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=00900000000000000000000000000000,http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_MED;DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=00900000000000000000000000000000,http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_SM;DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=00900000000000000000000000000000,http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_TN;DLNA.ORG_OP=01;DLNA.ORG_CI=1;DLNA.ORG_FLAGS=00900000000000000000000000000000,http-get:*:application/octet-stream,http-get:*:video/mp4:DLNA.ORG_PN=AVC_MP4_BL_L31_HD_AAC;DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=01100000000000000000000000000000,http-get:*:video/mp4:DLNA.ORG_PN=AVC_MP4_MP_HD_1080i_AAC;DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=01100000000000000000000000000000'

        SinkProtocolInfo is always empty string

        CurrentConnectionIDs is an integer number

        X_Panasonic_Cam_VRec can have string "start" and "done"

        X_Panasonic_Cam_Sync can have the following text:
        busy, update, lens_Update, lens_Deta, lens_Atta, mod_Play, mod_Rec

        lens_update is NOT sent, when a control ring of the lens is moved

        When detatching a lens camera sends: busy, lens_Deta, lens_Update, lens_Deta, lens_Update, update
        When attaching a lens, camera sends: busy, lens_Atta, lens_Update, update, lens_Atta

        busy is sent, when one of the camera is operated manually while a remote connection is still alive. When the manual operation stops, `update` and `lens_Atta` events are sent.
        """
        print(data)
        # TODO: make a more meaningful callback that calls get_lens on lens changes and curmenu on
        # mode changes and locks sending event while busy is active

    @_requires_host
    def _run_event_capture_server_blocking(self, port):

        self._http_server = Server(
            ("", port),
            HTTPRequestHandler,
            callback=self._camera_event_callback,
            expected_UDN=self.device_info_dict["UDN"],
            expected_remote_host=self._host,
        )
        with self._http_server as httpd:
            httpd.serve_forever()

    @_requires_connected
    def query_all_items(self):
        # TODO: continue

        self.raw_img_send_enable()
        content_info_dict = self.get_content_info()
        # {"current_position": 126, "total_content_number": 388, "content_number": 127}
        N_bulk = 50

        for i in range(math.ceil(content_info_dict["total_content_number"] / N_bulk)):
            print(
                i,
                self.query_items(StartingIndex=i * N_bulk, RequestedCount=N_bulk)[-2:],
            )

    @_requires_connected
    def query_items(
        self,
        StartingIndex=0,
        RequestedCount=15,
        age_in_days: int = None,
        rating_list: Tuple[int] = (0,),
        object_id_str="0",
        recgroup_type_string=None,
        auto_set_play_mode=True,
    ):
        """
        Parameters
        ----------
        age_in_days: int
            Zero, means only today's items.
            One means today's and yesterday's items.

        rating_list:
            0 identifies items with no ratings.
            1 identifies items with one star.
            2 identifies items with two star.
            3 identifies items with three star.
            4 identifies items with four star.
            5 identifies items with five star.

        object_id_str:
            '01112122DIR'
            TODO: it ist called container id and in between id and parentID as attribute to
            the element "ns0:item"
            didl-lite can decode that, but i don't get container id, with this script.
            but Lumix sync does get it (i can see it in wireshark).
            Once Lumix Sync requested it, i can connect with this script an get container id too.

        Notes
        -----
        use select_sd_card() to change which sd-card should be queried.

        """

        if auto_set_play_mode:
            state = self.get_state()
            if state["cammode"] != "play":
                self.set_playmode()

        filter_list = []
        if age_in_days:
            filter_list.append(f"type=date,value=relative,value2={age_in_days:d}")
        rating_string = "/".join(map(str, rating_list))
        filter_list.append(f"type=rating,value={rating_string}")
        filter_string = ";".join(filter_list)

        envelop = xml.etree.ElementTree.Element(
            "s:Envelope",
            attrib={
                "xmlns:s": "http://schemas.xmlsoap.org/soap/envelope/",
                "s:encodingStyle": "http://schemas.xmlsoap.org/soap/encoding/",
            },
        )
        body = xml.etree.ElementTree.SubElement(envelop, "s:Body")
        browse = xml.etree.ElementTree.SubElement(
            body,
            "u:Browse",
            attrib={
                "xmlns:u": "urn:schemas-upnp-org:service:ContentDirectory:1",
                "xmlns:pana": "urn:schemas-panasonic-com:pana",
            },
        )
        xml.etree.ElementTree.SubElement(browse, "ObjectID").text = object_id_str
        xml.etree.ElementTree.SubElement(browse, "BrowseFlag").text = (
            "BrowseDirectChildren"
        )
        xml.etree.ElementTree.SubElement(browse, "Filter").text = "*"
        xml.etree.ElementTree.SubElement(browse, "StartingIndex").text = str(
            int(StartingIndex)
        )
        xml.etree.ElementTree.SubElement(browse, "RequestedCount").text = str(
            int(RequestedCount)
        )
        xml.etree.ElementTree.SubElement(browse, "SortCriteria")
        xml.etree.ElementTree.SubElement(browse, "pana:X_FromCP").text = "LumixLink2.0"
        if recgroup_type_string is not None:
            xml.etree.ElementTree.SubElement(browse, "pana:X_RecGroupType").text = (
                recgroup_type_string
            )
        if filter_string is not None:
            xml.etree.ElementTree.SubElement(browse, "pana:X_Filter").text = (
                filter_string
            )
        xml.etree.ElementTree.SubElement(browse, "pana:X_Order").text = (
            "type=date,value=ascend"
        )

        xml.etree.ElementTree.indent(envelop, space=" ")
        xml_string = xml.etree.ElementTree.tostring(
            envelop, xml_declaration=True, encoding="utf-8", short_empty_elements=False
        )
        xml_string = xml_string.replace(b"'", b'"')
        ret = requests.post(
            url="http://192.168.7.211:60606/Server0/CDS_control",
            headers={
                "User-Agent": "Panasonic Android/1 DM-CP",
                "Content-Type": 'text/xml charset="utf-8"',
                "SOAPACTION": '"urn:schemas-upnp-org:service:ContentDirectory:1#Browse"',
            },
            data=xml_string,
        )

        if ret.ok:
            # decode the didl response, which is in a soap envelop
            soap_xml = defusedxml.ElementTree.fromstring(ret.text)
            didl_lite_xml = defusedxml.ElementTree.fromstring(
                soap_xml.find(".//Result").text
            )
            didl_object = didl_lite.from_xml_el(didl_lite_xml)
            UpdateID = int(soap_xml.find(".//UpdateID").text)
            TotalMatches = int(soap_xml.find(".//TotalMatches").text)  # 123
            NumberReturned = int(
                soap_xml.find(".//NumberReturned").text
            )  # max 50, even if more where requested
            return (
                soap_xml,
                didl_lite_xml,
                didl_object,
                TotalMatches,
                NumberReturned,
                ret.text.find("container"),
            )
        else:
            logger.error(
                "Request %s\n resulted in %s \n with answer %s\nEnsure you are in play mode and your filters are correct.",
                pprint.pformat(xml_string.decode()),
                pprint.pformat(ret),
                pprint.pformat(ret.text),
            )

    @_requires_connected
    def get_content_item(self, string, to_file: bool = False) -> bytes:
        # string is like DL01112176.JPG
        # DT01112176.JPG
        ret = requests.get(f"http://{self.host}/{string}", headers=self._headers)
        assert ret.ok
        if to_file:
            with open(string, "b") as f:
                f.write(ret.raw)
        return ret.raw


def setup_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", "-H", type=str, required=False)
    parser.add_argument("--auto-connect", action="store_true", default=False),
    parser.add_argument("--use-full-IPython", action="store_true", default=False)
    return parser


if __name__ == "__main__":

    args = setup_parser().parse_args()

    header = """LumixG9IIRemoteControl: use g9ii<tab> to see your options, e.g.
        g9ii.print_set_setting_commands()
        g9ii.print_current_settings()
        g9ii.set_setting('exposure', -3)
        g9ii.oneshot_af()
        g9ii.capture()
        use '?' instead of brackets to print the helpstring, e.g. g9ii.start_stream?
        """

    if args.use_full_IPython:
        import IPython
        from traitlets.config import Config

        c = Config()
        c.InteractiveShellApp.exec_lines = [
            "import LumixG9IIRemoteControl.LumixG9IIRemoteControl",
            f"g9ii = LumixG9IIRemoteControl.LumixG9IIRemoteControl.LumixG9IIRemoteControl(auto_connect={args.auto_connect}, host={args.host})",
        ]
        c.InteractiveShellApp.hide_initial_ns = False

        c.InteractiveShell.banner2 = header
        IPython.start_ipython(argv=[], local_ns=locals(), config=c)

    else:
        import IPython

        g9ii = LumixG9IIRemoteControl(auto_connect=args.auto_connect, host=args.host)
        IPython.embed(header=header)
    # try:
    #     g9ii.connect(host=args.host)
    # except RuntimeError as e:
    #     traceback.print_exception(e)

    # g9ii.start_stream()
    # g9ii.set_playmode()
    # g9ii.set_recmode()

    # g9ii._state_thread.join()
    # g9ii = LumixG9IIRemoteControl()
    # g9ii._allmenu_tree = defusedxml.ElementTree.parse("../../Dumps/allmenu.xml")
    # g9ii.set_local_language()
