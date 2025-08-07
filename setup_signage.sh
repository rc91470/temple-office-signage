#!/bin/bash

echo "🚀 Setting up Temple Office Digital Signage..."

# Update system
echo "📦 Updating system packages..."
sudo apt update

# Install Python dependencies
echo "🐍 Installing Python dependencies..."
sudo apt install -y python3-pip python3-venv

# Install system dependencies for the signage system
echo "🔧 Installing system dependencies..."
sudo apt install -y \
    cec-utils \
    xdotool \
    chromium-browser \
    x11-xserver-utils \
    unclutter

# Create virtual environment
echo "🌟 Creating Python virtual environment..."
cd /home/pi/RCcode/temple-office-signage
python3 -m venv venv
source venv/bin/activate

# Install Python packages
echo "📚 Installing Python packages..."
pip install --upgrade pip
pip install flask requests schedule pytz

# Create SharePoint sync directory
echo "📁 Creating SharePoint sync directory..."
mkdir -p /home/pi/sharepoint-sync

# Create systemd service file
echo "⚙️ Creating systemd service..."
sudo tee /etc/systemd/system/temple-signage.service > /dev/null <<EOF
[Unit]
Description=Temple Office Digital Signage
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/RCcode/temple-office-signage
Environment=PATH=/home/pi/RCcode/temple-office-signage/venv/bin
ExecStart=/home/pi/RCcode/temple-office-signage/venv/bin/python src/signage_controller.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable the service
echo "🔄 Enabling systemd service..."
sudo systemctl daemon-reload
sudo systemctl enable temple-signage.service

# Create kiosk mode script
echo "🖥️ Creating kiosk mode script..."
mkdir -p /home/pi/scripts
tee /home/pi/scripts/start-kiosk.sh > /dev/null <<EOF
#!/bin/bash

# Disable screen blanking
xset s noblank
xset s off
xset -dpms

# Remove cursor
unclutter -idle 0.5 -root &

# Start Chromium in kiosk mode
chromium-browser --noerrdialogs --disable-infobars --kiosk http://localhost:8080/cfss
EOF

chmod +x /home/pi/scripts/start-kiosk.sh

# Set up autostart for X session
echo "🎯 Setting up autostart..."
mkdir -p /home/pi/.config/autostart
tee /home/pi/.config/autostart/signage-kiosk.desktop > /dev/null <<EOF
[Desktop Entry]
Type=Application
Name=Temple Signage Kiosk
Exec=/home/pi/scripts/start-kiosk.sh
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF

echo "✅ Setup complete!"
echo ""
echo "📋 Next steps:"
echo "1. Get a free weather API key from: https://openweathermap.org/api"
echo "2. Set your weather API key: export WEATHER_API_KEY='your_key_here'"
echo "3. Start the service: sudo systemctl start temple-signage.service"
echo "4. Check status: sudo systemctl status temple-signage.service"
echo "5. View control panel: http://localhost:8080/control"
echo ""
echo "🔧 Optional configuration:"
echo "- Set up SharePoint sync in /home/pi/sharepoint-sync/"
echo "- Configure HDMI-CEC for TV control"
echo "- Set up remote access (Tailscale/SSH)"
echo ""
echo "🌐 Access URLs:"
echo "- Main dashboard: http://localhost:8080"
echo "- Control panel: http://localhost:8080/control"
echo "- Individual dashboards: /cfss, /weather, /sharepoint, /calendar"
