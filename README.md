# LumixG9IIRemoteControl
LumixG9IIRemoteControl is a Python module to control a Panasonic Lumix DC-G9II.

Interactive command-line interface
```sh
python3 -m LumixG9IIRemoteControl.LumixG9IIRemoteControl
```
The camera can output its screen content in recording mode without the overlays as UDP stream.
This stream can be caputerd by either StreamViewer or StreamReceiver

Stream viewer for live stream via Wi-Fi (can be started separately like)
```sh
python3 -m LumixG9IIRemoteControl.StreamViewer
```
or from the command-line interface

Stream receiver if stream via Wi-Fi should not go to the StreamViewer but to another endpoint.
```sh
python3 -m LumixG9IIRemoteControl.StreamReceiver
```

## Installation
```sh
pip install LumixG9IIRemoteControl
```

## Logging Wi-Fi Commands from LumixSync
### Prerequisites
* A Wi-fi Router with [OpenWrt](https://openwrt.org/) and installed package [tcpdump](https://openwrt.org/packages/pkgdata/tcpdump).
* A laptop running Linux and installed [Wireshark](https://www.wireshark.org/).
* A mobile phone running Panasonic's official [LumixSync App](https://www.panasonic.com/global/consumer/lumix/lumix-sync-app.html).

### Setup
* On the laptop execute the following commands (change the IP-adress of your router and the MAC address of your camera accordingly):
```bash
mkfifo /tmp/camtest
sudo wireshark -k -i /tmp/camtest
ssh root@192.168.0.1 "tcpdump -i br-lan ether host a0:cd:f3:e7:7e:48 -U -s0 -w -" > /tmp/camtest
```
* Connect your mobile phone and the DC-G9II to your router.
* Run the Lumix Sync App on the mobile device and see in Wireshark the communication between your mobile phone and the camera in accordance of your actions in the Lumix Sync App.

## Logging Blutooth Commands from LumixSync
In Developer settings on your phone, enable USB Debugging and Bluetooth HCI snoop log.
```sh
adb shell settings put secure bluetooth_hci_log 1
adb shell cmd bluetooth_manager disable
adb shell cmd bluetooth_manager enable
```

### Get Bluetooth logs via adb bugreport
```sh
SUFFIX=$(date -Is)
adb bugreport "bugreport_$SUFFIX"
unzip "bugreport_$SUFFIX" "FS/data/misc/bluetooth/*"
```
Open `*.cfa` file with Wireshark and use `btatt` as display filter

Generating the bugreport will be slow.

### Bluetooth dump using adb dumpsys
Get `btsnooz.py` from https://source.android.com/docs/core/connect/bluetooth/verifying_debugging?hl=de

Download log and convert it to a format, Wireshark understands and open it with display filter set to btatt
```sh
SUFFIX=$(date -Is)
adb shell dumpsys bluetooth_manager > "btsnoop_$SUFFIX.txt"
python3 btsnooz.py "btsnoop_$SUFFIX.txt" > "btsnoop_$SUFFIX.log"
wireshark -Y btatt "btsnoop_$SUFFIX.log"
```
Depeding on the commuincation content, wireshark will report [Packet size limited during capture: BT ATT truncated].
https://issuetracker.google.com/issues/226155463?pli=1

### Using Logcat from Android Studio for Live View
[Android Studio](https://developer.android.com/studio)
[Logcat](https://developer.android.com/studio/debug/logcat)
And set
 Log Tag (regex): BT|luetooth|bt|Bt
 Log Level: Debug

```sh
adb logcat | grep -i -e att -e bt_ -e bluetooth > logcat/logcat_bluetooth_gatt.txt
```

### Wireshark HCI snoop
Start wireshark while mobile is connected in debug mode and select 
Android Bluteooth Btsnoop as caputer adapter

### bluetoothctl
```sh
sudo bluetoothctl -m
```
