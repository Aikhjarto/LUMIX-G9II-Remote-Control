import http.server
import logging
import pprint
import socket
import socketserver
from threading import Lock
from typing import Dict

import defusedxml.ElementTree

from .configure_logging import logger


class Server(socketserver.ThreadingTCPServer):
    """
    Attributes:
    -----------
    cached_properties: Dict[str, str]
    Importante values:
    key: X_Panasonic_Cam_Sync: Union["lens_Update", "lens_Deta", "lens_Atta"]
    """

    # allow for rapid stop/start cycles during debugging
    # Assumption is, that no other process will start listening on `port` during restart of this script
    allow_reuse_address = True

    # allow IPv4 and IPv6
    address_family = socket.AF_INET

    def __init__(
        self,
        *args,
        callback=None,
        expected_UDN=None,
        expected_remote_host=None,
        **kwargs,
    ):

        self.cached_properties: Dict[str, str] = {}
        self.message_callback = callback
        self.expected_UDN = expected_UDN
        self.expected_remote_host = expected_remote_host

        self.my_lock = Lock()
        super().__init__(*args, **kwargs)


def start_server(port):
    # start server
    with Server(("", port), HTTPRequestHandler) as httpd:
        httpd.serve_forever()


class HTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    server: Server

    def do_NOTIFY(self):
        payload = self.rfile.read(int(self.headers.get("content-length")))
        logger.debug(
            "NOTIFY Message for path %s\nHeaders: \n%s\nPayload:\n%s\n",
            self.path,
            self.headers,
            payload,
        )
        if (
            self.headers["NT"] == "upnp:event"
            and self.headers["NTS"] == "upnp:propchange"
        ):

            # Example text with three properties
            #
            # <e:propertyset xmlns:e="urn:schemas-upnp-org:event-1-0">
            #   <e:property>
            #     <SourceProtocolInfo>http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_LRG;DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=00900000000000000000000000000000,http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_MED;DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=00900000000000000000000000000000,http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_SM;DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=00900000000000000000000000000000,http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_TN;DLNA.ORG_OP=01;DLNA.ORG_CI=1;DLNA.ORG_FLAGS=00900000000000000000000000000000,http-get:*:application/octet-stream,http-get:*:video/mp4:DLNA.ORG_PN=AVC_MP4_BL_L31_HD_AAC;DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=01100000000000000000000000000000,http-get:*:video/mp4:DLNA.ORG_PN=AVC_MP4_MP_HD_1080i_AAC;DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=01100000000000000000000000000000</SourceProtocolInfo>
            #   </e:property>
            #   <e:property>
            #     <SinkProtocolInfo></SinkProtocolInfo>
            #   </e:property>
            #   <e:property>
            #     <CurrentConnectionIDs>0</CurrentConnectionIDs>
            #   </e:property>
            # </e:propertyset>

            # NOTIFY /Camera/event HTTP/1.1
            # HOST: 192.168.7.160:49153
            # CONTENT-TYPE: text/xml; charset="utf-8"
            # CONTENT-LENGTH: 164
            # NT: upnp:event
            # NTS: upnp:propchange
            # SID: uuid:DEADBEEF-0000-1000-8000-1234567890AB
            # SEQ: 8
            # CONNECTION: close
            #
            # <e:propertyset xmlns:e="urn:schemas-upnp-org:event-1-0">
            #   <e:property>
            #     <X_Panasonic_Cam_VRec>done</X_Panasonic_Cam_VRec>
            #   </e:property>
            # </e:propertyset>
            # HTTP/1.1 200 OK

            # check if MAC-adress part of SID header matches UDN
            if self.server.expected_UDN is not None:
                assert (
                    self.headers["SID"].split("-")[-1]
                    == self.server.expected_UDN.split("-")[-1]
                ), f"{self.headers['SID'].split('-')[-1]} != {self.server.expected_UDN.split('-')[-1]}"

            # check if IP address match
            if self.server.expected_remote_host:
                assert self.connection.getpeername()[0] == socket.gethostbyname(
                    self.server.expected_remote_host
                ), f"{self.connection.getpeername()[0]} != {socket.gethostbyname(self.server.expected_remote_host)}"

            et = defusedxml.ElementTree.fromstring(payload)
            namespaces = {"e": "urn:schemas-upnp-org:event-1-0"}
            if et.tag == "{urn:schemas-upnp-org:event-1-0}propertyset":
                list_of_changed_properties = et.findall("e:property", namespaces)
                for prop in list_of_changed_properties:
                    for tmp in prop.findall(".//"):
                        self.server.cached_properties[tmp.tag] = tmp.text
                        if callable(self.server.message_callback):
                            self.server.message_callback((tmp.tag, tmp.text))

            else:
                logger.error(
                    "Unknown message for path %s\nHeaders: \n%s\nPayload:\n%s\n",
                    self.path,
                    self.headers,
                    payload,
                )
        else:
            logger.debug(
                "NOTIFY Message for path %s\nHeaders: \n%s\nPayload:\n%s\n",
                self.path,
                self.headers,
                payload,
            )
        self.send_response_only(200)
