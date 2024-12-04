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

## Logging Blutooth Commads from LumixSync
Enable Developer settings on your phone, enable USB Debugging
```sh
adb shell settings put secure bluetooth_hci_log 1
adb shell cmd bluetooth_manager disable
adb shell cmd bluetooth_manager enable
```

```sh
adb bugreport zipFilename
```

```sh
unzip zipFileName "FS/data/misc/bluetooth/*"
```
Open `*.cfa` file with Wireshark and use `btatt` as display filter


### Bluetooth dump using adb dumpsys
https://source.android.com/docs/core/connect/bluetooth/verifying_debugging?hl=de

```sh
adb shell dumpsys bluetooth_manager > btsnoop.txt
```
Convert to a format, Wireshark understands
```sh
./btsnooz.py btsnoop.txt > btsnoop.log
```

Open `btsnoop.log` file with Wireshark and use `btatt` as display filter
`wireshark -Y btatt btsnoop.log `

### Using Logcat from Android Studio
[Android Studio](https://developer.android.com/studio)

### bluetoothctl
```sh
sudo bluetoothctl -m
```
