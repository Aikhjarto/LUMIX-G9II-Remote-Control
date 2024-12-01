from typing import Literal, TypedDict, Union

from didl_lite import didl_lite

CamCGISettingKeys = Literal["mode", "type", "value", "value2"]
SetSettingKeys = Literal["type", "value", "value2"]
FocusSteps = Literal["wide-fast", "wide-normal", "tele-fast", "tele_normal"]
CamCGISettingDict = TypedDict(
    "CamCGISettingDict",
    {
        "mode": str,
        "type": str,
        "value": str,
        "value2": str,
        "cmd_mode": str,
        "cmd_type": str,
        "cmd_value": str,
        "cmd_value2": str,
    },
)

ResourceDict = TypedDict(
    "ResourceDict",
    {
        "CAM_RAW_JPG": str,
        "CAM_RAW": str,
        "CAM_TN": str,
        "CAM_LRGTN": str,
        "CAM_ORG": str,
        "CAM_AVC_MP4_ORG": str,
        "OriginalFileName": str,
        "didl_object": Union[
            didl_lite.ImageItem, didl_lite.VideoItem, didl_lite.Container
        ],
        "index": int,
    },
)
