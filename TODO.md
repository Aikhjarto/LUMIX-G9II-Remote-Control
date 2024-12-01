## photostyle2
photostyle2 value="standard, value2="11/invalid/0/0/0/0/0/hidden/hidden/hidden/hidden/0/0/hidden/hidden/hidden/hidden/iso//hidden//hidden/hidden/hidden/hidden/hidden"

getsetting photostyle2 returns
<?xml version="1.0" encoding="UTF-8"?>
<camrply><result>ok</result><settingvalue photostyle2="standard">11/invalid/invalid/invalid/invalid/invalid/invalid/hidden/hidden/hidden/hidden/invalid/invalid/hidden/hidden/hidden/hidden/iso//hidden//hidden/hidden/hidden/hidden/hidden</settingvalue></camrply>


## Get files via UPNP from camera.

https://github.com/flyte/upnpclient

https://github.com/tenable/upnp_info/blob/master/upnp_info.py

https://www.electricmonk.nl/log/2016/07/05/exploring-upnp-with-python/

https://www.lesbonscomptes.com/upmpdcli/libupnpp-python/upnpp-python.html

https://github.com/hswlab/dlna-browser-net/tree/v2.9.0

https://play.google.com/store/apps/details?id=com.samueljhuf.upnp_explorer&hl=de_AT

https://github.com/StevenLooman/python-didl-lite/blob/master/didl_lite/didl_lite.py

```
def list_directory(device: upnpy.ssdp.SSDPDevice.SSDPDevice):
    service = device.services['ContentDirectory']
    #service.actions()
    action = service.actions['Browse']
    upnpy.soap.SOAP.send(service, action, ObjectID=0, BrowseFlag="BrowseDirectChildren", 
                         StartingIndex=0, Filter='*', RequestedCount=10, SortCriteria='')
    
    for argument in action.arguments:
        print(argument.name, argument.direction, argument.related_state_variable, argument.return_value)
```
