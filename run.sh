#!/bin/bash

# FlexROV control server + video stream.
#
# You do NOT need to set a static IP on the control PC any more. The Pi runs a
# WiFi hotspot called "hotspot"; join it, then open http://192.168.4.1
#
# One-time on the Pi:  sudo ./setup_hotspot.sh
# Every time:          ./run.sh
#
# Note: the server needs root - port 80 needs it, and so does /dev/ttyUSB0.
# Run it with sudo even though the dependency install below already does.

sudo apt update
sudo apt install -y ustreamer python3-flask python3-serial

sudo python3 Control_Server.py &
ustreamer --device=/dev/video1 --host=0.0.0.0 --port=8080 --desired-fps=30
