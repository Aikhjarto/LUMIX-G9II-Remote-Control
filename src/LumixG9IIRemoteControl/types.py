from typing import Dict, Literal, TypedDict, Union

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

# file format identifiers used in the camera as obtained from capabilities.xml
CameraFileformatIdentfiers = Literal[
    "CAM_ORG",
    "CAM_MPO_JPG",
    "CAM_MPO",
    "CAM_RAW_JPG",
    "CAM_RAW",
    "CAM_HSP",
    "CAM_HSP_JPG: str,CAM_HSP_RAW_JPG",
    "CAM_HSP_RAW",
    "CAM_FOCUS_SELECT_MP4",
    "CAM_AVC_MP4_LPCM_ORG: str,CAM_AVC_MP4_XK_ORG",
    "CAM_AVC_MP4_4K_ORG",
    "CAM_AVC_MP4_ORG",
    "CAM_AVC_TS_HP_ORG",
    "CAM_AVC_MOV_ORG",
]

MyResource = TypedDict(
    "MyResource", {"additional_info": Dict[str, str], "res": didl_lite.Resource}
)
CameraContentItemResource = Dict[
    Union[CameraFileformatIdentfiers, Literal["CAM_TN", "CAM_LRGTN"]], MyResource
]

CameraContentItem = TypedDict(
    "CameraContentItem",
    {
        "resources": CameraContentItemResource,
        "didl_object": Union[didl_lite.ImageItem, didl_lite.Movie, didl_lite.Container],
        "index": int,
    },
)
