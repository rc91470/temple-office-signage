# Temple Office Digital Signage - v2.1.0

A comprehensive digital signage system with 4K display optimization, browser crash prevention, weather integration, and Google Calendar sync.

## Features

- **Browser Crash Prevention**: Automatic monitoring and restart of browser processes
- **4K Display Optimization**: Enhanced layouts for high-resolution displays
- **Weather Integration**: Real-time weather with lightning detection and safety alerts
- **Google Calendar Sync**: Displays upcoming events with proper formatting
- **CFSS Dashboard**: Circuit monitoring with auto-scroll functionality
- **News Ticker**: Local news content with smooth scrolling animation
- **TV Control**: HDMI-CEC integration for automatic TV on/off
- **Business Hours**: Scheduled operation (7 AM - 5 PM weekdays)

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

The system includes comprehensive browser crash prevention:
- Process monitoring every 5 minutes during business hours
- Automatic restart on browser death
- Multiple process management fallback methods
- Logging to `/tmp/browser-control.log`
- Graceful cleanup on service shutdown

## Version History

- **v2.1.0** - Browser crash prevention, 4K layout fixes, enhanced news system
- **v2.0.0** - Major rewrite with weather integration and Google Calendar
- **v1.0.0** - Basic digital signage functionality

## Contributing

This is a custom system for Temple Office. Contact richard.coleman@iescomm.com for questions.
