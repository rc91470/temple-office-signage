#!/bin/bash

# Launch Temple Office Signage Dashboard in fullscreen
export DISPLAY=:0

# Wait for X to be ready
sleep 5

# Launch Chromium in kiosk mode with 4K optimizations
chromium-browser \
    --start-fullscreen \
    --kiosk \
    --incognito \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-restore-session-state \
    --noerrdialogs \
    --no-first-run \
    --fast \
    --fast-start \
    --disable-default-apps \
    --disable-popup-blocking \
    --disable-translate \
    --force-device-scale-factor=1 \
    --high-dpi-support=1 \
    --disable-features=TranslateUI \
    --disable-background-timer-throttling \
    http://localhost:8080

# If that fails, try with different approach
if [ $? -ne 0 ]; then
    sleep 2
    DISPLAY=:0 chromium-browser --kiosk http://localhost:8080
fi
