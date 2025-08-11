# Temple Office Digital Signage - v2.1.2

A comprehensive digital signage system with **bulletproof browser crash prevention**, 4K display optimization, weather integration, and Google Calendar sync.

## Features

- **🛡️ Bulletproof Crash Prevention**: Tested automatic monitoring and restart of browser processes
- **🖥️ 4K Display Optimization**: Enhanced layouts for high-resolution displays  
- **🌤️ Weather Integration**: Real-time weather with lightning detection and safety alerts
- **📅 Google Calendar Sync**: Displays upcoming events with proper formatting
- **📊 CFSS Dashboard**: Circuit monitoring with auto-scroll functionality
- **📰 News Ticker**: Local news content with smooth scrolling animation
- **📺 TV Control**: HDMI-CEC integration for automatic TV on/off
- **⏰ Business Hours**: Scheduled operation (7 AM - 5 PM weekdays)
- **🔧 SystemD Integration**: Reliable service management with proper environment

## System Requirements

- Raspberry Pi (tested on Pi 4)
- Python 3.9+
- Chromium browser
- HDMI-CEC capable TV
- systemd service management

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/rc91470/temple-office-signage.git
   cd temple-office-signage
   ```

2. Set up virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. Configure environment variables:
   ```bash
   export WEATHER_API_KEY="your_openweathermap_key"
   ```

4. Set up systemd service:
   ```bash
   sudo cp temple-signage.service /etc/systemd/system/
   sudo systemctl enable temple-signage
   sudo systemctl start temple-signage
   ```

## Architecture

- **signage_controller.py**: Main Flask application with digital signage logic
- **temple_weather.py**: Weather API integration and lightning detection
- **google_calendar.py**: Google Calendar API integration
- **Browser Monitoring**: Automatic process health checks and restart capability
- **Dashboard Rotation**: JavaScript-based switching between CFSS, Calendar, and Weather

## API Endpoints

- `/` - Main dashboard with automatic rotation
- `/weather` - Weather and news display
- `/calendar3` - 3-month calendar view  
- `/cfss` - CFSS circuit monitoring dashboard
- `/api/debug/start-business-day` - Manual business day trigger
- `/api/debug/schedule` - View scheduled jobs

## Crash Prevention

The system includes comprehensive **bulletproof** browser crash prevention:
- ✅ **TESTED & VERIFIED**: Process monitoring every 5 minutes during business hours
- ✅ **PROVEN RELIABLE**: Automatic restart on browser death (tested with manual kill)
- 🛡️ **BULLETPROOF**: SystemD service with proper PATH environment for chromium access
- 🔍 **COMPREHENSIVE**: Multiple process management fallback methods
- 📋 **DETAILED LOGGING**: Activity logged to `/tmp/browser-control.log`
- ⚡ **GRACEFUL**: Clean shutdown and restart procedures

## Version History

- **v2.1.2** - SystemD Service PATH Fix (Current) - CRITICAL FIX: Updated systemd service PATH to include `/usr/bin` for chromium executable. TESTED crash prevention - manual process kill results in automatic restart within 5 minutes. System now truly bulletproof.
- **v2.1.1** - Browser Executable Path Fix - Fixed browser executable name from `chromium-browser` to `chromium`, improved monitoring reliability
- **v2.1.0** - Browser crash prevention, 4K layout fixes, enhanced news system
- **v2.0.0** - Major rewrite with weather integration and Google Calendar
- **v1.0.0** - Basic digital signage functionality

## Contributing

This is a custom system for Temple Office. Contact richard.coleman@iescomm.com for questions.
