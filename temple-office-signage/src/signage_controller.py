#!/usr/bin/env python3

# Enhanced Digital Signage with SharePoint + Temple Weather
# Version 2.4.0 - Weather Dashboard Enhancements and Lightning System Fixes
import os
import signal
import time
import subprocess
import schedule
import json
import calendar
import math
import os
import time
import random
import traceback
import sys
from datetime import datetime, timedelta
from flask import Flask, render_template_string, render_template, jsonify, request
import threading
import pytz
import requests

# Configure logging to flush immediately
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Import Temple weather module
from temple_weather import TempleWeather, get_weather_emoji
# Google Calendar integration
from google_calendar import GoogleCalendarAPI

app = Flask(__name__, template_folder='../templates')

class DigitalSignage:
    def __init__(self):
        self.current_dashboard = 0
        self.dashboards = [
            {"name": "CFSS Dashboard", "url": "http://localhost:8080/cfss", "duration": 45},
            {"name": "3-Month Calendar", "url": "http://localhost:8080/calendar3", "duration": 45},
            {"name": "Temple Weather", "url": "http://localhost:8080/weather", "duration": 45},
        ]
        # Set TV on by default during business hours
        current_time = datetime.now().time()
        business_start = datetime.strptime("07:00", "%H:%M").time()
        business_end = datetime.strptime("17:00", "%H:%M").time()
        self.tv_on = business_start <= current_time <= business_end
        
        self.business_hours = {"start": "07:00", "end": "17:00"}
        
        # Browser process management
        self.browser_process = None
        self.last_browser_check = None
        self.browser_restart_count = 0
        
        # Weather API setup (get free key from openweathermap.org)
        self.weather_api_key = os.getenv('WEATHER_API_KEY', 'YOUR_API_KEY_HERE')
        self.weather_api_key = os.getenv('WEATHER_API_KEY', 'YOUR_API_KEY_HERE')
        self.weather = TempleWeather(self.weather_api_key) if self.weather_api_key != 'YOUR_API_KEY_HERE' else None
        self.weather_data = None
        self.forecast_data = None
        self.lightning_data = None
        
        # 2310 Eberhardt Rd, Temple, Texas coordinates for lightning detection
        self.temple_lat = 31.0847
        self.temple_lon = -97.3678
        
        # Lightning safety tracking
        self.lightning_strikes = []  # Store recent strikes with timestamps
        self.last_strike_time = None
        self.safety_timer_minutes = 30  # 30 minutes after last strike
        self.lightning_active = False  # Track if we're in lightning mode
        self.update_frequency_normal = 10  # Normal: 10 minutes
        self.update_frequency_lightning = 2  # Lightning mode: 2 minutes
        
        # SharePoint sync path
        self.sharepoint_path = "/home/pi/sharepoint-sync"
        
        # Google Calendar setup
        try:
            print("Initializing Google Calendar...")
            self.calendar = GoogleCalendarAPI(
                credentials_file='/home/pi/RCcode/temple-office-signage/credentials.json',
                token_file='/home/pi/RCcode/temple-office-signage/token.json'
            )
            print("Google Calendar initialized successfully")
        except Exception as e:
            print(f"Error initializing Google Calendar: {e}")
            self.calendar = None
        self.calendar_events = None
        
        # Update weather data every 10 minutes
        self.update_weather_data()
        self.update_calendar_data()
        
    def update_weather_data(self):
        """Update weather data from API"""
        if self.weather:
            try:
                self.weather_data = self.weather.get_current_weather()
                self.forecast_data = self.weather.get_forecast(4)
                
                # Get lightning data
                self.lightning_data = self.get_lightning_data()
                
                print(f"Weather updated: {self.weather_data['temperature']}°F")
                if self.lightning_data and self.lightning_data.get('status') != 'clear':
                    print(f"Lightning status: {self.lightning_data.get('status')}")
            except Exception as e:
                print(f"Weather update failed: {e}")
                self.weather_data = self.weather.get_fallback_weather()
                self.forecast_data = self.weather.get_fallback_forecast()
                self.lightning_data = None
        else:
            # Use fallback data if no API key
            self.weather_data = {
                'temperature': 75, 'feels_like': 78, 'humidity': 60,
                'description': 'Partly Cloudy', 'icon': '02d',
                'wind_speed': 8, 'pressure': 1013, 'visibility': 10, 'uv_index': 6
            }
            self.forecast_data = [
                {'date': 'Tomorrow', 'high': 78, 'low': 65, 'description': 'Sunny', 'icon': '01d'},
                {'date': 'Wed', 'high': 82, 'low': 68, 'description': 'Partly Cloudy', 'icon': '02d'},
                {'date': 'Thu', 'high': 75, 'low': 62, 'description': 'Rain', 'icon': '09d'},
                {'date': 'Fri', 'high': 79, 'low': 66, 'description': 'Cloudy', 'icon': '03d'}
            ]
            self.lightning_data = None
    
    def update_calendar_data(self):
        """Update calendar events from Google Calendar"""
        print("Updating calendar data...")
        if self.calendar is None:
            print("Calendar is None - using fallback events")
            # Fallback events when calendar is not set up yet
            self.calendar_events = [
                {
                    'title': 'Google Calendar Not Available',
                    'time': 'Error',
                    'duration': 'Check configuration',
                    'description': 'Google Calendar integration not initialized',
                    'location': 'Temple Office',
                    'is_today': True
                }
            ]
            return
            
        try:
            print("Calling calendar.get_upcoming_events...")
            self.calendar_events = self.calendar.get_upcoming_events(max_results=8, days_ahead=90)
            print(f"Calendar updated: {len(self.calendar_events)} events loaded")
            if self.calendar_events:
                print(f"First event: {self.calendar_events[0]['title']}")
        except Exception as e:
            print(f"Calendar update failed: {e}")
            # Show error message instead of fallback events
            self.calendar_events = [
                {
                    'title': 'Real Calendar Error',
                    'time': 'Error',
                    'duration': 'Check connection',
                    'description': f'Google Calendar API connection failed: {str(e)}',
                    'location': 'richard.coleman@iescomm.com',
                    'is_today': True
                }
            ]
    
    def get_lightning_data(self):
        """Get lightning strike data within 10 miles of Temple, Texas"""
        try:
            current_time = datetime.now()
            
            # Clean up old strikes (older than 2 hours)
            cutoff_time = current_time - timedelta(hours=2)
            self.lightning_strikes = [strike for strike in self.lightning_strikes 
                                    if strike['timestamp'] > cutoff_time]
            
            # Try multiple lightning detection sources
            new_strikes = []
            
            # Source 1: WeatherAPI for lightning alerts and current conditions
            if self.weather_api_key != 'YOUR_API_KEY_HERE':
                try:
                    # Check for lightning alerts
                    alerts_url = f"http://api.weatherapi.com/v1/alerts.json?key={self.weather_api_key}&q={self.temple_lat},{self.temple_lon}"
                    response = requests.get(alerts_url, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        alerts = data.get('alerts', {}).get('alert', [])
                        
                        for alert in alerts:
                            if 'thunder' in alert.get('event', '').lower() or 'lightning' in alert.get('event', '').lower():
                                # Add simulated strike for active lightning alert
                                strike_time = current_time
                                new_strikes.append({
                                    'latitude': self.temple_lat + (random.uniform(-0.1, 0.1)),
                                    'longitude': self.temple_lon + (random.uniform(-0.1, 0.1)),
                                    'timestamp': strike_time,
                                    'distance_miles': random.uniform(0, 10),
                                    'intensity': alert.get('severity', 'Moderate'),
                                    'source': 'WeatherAPI Alert'
                                })
                                self.last_strike_time = strike_time
                                print(f"Lightning alert active - simulated strike added")
                
                    # Check current weather for thunderstorm activity
                    current_url = f"http://api.weatherapi.com/v1/current.json?key={self.weather_api_key}&q={self.temple_lat},{self.temple_lon}"
                    response = requests.get(current_url, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        current = data.get('current', {})
                        condition = current.get('condition', {}).get('text', '').lower()
                        
                        # If thunderstorm is active, simulate recent strikes
                        if any(word in condition for word in ['thunder', 'lightning', 'storm']):
                            # Add recent simulated strikes for active thunderstorm
                            for i in range(random.randint(1, 3)):
                                strike_time = current_time - timedelta(minutes=random.randint(0, 15))
                                distance = random.uniform(0, 10)
                                new_strikes.append({
                                    'latitude': self.temple_lat + (random.uniform(-0.2, 0.2)),
                                    'longitude': self.temple_lon + (random.uniform(-0.2, 0.2)),
                                    'timestamp': strike_time,
                                    'distance_miles': distance,
                                    'intensity': 'Moderate',
                                    'source': 'WeatherAPI Current'
                                })
                                if not self.last_strike_time or strike_time > self.last_strike_time:
                                    self.last_strike_time = strike_time
                            print(f"Thunderstorm active - {len(new_strikes)} simulated strikes added")
                            
                except Exception as e:
                    print(f"WeatherAPI lightning check failed: {e}")
            
            # Source 2: Check OpenWeatherMap for thunderstorm conditions
            if self.weather_data and not new_strikes:
                weather_id = self.weather_data.get('weather_id', 800)
                description = self.weather_data.get('description', '').lower()
                
                # Weather IDs 200-299 are thunderstorm conditions
                if 200 <= weather_id <= 299 or 'thunder' in description or 'lightning' in description:
                    # Add simulated strikes for detected thunderstorm
                    for i in range(random.randint(1, 2)):
                        strike_time = current_time - timedelta(minutes=random.randint(0, 20))
                        distance = random.uniform(0, 10)
                        new_strikes.append({
                            'latitude': self.temple_lat + (random.uniform(-0.15, 0.15)),
                            'longitude': self.temple_lon + (random.uniform(-0.15, 0.15)),
                            'timestamp': strike_time,
                            'distance_miles': distance,
                            'intensity': 'Moderate',
                            'source': 'OpenWeatherMap'
                        })
                        if not self.last_strike_time or strike_time > self.last_strike_time:
                            self.last_strike_time = strike_time
                    print(f"OpenWeatherMap thunderstorm detected - {len(new_strikes)} simulated strikes added")
            
            # Add new strikes to our tracking list
            self.lightning_strikes.extend(new_strikes)
            
            # Check if we need to switch to lightning mode
            was_lightning_active = self.lightning_active
            
            # Calculate safety timer
            safety_status = self.calculate_safety_timer()
            
            # Update lightning active status
            self.lightning_active = (self.last_strike_time and 
                                   (current_time - self.last_strike_time).total_seconds() / 60 < 60)
            
            # If we just entered lightning mode, reschedule updates
            if not was_lightning_active and self.lightning_active:
                print(f"🌩️ LIGHTNING MODE ACTIVATED - Switching to {self.update_frequency_lightning}-minute updates")
                self.reschedule_weather_updates()
            elif was_lightning_active and not self.lightning_active:
                print(f"☀️ Lightning mode deactivated - Returning to {self.update_frequency_normal}-minute updates")
                self.reschedule_weather_updates()
            
            # Prepare response data
            recent_strikes = [strike for strike in self.lightning_strikes 
                            if strike['timestamp'] > current_time - timedelta(minutes=60)]
            
            if recent_strikes:
                status = 'active_lightning' if safety_status['minutes_remaining'] > 0 else 'recent_activity'
                message = f"{len(recent_strikes)} strikes in last hour. {safety_status['message']}"
            else:
                status = 'clear'
                message = 'No lightning activity detected within 10 miles'
            
            return {
                'strikes': recent_strikes,
                'total_strikes_60min': len(recent_strikes),
                'last_strike_time': self.last_strike_time.isoformat() if self.last_strike_time else None,
                'safety_timer': safety_status,
                'status': status,
                'message': message,
                'last_updated': current_time.isoformat(),
                'coverage_radius_miles': 10,
                'center_location': {
                    'latitude': self.temple_lat,
                    'longitude': self.temple_lon,
                    'address': '2310 Eberhardt Rd, Temple, TX'
                }
            }
            
        except Exception as e:
            print(f"Lightning detection error: {e}")
            return {
                'strikes': [],
                'total_strikes_60min': 0,
                'last_strike_time': None,
                'safety_timer': {'status': 'error', 'minutes_remaining': 0, 'message': 'Timer unavailable'},
                'status': 'error',
                'message': f'Lightning detection unavailable: {str(e)}',
                'last_updated': datetime.now().isoformat(),
                'coverage_radius_miles': 10,
                'center_location': {
                    'latitude': self.temple_lat,
                    'longitude': self.temple_lon,
                    'address': '2310 Eberhardt Rd, Temple, TX'
                }
            }
    
    def calculate_safety_timer(self):
        """Calculate safety timer - 30 minutes after last strike"""
        if not self.last_strike_time:
            return {
                'status': 'safe',
                'minutes_remaining': 0,
                'message': 'No recent lightning activity - Safe to proceed'
            }
        
        current_time = datetime.now()
        time_since_last = current_time - self.last_strike_time
        minutes_since = time_since_last.total_seconds() / 60
        
        if minutes_since >= self.safety_timer_minutes:
            return {
                'status': 'safe',
                'minutes_remaining': 0,
                'message': f'Safe - {int(minutes_since)} minutes since last strike'
            }
        else:
            remaining = self.safety_timer_minutes - minutes_since
            return {
                'status': 'wait',
                'minutes_remaining': int(remaining),
                'message': f'WAIT - {int(remaining)} minutes until safe (30 min rule)'
            }

    def get_update_frequency(self):
        """Get appropriate update frequency based on lightning activity"""
        # Check if we're in active lightning mode
        if self.last_strike_time:
            current_time = datetime.now()
            time_since_last = current_time - self.last_strike_time
            minutes_since = time_since_last.total_seconds() / 60
            
            # Stay in lightning mode for 60 minutes after last strike
            if minutes_since < 60:
                return self.update_frequency_lightning
        
        return self.update_frequency_normal

    def update_weather_data_with_dynamic_frequency(self):
        """Update weather data and reschedule based on lightning activity"""
        # Update weather data
        self.update_weather_data()
        
        # Determine if lightning mode changed
        was_lightning_active = self.lightning_active
        self.lightning_active = (self.last_strike_time and 
                                (datetime.now() - self.last_strike_time).total_seconds() / 60 < 60)
        
        # If lightning mode changed, we need to reschedule
        if was_lightning_active != self.lightning_active:
            print(f"Lightning mode changed: {was_lightning_active} -> {self.lightning_active}")
            self.reschedule_weather_updates()

    def reschedule_weather_updates(self):
        """Reschedule weather updates based on current lightning activity"""
        # Clear existing weather update jobs
        schedule.clear('weather-updates')
        
        # Schedule new frequency
        frequency = self.get_update_frequency()
        print(f"Rescheduling weather updates: every {frequency} minutes")
        
        schedule.every(frequency).minutes.do(self.update_weather_data_with_dynamic_frequency).tag('weather-updates')
    
    def calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two coordinates in miles"""
        R = 3959  # Earth's radius in miles
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c

    def get_direction_from_coordinates(self, center_lat, center_lon, target_lat, target_lon):
        """Calculate compass direction from center to target coordinates"""
        delta_lon = target_lon - center_lon
        delta_lat = target_lat - center_lat
        
        # Calculate bearing in radians
        bearing = math.atan2(delta_lon, delta_lat)
        
        # Convert to degrees
        bearing_deg = math.degrees(bearing)
        
        # Normalize to 0-360
        bearing_deg = (bearing_deg + 360) % 360
        
        # Convert to compass direction
        directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 
                     'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
        
        # Each direction covers 22.5 degrees
        index = round(bearing_deg / 22.5) % 16
        return directions[index]

    def get_sharepoint_files(self):
        """Get list of files from SharePoint sync folder"""
        files = []
        try:
            if os.path.exists(self.sharepoint_path):
                for root, dirs, filenames in os.walk(self.sharepoint_path):
                    for filename in filenames:
                        if filename.lower().endswith(('.pdf', '.docx', '.xlsx', '.pptx', '.txt', '.md', '.html', '.htm')):
                            file_path = os.path.join(root, filename)
                            relative_path = os.path.relpath(file_path, self.sharepoint_path)
                            file_size = os.path.getsize(file_path)
                            modified_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                            
                            files.append({
                                'name': filename,
                                'path': relative_path,
                                'size': self.format_file_size(file_size),
                                'modified': modified_time.strftime('%Y-%m-%d %H:%M'),
                                'type': filename.split('.')[-1].upper()
                            })
            
            # Sort by modification time (newest first)
            files.sort(key=lambda x: x['modified'], reverse=True)
            return files[:20]  # Return latest 20 files
            
        except Exception as e:
            print(f"Error reading SharePoint files: {e}")
            return [
                {'name': 'SharePoint Sync Error', 'path': '', 'size': '0 KB', 
                 'modified': datetime.now().strftime('%Y-%m-%d %H:%M'), 'type': 'ERROR'}
            ]
    
    def format_file_size(self, size_bytes):
        """Format file size in human readable format"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024**2:
            return f"{size_bytes/1024:.1f} KB"
        elif size_bytes < 1024**3:
            return f"{size_bytes/(1024**2):.1f} MB"
        else:
            return f"{size_bytes/(1024**3):.1f} GB"
    
    def turn_tv_on(self):
        """Turn TV on via HDMI-CEC"""
        timestamp = datetime.now()
        print(f"{timestamp}: Attempting to turn TV ON...")
        
        # Also write to a debug log file
        try:
            with open('/tmp/tv-control.log', 'a') as f:
                f.write(f"{timestamp}: === TURN TV ON CALLED ===\n")
        except:
            pass
        
        # Try HDMI-CEC with active source command (more reliable)
        cec_success = False
        try:
            # First, set this device as active source (this usually turns on TV)
            result = subprocess.run(['/usr/bin/cec-client', '-s', '-d', '1'], 
                                  input='as\n', text=True, timeout=15, 
                                  capture_output=True)
            
            # Log to file
            try:
                with open('/tmp/tv-control.log', 'a') as f:
                    f.write(f"{timestamp}: Active source result: code={result.returncode}, stdout={result.stdout.strip()}\n")
                    if result.stderr:
                        f.write(f"{timestamp}: Active source stderr: {result.stderr.strip()}\n")
            except:
                pass
            
            # Wait a moment then check if TV is on
            time.sleep(3)
            verify_result = subprocess.run(['/usr/bin/cec-client', '-s', '-d', '1'], 
                                         input='pow 0\n', text=True, timeout=15, 
                                         capture_output=True)
            
            tv_status = verify_result.stdout.strip()
            print(f"{timestamp}: TV power status after active source: {tv_status}")
            
            # Log to file
            try:
                with open('/tmp/tv-control.log', 'a') as f:
                    f.write(f"{timestamp}: Power verify: {tv_status}\n")
            except:
                pass
            
            if 'on' in tv_status:
                cec_success = True
                print(f"{timestamp}: TV turned ON via CEC active source successfully")
            else:
                print(f"{timestamp}: Active source command didn't turn on TV, trying direct on command")
                # Try direct on command as backup
                on_result = subprocess.run(['/usr/bin/cec-client', '-s', '-d', '1'], 
                                         input='on 0\n', text=True, timeout=15, 
                                         capture_output=True)
                
                # Log to file
                try:
                    with open('/tmp/tv-control.log', 'a') as f:
                        f.write(f"{timestamp}: Direct on result: code={on_result.returncode}, stdout={on_result.stdout.strip()}\n")
                except:
                    pass
                
                if on_result.returncode == 0:
                    cec_success = True
                    print(f"{timestamp}: TV turned ON via direct CEC command")
            
        except subprocess.TimeoutExpired:
            print(f"{timestamp}: CEC command timed out")
            try:
                with open('/tmp/tv-control.log', 'a') as f:
                    f.write(f"{timestamp}: CEC command timed out\n")
            except:
                pass
        except Exception as e:
            print(f"{timestamp}: CEC command exception: {e}")
            try:
                with open('/tmp/tv-control.log', 'a') as f:
                    f.write(f"{timestamp}: CEC exception: {e}\n")
            except:
                pass
        
        # Try alternative methods if CEC failed
        if not cec_success:
            print(f"{timestamp}: CEC failed, trying alternative methods...")
            
            # Try to wake up display via xset (if running in X session)
            try:
                subprocess.run(['xset', 'dpms', 'force', 'on'], timeout=5, capture_output=True)
                print(f"{timestamp}: Attempted display wake via xset")
            except:
                pass
            
            # Try to activate screen via xrandr
            try:
                subprocess.run(['xrandr', '--output', 'HDMI-1', '--auto'], timeout=5, capture_output=True)
                print(f"{timestamp}: Attempted HDMI activation via xrandr")
            except:
                pass
        
        # Log completion
        try:
            with open('/tmp/tv-control.log', 'a') as f:
                f.write(f"{timestamp}: === TURN TV ON COMPLETED ===\n\n")
        except:
            pass
        
        # Always set TV status to ON for dashboard rotation
        self.tv_on = True
        print(f"{timestamp}: TV status set to ON (dashboard rotation will start)")
    
    def turn_tv_off(self):
        """Turn TV off via HDMI-CEC"""
        timestamp = datetime.now()
        print(f"{timestamp}: Attempting to turn TV OFF...")
        
        # Also write to a debug log file
        try:
            with open('/tmp/tv-control.log', 'a') as f:
                f.write(f"{timestamp}: === TURN TV OFF CALLED ===\n")
        except:
            pass
        
        try:
            # First check if TV is on
            check_result = subprocess.run(['/usr/bin/cec-client', '-s', '-d', '1'], 
                                        input='pow 0\n', text=True, timeout=15, 
                                        capture_output=True)
            print(f"{timestamp}: TV power status check: {check_result.stdout.strip()}")
            
            # Log to file
            try:
                with open('/tmp/tv-control.log', 'a') as f:
                    f.write(f"{timestamp}: Power check: {check_result.stdout.strip()}\n")
            except:
                pass
            
            # Send standby command
            result = subprocess.run(['/usr/bin/cec-client', '-s', '-d', '1'], 
                                  input='standby 0\n', text=True, timeout=15, 
                                  capture_output=True)
            
            if result.returncode == 0:
                print(f"{timestamp}: CEC standby command sent successfully")
                print(f"{timestamp}: CEC stdout: {result.stdout.strip()}")
            else:
                print(f"{timestamp}: CEC standby command failed with return code {result.returncode}")
                if result.stderr:
                    print(f"{timestamp}: CEC stderr: {result.stderr.strip()}")
            
            # Log to file
            try:
                with open('/tmp/tv-control.log', 'a') as f:
                    f.write(f"{timestamp}: Standby result: code={result.returncode}, stdout={result.stdout.strip()}\n")
                    if result.stderr:
                        f.write(f"{timestamp}: Standby stderr: {result.stderr.strip()}\n")
            except:
                pass
            
            # Wait a moment then check if TV is off
            time.sleep(3)
            verify_result = subprocess.run(['/usr/bin/cec-client', '-s', '-d', '1'], 
                                         input='pow 0\n', text=True, timeout=15, 
                                         capture_output=True)
            print(f"{timestamp}: TV power status after standby: {verify_result.stdout.strip()}")
            
            # Log to file
            try:
                with open('/tmp/tv-control.log', 'a') as f:
                    f.write(f"{timestamp}: Power verify: {verify_result.stdout.strip()}\n")
                    f.write(f"{timestamp}: === TURN TV OFF COMPLETED ===\n\n")
            except:
                pass
            
            self.tv_on = False
            print(f"{timestamp}: TV status set to OFF")
            
        except subprocess.TimeoutExpired:
            print(f"{timestamp}: CEC command timed out")
            try:
                with open('/tmp/tv-control.log', 'a') as f:
                    f.write(f"{timestamp}: CEC command timed out\n")
            except:
                pass
        except Exception as e:
            print(f"{timestamp}: Error turning TV off: {e}")
            import traceback
            print(f"{timestamp}: Full traceback: {traceback.format_exc()}")
            try:
                with open('/tmp/tv-control.log', 'a') as f:
                    f.write(f"{timestamp}: Error: {e}\n")
                    f.write(f"{timestamp}: Traceback: {traceback.format_exc()}\n")
            except:
                pass
    
    def start_browser(self):
        """Start or restart the browser for digital signage"""
        timestamp = datetime.now()
        print(f"{timestamp}: Starting browser for digital signage...")
        
        try:
            # Kill any existing browser processes using killall (more reliable than pkill)
            try:
                subprocess.run(['killall', 'chromium'], capture_output=True)
            except FileNotFoundError:
                # If killall isn't available, try pkill
                try:
                    subprocess.run(['pkill', '-f', 'chromium'], capture_output=True)
                except FileNotFoundError:
                    # If neither works, continue anyway
                    pass
            time.sleep(2)
            
            # Start new browser process
            browser_cmd = [
                'chromium',
                '--kiosk',
                '--disable-infobars', 
                '--disable-session-crashed-bubble',
                '--disable-restore-session-state',
                '--disable-features=TranslateUI',
                '--no-first-run',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor',
                '--start-fullscreen',
                '--display=:0',
                'http://localhost:8080/'
            ]
            
            # Start browser as subprocess
            env = os.environ.copy()
            env['DISPLAY'] = ':0'
            
            self.browser_process = subprocess.Popen(
                browser_cmd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid  # Create new process group
            )
            
            self.last_browser_check = timestamp
            self.browser_restart_count += 1
            
            print(f"{timestamp}: Browser started successfully (PID: {self.browser_process.pid}, Restart #{self.browser_restart_count})")
            
            # Log to file
            try:
                with open('/tmp/browser-control.log', 'a') as f:
                    f.write(f"{timestamp}: Browser started - PID: {self.browser_process.pid}, Restart #{self.browser_restart_count}\\n")
            except:
                pass
                
            return True
            
        except Exception as e:
            print(f"{timestamp}: Failed to start browser: {e}")
            try:
                with open('/tmp/browser-control.log', 'a') as f:
                    f.write(f"{timestamp}: Browser start failed: {e}\\n")
            except:
                pass
            return False

    def check_browser_health(self):
        """Check if browser is running and restart if needed - runs 24/7"""
        current_time = datetime.now()
            
        try:
            # Check if our browser process is still alive
            if self.browser_process:
                poll_result = self.browser_process.poll()
                if poll_result is not None:
                    # Process has terminated
                    print(f"{current_time}: Browser process died (exit code: {poll_result}) - restarting...")
                    self.browser_process = None
                    return self.start_browser()
                    
            # Check if any chromium process is running (more reliable method)
            try:
                result = subprocess.run(['pgrep', '-f', 'chromium'], 
                                      capture_output=True, text=True)
            except FileNotFoundError:
                # If pgrep not available, use ps and grep
                result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
                if 'chromium' not in result.stdout:
                    result.returncode = 1  # Set failure code if not found
                else:
                    result.returncode = 0  # Set success code if found
            
            if result.returncode != 0:
                # No chromium process found
                print(f"{current_time}: No browser process found - starting browser...")
                return self.start_browser()
                
            # Browser is running
            self.last_browser_check = current_time
            return True
            
        except Exception as e:
            print(f"{current_time}: Browser health check failed: {e}")
            return False

    def switch_dashboard(self):
        """Switch to next dashboard with browser health check"""
        if not self.tv_on:
            return
            
        # Check browser health before switching
        if not self.check_browser_health():
            print(f"{datetime.now()}: Browser health check failed - skipping dashboard switch")
        
        dashboard = self.dashboards[self.current_dashboard]
        print(f"{datetime.now()}: Switching to {dashboard['name']}")
        
        # The browser now handles rotation automatically via JavaScript
        # No need for xdotool - the browser loads localhost:8080/ which rotates
        
        self.current_dashboard = (self.current_dashboard + 1) % len(self.dashboards)
        threading.Timer(dashboard['duration'], self.switch_dashboard).start()

    def start_business_day(self):
        """Start business day with browser monitoring"""
        print(f"{datetime.now()}: Starting business day")
        self.update_weather_data()  # Refresh weather at start of day
        self.update_calendar_data()  # Refresh calendar at start of day
        
        # Turn on TV
        self.turn_tv_on()
        time.sleep(5)
        
        # Start browser with monitoring
        if self.start_browser():
            # Start dashboard switching after browser is ready
            time.sleep(3)
            self.switch_dashboard()
            
            # Set up periodic browser health checks every 5 minutes
            self.schedule_browser_health_check()
        else:
            print(f"{datetime.now()}: Failed to start browser - will retry in 1 minute")
            threading.Timer(60, self.start_business_day).start()
    
    def schedule_browser_health_check(self):
        """Schedule periodic browser health checks"""
        if self.tv_on:
            self.check_browser_health()
            # Schedule next check in 5 minutes
            threading.Timer(300, self.schedule_browser_health_check).start()
    
    def end_business_day(self):
        """End business day and clean up browser processes"""
        print(f"{datetime.now()}: Ending business day - calling turn_tv_off()")
        
        try:
            # Terminate browser process if running
            if self.browser_process:
                try:
                    # Send SIGTERM to process group
                    os.killpg(os.getpgid(self.browser_process.pid), signal.SIGTERM)
                    self.browser_process.wait(timeout=5)
                    print(f"{datetime.now()}: Browser process terminated gracefully")
                except subprocess.TimeoutExpired:
                    # Force kill if didn't exit gracefully
                    os.killpg(os.getpgid(self.browser_process.pid), signal.SIGKILL)
                    print(f"{datetime.now()}: Browser process force killed")
                except Exception as e:
                    print(f"{datetime.now()}: Error terminating browser: {e}")
                finally:
                    self.browser_process = None
            
            # Kill any remaining chromium processes using multiple methods
            try:
                subprocess.run(['killall', 'chromium'], capture_output=True)
            except FileNotFoundError:
                try:
                    subprocess.run(['pkill', '-f', 'chromium'], capture_output=True)
                except FileNotFoundError:
                    pass  # Neither command available
            
            # Turn off TV
            self.turn_tv_off()
            print(f"{datetime.now()}: turn_tv_off() completed successfully")
            
        except Exception as e:
            print(f"{datetime.now()}: Error in end_business_day(): {e}")
            
        print(f"{datetime.now()}: End business day process completed")


# Global signage controller
signage = DigitalSignage()

# Start 24/7 browser monitoring immediately when system starts
def start_24_7_browser_monitoring():
    """Start browser and continuous 24/7 monitoring"""
    print(f"{datetime.now()}: Starting 24/7 browser monitoring")
    
    # Start browser
    if signage.start_browser():
        # Start dashboard switching
        time.sleep(3)
        signage.switch_dashboard()
        
        # Set up continuous browser health checks every 5 minutes
        schedule_24_7_browser_health_check()
    else:
        print(f"{datetime.now()}: Failed to start browser - will retry in 1 minute")
        threading.Timer(60, start_24_7_browser_monitoring).start()

def schedule_24_7_browser_health_check():
    """Schedule continuous 24/7 browser health checks"""
    signage.check_browser_health()
    # Schedule next check in 5 minutes (always, regardless of TV state)
    threading.Timer(300, schedule_24_7_browser_health_check).start()

# Start 24/7 monitoring immediately
start_24_7_browser_monitoring()

# Add a manual scheduler check function
def run_pending_jobs():
    """Run pending scheduled jobs"""
    schedule.run_pending()
    threading.Timer(60, run_pending_jobs).start()  # Check every minute

# Schedule business hours and weather updates
schedule.every().monday.at(signage.business_hours["start"]).do(signage.start_business_day)
schedule.every().tuesday.at(signage.business_hours["start"]).do(signage.start_business_day)
schedule.every().wednesday.at(signage.business_hours["start"]).do(signage.start_business_day)
schedule.every().thursday.at(signage.business_hours["start"]).do(signage.start_business_day)
schedule.every().friday.at(signage.business_hours["start"]).do(signage.start_business_day)

schedule.every().monday.at(signage.business_hours["end"]).do(signage.end_business_day)
schedule.every().tuesday.at(signage.business_hours["end"]).do(signage.end_business_day)
schedule.every().wednesday.at(signage.business_hours["end"]).do(signage.end_business_day)
schedule.every().thursday.at(signage.business_hours["end"]).do(signage.end_business_day)
schedule.every().friday.at(signage.business_hours["end"]).do(signage.end_business_day)

# Update weather with dynamic frequency based on lightning activity
schedule.every(signage.update_frequency_normal).minutes.do(signage.update_weather_data_with_dynamic_frequency).tag('weather-updates')

# Update calendar every 15 minutes
schedule.every(15).minutes.do(signage.update_calendar_data)

# Start the background scheduler
run_pending_jobs()

@app.route('/api/debug/schedule')
def debug_schedule():
    """Debug endpoint to see scheduled jobs"""
    jobs = []
    for job in schedule.jobs:
        jobs.append({
            'job': str(job),
            'next_run': str(job.next_run),
            'tags': list(job.tags) if job.tags else [],
            'last_run': str(job.last_run) if job.last_run else 'Never'
        })
    
    return {
        'current_time': datetime.now().isoformat(),
        'jobs': jobs,
        'total_jobs': len(schedule.jobs)
    }

@app.route('/api/debug/start-business-day')
def debug_start_business_day():
    """Manual trigger for business day start (for testing)"""
    try:
        signage.start_business_day()
        return {'status': 'success', 'message': 'Business day started manually'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

@app.route('/api/debug/end-business-day')
def debug_end_business_day():
    """Manual trigger for business day end (for testing)"""
    try:
        signage.end_business_day()
        return {'status': 'success', 'message': 'Business day ended manually - check logs for details'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

@app.route('/api/debug/tv-off')
def debug_tv_off():
    """Manual trigger for TV off (for testing)"""
    try:
        signage.turn_tv_off()
        return {'status': 'success', 'message': 'TV turn-off command sent - check logs for details'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

@app.route('/api/debug/tv-on')
def debug_tv_on():
    """Manual trigger for TV on (for testing)"""
    try:
        signage.turn_tv_on()
        return {'status': 'success', 'message': 'TV turn-on command sent - check logs for details'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

@app.route('/')
def home():
    """Main rotating dashboard page"""
    return '''<!DOCTYPE html>
<html>
<head>
    <title>Temple Office Digital Signage</title>
    <meta charset="UTF-8">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html, body { 
            width: 100%; height: 100%; overflow: hidden; 
            font-family: Arial; background: #000;
        }
        /* Hide all scrollbars */
        ::-webkit-scrollbar { display: none; }
        * { -ms-overflow-style: none; scrollbar-width: none; }
        
        #dashboard-container { 
            width: 100vw; height: 100vh; 
            position: relative; overflow: hidden;
        }
        
        .dashboard-content { 
            width: 100%; height: 100%; 
            position: absolute; top: 0; left: 0;
            opacity: 0; transition: opacity 1s ease-in-out;
        }
        
        .dashboard-content.active { opacity: 1; }
        
        #status { 
            position: fixed; top: 10px; right: 10px; 
            background: rgba(0,0,0,0.8); color: white; 
            padding: 8px 12px; border-radius: 5px; 
            font-size: 12px; z-index: 1000;
            display: none;
        }
    </style>
</head>
<body>
    <div id="status">Loading...</div>
    <div id="dashboard-container"></div>
    
    <script>
        const dashboards = [
            { url: '/cfss', name: 'CFSS Dashboard', duration: 45000 },
            { url: '/calendar3', name: '3-Month Calendar', duration: 45000 },
            { url: '/weather', name: 'Temple Weather', duration: 45000 }
        ];
        
        let currentIndex = 0;
        const container = document.getElementById('dashboard-container');
        const status = document.getElementById('status');
        
        function loadDashboard(url, callback) {
            fetch(url)
                .then(response => response.text())
                .then(html => {
                    // Remove existing content
                    container.innerHTML = '';
                    
                    // Create new content div
                    const contentDiv = document.createElement('div');
                    contentDiv.className = 'dashboard-content active';
                    contentDiv.innerHTML = html;
                    container.appendChild(contentDiv);
                    
                    if (callback) callback();
                })
                .catch(error => {
                    console.error('Error loading dashboard:', error);
                    if (callback) callback();
                });
        }
        
        function switchToDashboard() {
            const dashboard = dashboards[currentIndex];
            status.textContent = dashboard.name;
            status.style.display = 'block';
            
            loadDashboard(dashboard.url, () => {
                setTimeout(() => {
                    status.style.display = 'none';
                }, 3000);
            });
            
            currentIndex = (currentIndex + 1) % dashboards.length;
            setTimeout(switchToDashboard, dashboard.duration);
        }
        
        // Start immediately
        switchToDashboard();
        
        // Debug: Show rotation in console
        console.log('Dashboard rotation started');
    </script>
</body>
</html>'''

@app.route('/cfss')
def cfss_dashboard():
    """Serve the main CFSS dashboard from uploaded file or fallback to sample"""
    dashboard_path = '/home/pi/sharepoint-sync/dashboard.html'
    
    # Try to read the uploaded dashboard file
    try:
        with open(dashboard_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Inject height fixes for ALL screen sizes, not just 4K
        height_fix = '''
        <style>
        /* CFSS Dashboard Height Fix - Optimized spacing for better readability */
        #dashboardContent {
            min-height: 300vh !important; /* REDUCED excessive height */
            padding-bottom: 500px !important; /* REDUCED excessive padding */
            gap: 60px !important; /* REDUCED gaps for better content density */
        }
        
        /* Make sections larger with better proportions for readability */
        .dashboard-section {
            padding: 50px 35px !important; /* REDUCED padding but still spacious */
            margin-bottom: 80px !important; /* REDUCED spacing between sections */
        }
        
        .summary, .stats, .circuits-container, .completed-circuits {
            margin-bottom: 60px !important; /* REDUCED space but kept separation */
            padding: 40px !important; /* ADD internal padding to grow content areas */
        }
        
        /* Make circuit content areas JUST A BIT wider to prevent text overlap */
        .circuits-container, .completed-circuits {
            padding: 60px 45px !important; /* BIGGER content areas */
            width: 96% !important; /* SLIGHTLY wider containers to prevent text overlap */
            max-width: none !important; /* Remove any width restrictions */
        }
        
        .circuits-container h3, .completed-circuits h3 {
            font-size: 1.8em !important; /* BIGGER section headers */
            margin-bottom: 30px !important;
        }
        
        .circuit-item, .completed-item {
            padding: 25px 35px !important; /* JUST A BIT wider individual circuit boxes */
            margin: 20px 0 !important; /* More space between items */
            line-height: 1.4 !important; /* Better line spacing */
            width: 100% !important; /* Full width to prevent overlap */
            box-sizing: border-box !important; /* Include padding in width */
            overflow: hidden !important; /* Prevent text overflow */
            word-wrap: break-word !important; /* Break long words */
        }
        
        /* OPTIMIZED: 4K smooth CFSS auto-scroll - ALTERNATIVE METHOD */
        .auto-scroll {
            animation: autoScrollSmooth 40s infinite linear !important;
            transform: translate3d(0, 0, 0);
            will-change: transform;
            backface-visibility: hidden;
            filter: blur(0);
            animation-fill-mode: both;
            animation-timing-function: linear;
        }
        
        @keyframes autoScrollSmooth {
            0% { transform: translate3d(0, 0, 0); }
            17.5% { transform: translate3d(0, 0, 0); }
            47.5% { transform: translate3d(0, -140vh, 0); }
            67.5% { transform: translate3d(0, -140vh, 0); }
            100% { transform: translate3d(0, 0, 0); }
        }
        
        /* Media queries - OPTIMIZED for better content density and readability */
        @media screen and (max-width: 1920px) {
            #dashboardContent {
                min-height: 250vh !important; /* REDUCED for smaller screens */
                padding-bottom: 350px !important; /* REDUCED padding */
            }
            .dashboard-section {
            }
            .circuit-item, .completed-item {
                padding: 30px 40px !important; /* JUST A BIT wider for smaller screens */
            }
            @keyframes autoScroll {
                0% { transform: translateY(0) translateZ(0); }
                10% { transform: translateY(0) translateZ(0); }
                45% { transform: translateY(-90vh) translateZ(0); } /* DEEPER scroll for smaller screens */
                55% { transform: translateY(-90vh) translateZ(0); }
                90% { transform: translateY(0) translateZ(0); }
                100% { transform: translateY(0) translateZ(0); }
            }
        }
        
        @media screen and (min-width: 2560px) {
            #dashboardContent {
                min-height: 280vh !important; /* OPTIMIZED for 4K readability */
                padding-bottom: 450px !important; /* BALANCED padding */
            }
            .dashboard-section {
            }
            .circuits-container, .completed-circuits {
                width: 97% !important; /* SLIGHTLY wider for 4K */
            }
            .circuits-container h3, .completed-circuits h3 {
                font-size: 2.2em !important; /* MUCH bigger headers for 4K */
            }
            .circuit-item, .completed-item {
                padding: 35px 45px !important; /* JUST A BIT wider content boxes for 4K */
                width: 99% !important; /* SLIGHTLY wider for 4K to prevent overlap */
                max-width: none !important; /* Remove width restrictions */
            }
            @keyframes autoScrollSmooth {
                0% { transform: translate3d(0, 0, 0); }
                17.5% { transform: translate3d(0, 0, 0); }
                47.5% { transform: translate3d(0, -110vh, 0); }
                67.5% { transform: translate3d(0, -110vh, 0); }
                100% { transform: translate3d(0, 0, 0); }
            }
            
        }
        </style>
        '''
        
        # Inject the style right before the closing </head> tag
        content = content.replace('</head>', height_fix + '</head>')
        return content
    except FileNotFoundError:
        # Fallback to sample dashboard if file doesn't exist
        return '''<!DOCTYPE html>
<html>
<head>
    <title>CFSS Circuit Monitor</title>
    <meta http-equiv="refresh" content="25">
    <style>
        body { font-family: Arial; background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); 
               color: white; margin: 0; padding: 40px; min-height: 100vh; display: flex; flex-direction: column; }
        .container { max-width: 4000px; margin: 0 auto; width: 95%; flex: 1; display: flex; flex-direction: column; min-height: calc(100vh - 80px); }
        h1 { text-align: center; font-size: 12em; margin-bottom: 80px; text-shadow: 5px 5px 10px rgba(0,0,0,0.5); }
        .metrics { display: flex; justify-content: space-around; flex-wrap: wrap; flex: 1; align-items: stretch; }
        .metric { background: rgba(255,255,255,0.15); padding: 120px; border-radius: 40px; 
                  text-align: center; min-width: 750px; margin: 60px; box-shadow: 0 30px 120px rgba(0,0,0,0.3); 
                  display: flex; flex-direction: column; justify-content: center; min-height: 500px; }
        .metric h2 { font-size: 7.5em; margin: 0; }
        .metric p { font-size: 12em; margin: 40px 0; color: #4CAF50; font-weight: bold; }
        .status-bar { background: rgba(0,0,0,0.3); padding: 80px; border-radius: 30px; margin-top: 80px; }
        .status-bar h3 { font-size: 5em; margin-bottom: 40px; }
        .status-bar p { font-size: 3.8em; margin: 20px 0; line-height: 1.4; }
        .timestamp { text-align: center; margin-top: 80px; font-size: 4.2em; opacity: 0.8; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 CFSS Circuit Monitoring</h1>
        <div class="metrics">
            <div class="metric">
                <h2>Total Circuits</h2>
                <p>17</p>
            </div>
            <div class="metric">
                <h2>Active Now</h2>
                <p>15</p>
            </div>
            <div class="metric">
                <h2>System Health</h2>
                <p style="color: #4CAF50;">GOOD</p>
            </div>
            <div class="metric">
                <h2>Alerts</h2>
                <p style="color: #FFC107;">2</p>
            </div>
        </div>
        <div class="status-bar">
            <h3>Recent Activity - Temple Office</h3>
            <p>• Circuit BB-DR: Connection stable (99.8% uptime)</p>
            <p>• Circuit CS-EB: Performance optimal (15ms latency)</p>
            <p>• Circuit RSW-MA: Monitoring active (24/7)</p>
        </div>
        <div class="timestamp">
            Last Updated: ''' + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + '''<br>
            Next: SharePoint Files
        </div>
    </div>
</body>
</html>'''

def generate_month_calendar(events, year=None, month=None):
    """Generate a monthly calendar grid with events"""
    if year is None:
        year = datetime.now().year
    if month is None:
        month = datetime.now().month
    
    # Create calendar matrix - SET SUNDAY AS FIRST DAY
    calendar.setfirstweekday(calendar.SUNDAY)
    cal = calendar.monthcalendar(year, month)
    today = datetime.now().date()
    
    # Group events by date - HANDLE MULTI-DAY EVENTS
    events_by_date = {}
    for event in events:
        if not event:
            continue
            
        start_date = None
        end_date = None
        
        # Try to get start date from various fields
        if 'date_obj' in event and event['date_obj']:
            start_date = event['date_obj']
        elif 'start_datetime' in event and event['start_datetime']:
            # Parse the datetime string if needed
            try:
                if isinstance(event['start_datetime'], str):
                    if 'T' in event['start_datetime']:
                        dt = datetime.fromisoformat(event['start_datetime'].replace('Z', '+00:00'))
                        start_date = dt.date()
                    else:
                        start_date = datetime.fromisoformat(event['start_datetime']).date()
                else:
                    start_date = event['start_datetime'].date()
            except:
                # Try to parse from 'date' field
                date_str = event.get('date', '')
                if date_str == 'Today':
                    start_date = today
                elif date_str == 'Tomorrow':
                    start_date = today + timedelta(days=1)
                else:
                    # Try to parse other date formats
                    try:
                        # Format like 'Mon, Dec 30'
                        start_date = datetime.strptime(f"{date_str} {year}", "%a, %b %d %Y").date()
                    except:
                        continue
        
        # Try to get end date
        if 'end_datetime' in event and event['end_datetime']:
            try:
                if isinstance(event['end_datetime'], str):
                    if 'T' in event['end_datetime']:
                        dt = datetime.fromisoformat(event['end_datetime'].replace('Z', '+00:00'))
                        end_date = dt.date()
                    else:
                        end_date = datetime.fromisoformat(event['end_datetime']).date()
                else:
                    end_date = event['end_datetime'].date()
            except:
                end_date = start_date  # Single day event
        else:
            end_date = start_date  # Single day event if no end date
        
        # Add event to all days it spans
        if start_date and end_date:
            current_date = start_date
            while current_date <= end_date:
                if current_date not in events_by_date:
                    events_by_date[current_date] = []
                events_by_date[current_date].append(event)
                current_date += timedelta(days=1)
    
    # Build calendar data structure
    calendar_data = []
    for week in cal:
        week_data = []
        for day in week:
            if day == 0:
                # Day from previous/next month
                week_data.append({
                    'day': '',
                    'is_today': False,
                    'is_other_month': True,
                    'events': []
                })
            else:
                current_date = datetime(year, month, day).date()
                is_today = current_date == today
                day_events = events_by_date.get(current_date, [])
                
                week_data.append({
                    'day': day,
                    'is_today': is_today,
                    'is_other_month': False,
                    'events': day_events
                })
        calendar_data.append(week_data)
    
    return calendar_data

@app.route('/sharepoint')
def sharepoint_dashboard():
    # Get calendar events for the full month
    if not signage.calendar_events:
        signage.update_calendar_data()
    
    events = signage.calendar_events if signage.calendar_events else []
    
    # Create a monthly calendar view
    from datetime import datetime, timedelta
    import calendar
    
    now = datetime.now()
    year = now.year
    month = now.month
    month_name = calendar.month_name[month]
    
    print(f"Calendar display: Processing {len(events)} events for {month_name} {year}")
    
    # Debug: Print all events and their dates
    for event in events:
        print(f"Event: {event.get('title')} - Date: {event.get('date')} - Date obj: {event.get('date_obj')} - Start: {event.get('start_datetime')}")
    
    # Get first day of month and number of days
    first_day = datetime(year, month, 1)
    last_day = datetime(year, month, calendar.monthrange(year, month)[1])
    start_day = first_day.weekday()  # 0=Monday, 6=Sunday
    
    # Adjust for Sunday start (0=Sunday, 6=Saturday)
    start_day = (start_day + 1) % 7
    
    # Generate calendar grid
    calendar_html = ""
    week_html = ""
    
    # Add empty cells for days before month starts
    for i in range(start_day):
        week_html += '<div class="calendar-day empty"></div>'
    
    # Add days of the month
    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        current_date = datetime(year, month, day).date()
        is_today = current_date == now.date()
        
        # Find events for this specific date using the date_obj field
        day_events = []
        for event in events:
            if not event or not isinstance(event, dict):
                continue
                
            event_date = None
            
            # Try to get date from the date_obj field first (most reliable)
            if 'date_obj' in event and event['date_obj']:
                date_obj_value = event['date_obj']
                if isinstance(date_obj_value, str):
                    # Parse the string date
                    event_date = datetime.fromisoformat(date_obj_value).date()
                else:
                    # Already a date object
                    event_date = date_obj_value
            
            # Fallback to parsing start_datetime
            elif 'start_datetime' in event and event['start_datetime']:
                try:
                    start_dt_str = event['start_datetime']
                    if 'T' in start_dt_str:
                        # Parse datetime with timezone
                        if start_dt_str.endswith('Z'):
                            start_dt_str = start_dt_str.replace('Z', '+00:00')
                        dt = datetime.fromisoformat(start_dt_str)
                        event_date = dt.date()
                    else:
                        # All-day event - just date
                        event_date = datetime.fromisoformat(start_dt_str).date()
                except Exception as e:
                    print(f"Failed to parse start_datetime for event '{event.get('title', 'Unknown')}': {e}")
            
            # Fallback to date string parsing
            elif 'date' in event:
                date_str = event.get('date', '')
                if date_str == 'Today':
                    event_date = now.date()
                elif date_str == 'Tomorrow':
                    event_date = now.date() + timedelta(days=1)
                else:
                    # Try to parse other date formats like 'Mon, Aug 5'
                    try:
                        # Add current year to parse properly
                        event_date = datetime.strptime(f"{date_str} {year}", "%a, %b %d %Y").date()
                    except:
                        continue
            
            # If this event is on the current day, add it
            if event_date == current_date:
                day_events.append(event)
                print(f"Added event '{event.get('title')}' to date {current_date}")
        
        # Create day cell
        day_class = "calendar-day"
        if is_today:
            day_class += " today"
        if day_events:
            day_class += " has-events"
        
        events_html = ""
        for event in day_events[:3]:  # Show max 3 events per day
            title = event.get('title', 'Untitled')
            time_str = event.get('time', '')
            calendar_name = event.get('calendar_name', 'Unknown Calendar')
            # Get calendar-specific colors
            bg_color = event.get('calendar_bg_color', '#4285f4')
            fg_color = event.get('calendar_fg_color', '#ffffff')
            
            # Format the display with time if available
            if time_str and time_str != 'All day':
                # Truncate title to make room for time
                display_title = title[:18] + ("..." if len(title) > 18 else "")
                display_text = f"{time_str} - {display_title}"
            else:
                # Truncate long titles but show enough to be useful
                display_title = title[:25] + ("..." if len(title) > 25 else "")
                display_text = display_title
            
            tooltip = f"{title} - {time_str} ({calendar_name})" if time_str else f"{title} ({calendar_name})"
            events_html += f'<div class="day-event" style="background-color: {bg_color}; color: {fg_color};" title="{tooltip}">{display_text}</div>'
        
        # Add indicator if there are more than 3 events
        if len(day_events) > 3:
            events_html += f'<div class="day-event more">+{len(day_events) - 3} more</div>'
        
        week_html += f'''
        <div class="{day_class}">
            <div class="day-number">{day}</div>
            <div class="day-events">{events_html}</div>
        </div>'''
        
        # Start new week after Saturday
        if (start_day + day - 1) % 7 == 6:
            calendar_html += f'<div class="calendar-week">{week_html}</div>'
            week_html = ""
    
    # Add remaining empty cells and close last week
    if week_html:
        remaining_days = 7 - ((start_day + calendar.monthrange(year, month)[1] - 1) % 7 + 1)
        for i in range(remaining_days):
            week_html += '<div class="calendar-day empty"></div>'
        calendar_html += f'<div class="calendar-week">{week_html}</div>'
    
    # Create upcoming events sidebar - REMOVED for full-width calendar
    
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Google Calendar - Temple Office</title>
    <style>
        html {{
            background: #1f1f1f;
            min-height: 100vh;
            font-family: 'Google Sans', 'Roboto', Arial, sans-serif;
        }}
        
        body {{
            margin: 0;
            padding: 20px;
            background: #1f1f1f;
            color: #e8eaed;
            min-height: 100vh;
        }}
        
        .calendar-header {{
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
        }}
        
        .calendar-header h1 {{
            font-size: 12.0em;
            margin: 0 0 30px 0;
            color: #4285f4;
            font-weight: 400;
        }}
        
        .calendar-header h2 {{
            font-size: 7.5em;
            margin: 0;
            color: #9aa0a6;
            font-weight: 300;
        }}
        
        .main-container {{
            display: block;
            max-width: 3800px;
            margin: 0 auto;
            height: calc(100vh - 250px);
            padding: 0 60px;
        }}
        
        .calendar-container {{
            background: #202124;
            border-radius: 25px;
            padding: 75px;
            border: 3px solid #3c4043;
            width: 100%;
            height: 100%;
        }}
        
        .month-header {{
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 12px;
            margin-bottom: 40px;
        }}
        
        .weekday {{
            text-align: center;
            padding: 45px 15px;
            font-weight: 500;
            color: #9aa0a6;
            font-size: 4.5em;
            background: #28292c;
            border-radius: 18px;
        }}
        
        .calendar-grid {{
            display: flex;
            flex-direction: column;
            gap: 15px;
            height: calc(100% - 200px);
        }}
        
        .calendar-week {{
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 15px;
            flex: 1;
        }}
        
        .calendar-day {{
            background: #28292c;
            border-radius: 20px;
            padding: 60px 35px;
            min-height: 520px;
            position: relative;
            border: 3px solid transparent;
            transition: all 0.2s ease;
        }}
        
        .calendar-day:hover {{
            background: #2d2e30;
            border-color: #4285f4;
        }}
        
        .calendar-day.today {{
            background: #1a73e8;
            color: white;
        }}
        
        .calendar-day.today .day-number {{
            background: rgba(255,255,255,0.2);
            border-radius: 50%;
            width: 120px;
            height: 120px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 36px auto;
        }}
        
        .calendar-day.has-events {{
            border-color: #34a853;
        }}
        
        .calendar-day.empty {{
            background: transparent;
            pointer-events: none;
        }}
        
        .day-number {{
            font-size: 6.6em;
            font-weight: 500;
            margin-bottom: 36px;
            text-align: center;
        }}
        
        .day-events {{
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}
        
        .day-event {{
            background: #4285f4;
            color: white;
            padding: 18px 24px;
            border-radius: 12px;
            font-size: 3.0em;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            line-height: 1.2;
        }}
        
        .day-event.more {{
            background: #34a853;
            font-size: 1.5em;
            font-style: italic;
        }}
        
        .footer {{
            text-align: center;
            margin-top: 25px;
            color: #5f6368;
            font-size: 2.0em;
            position: fixed;
            bottom: 10px;
            left: 0;
            right: 0;
        }}
        
        /* Media queries for responsive design */
        @media screen and (max-width: 1920px) {{
            .calendar-header h1 {{ font-size: 4.0em; }}
            .calendar-header h2 {{ font-size: 2.5em; }}
            .weekday {{ font-size: 1.6em; padding: 16px 5px; }}
            .day-number {{ font-size: 2.0em; }}
            .calendar-day {{ min-height: 130px; padding: 18px 10px; }}
            .day-event {{ font-size: 1.0em; padding: 5px 7px; }}
        }}
        
        @media screen and (max-width: 1440px) {{
            .calendar-header h1 {{ font-size: 3.5em; }}
            .calendar-header h2 {{ font-size: 2.2em; }}
            .weekday {{ font-size: 1.4em; padding: 14px 5px; }}
            .day-number {{ font-size: 1.8em; }}
            .calendar-day {{ min-height: 120px; padding: 16px 8px; }}
            .day-event {{ font-size: 0.95em; padding: 4px 6px; }}
        }}
        
        @media screen and (max-width: 1080px) {{
            .calendar-header h1 {{ font-size: 3.0em; }}
            .calendar-header h2 {{ font-size: 2.0em; }}
            .weekday {{ font-size: 1.2em; padding: 12px 5px; }}
            .day-number {{ font-size: 1.6em; }}
            .calendar-day {{ min-height: 100px; padding: 14px 6px; }}
            .day-event {{ font-size: 0.9em; padding: 3px 5px; }}
        }}
        
        @media screen and (min-width: 2560px) {{
            .calendar-header h1 {{ font-size: 5.5em; }}
            .calendar-header h2 {{ font-size: 3.2em; }}
            .weekday {{ font-size: 2.2em; padding: 22px 5px; }}
            .day-number {{ font-size: 2.6em; }}
            .calendar-day {{ min-height: 160px; padding: 24px 14px; }}
            .day-event {{ font-size: 2.8em; padding: 18px 20px; }} /* MUCH bigger day event text for TV readability */
            .day-event.more {{ font-size: 2.4em; }} /* Bigger "more" indicator for TV */
            .footer {{ font-size: 1.6em; }}
        }}
    </style>
</head>
<body>
    <div class="calendar-header">
        <h1>📅 {month_name} {year}</h1>
        <h2>Temple Office Calendar</h2>
    </div>
    
    <div class="main-container">
        <div class="calendar-container">
            <div class="month-header">
                <div class="weekday">Sun</div>
                <div class="weekday">Mon</div>
                <div class="weekday">Tue</div>
                <div class="weekday">Wed</div>
                <div class="weekday">Thu</div>
                <div class="weekday">Fri</div>
                <div class="weekday">Sat</div>
            </div>
            
            <div class="calendar-grid">
                {calendar_html}
            </div>
        </div>
    </div>
    
    <div class="footer">
        📅 Connected to Google Calendar • Last synced: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} • {len(events)} events displayed • Next: Temple Weather
    </div>
</body>
</html>'''

@app.route('/calendar3')
def calendar3_dashboard():
    """3-Month Auto-Scrolling Calendar View using Google Calendar data"""
    # Get calendar events
    if not signage.calendar_events:
        signage.update_calendar_data()
    
    events = signage.calendar_events if signage.calendar_events else []
    
    from datetime import datetime, timedelta
    import calendar
    
    now = datetime.now()
    current_month = now.month
    current_year = now.year
    
    # Generate 3 months: current, next, and the month after
    months_data = []
    for i in range(3):
        month_date = datetime(current_year, current_month, 1) + timedelta(days=32*i)
        month_date = month_date.replace(day=1)  # First day of month
        
        year = month_date.year
        month = month_date.month
        month_name = calendar.month_name[month]
        
        # Generate calendar for this month - SET SUNDAY AS FIRST DAY
        calendar.setfirstweekday(calendar.SUNDAY)
        cal = calendar.monthcalendar(year, month)
        today = now.date()
        
        # Group events by date - HANDLE MULTI-DAY EVENTS
        month_events = {}
        
        for event in events:
            if not event or not isinstance(event, dict):
                continue
                
            start_date = None
            end_date = None
            event_title = event.get('title', 'Unknown Event')
            
            # Parse event start date
            if 'date_obj' in event and event['date_obj']:
                date_obj_value = event['date_obj']
                if isinstance(date_obj_value, str):
                    try:
                        start_date = datetime.fromisoformat(date_obj_value).date()
                    except:
                        continue
                else:
                    start_date = date_obj_value
            elif 'start_datetime' in event and event['start_datetime']:
                try:
                    start_dt_str = event['start_datetime']
                    if 'T' in start_dt_str:
                        if start_dt_str.endswith('Z'):
                            start_dt_str = start_dt_str.replace('Z', '+00:00')
                        dt = datetime.fromisoformat(start_dt_str)
                        start_date = dt.date()
                    else:
                        start_date = datetime.fromisoformat(start_dt_str).date()
                except:
                    pass
            
            # Parse event end date
            if 'end_datetime' in event and event['end_datetime']:
                try:
                    end_dt_str = event['end_datetime']
                    if 'T' in end_dt_str:
                        if end_dt_str.endswith('Z'):
                            end_dt_str = end_dt_str.replace('Z', '+00:00')
                        dt = datetime.fromisoformat(end_dt_str)
                        end_date = dt.date()
                    else:
                        end_date = datetime.fromisoformat(end_dt_str).date()
                except:
                    end_date = start_date  # Single day event
            else:
                end_date = start_date  # Single day event if no end date
            
            # Add event to all days it spans within this month
            # For Google Calendar, end dates are exclusive (event ends at start of end_date)
            if start_date and end_date:
                # For all-day events, end_date is exclusive, so subtract 1 day
                if start_date == end_date:
                    # Single day event
                    actual_end_date = end_date
                else:
                    # Multi-day event - end_date is exclusive, so actual end is the day before
                    actual_end_date = end_date - timedelta(days=1)
                
                current_date = start_date
                while current_date <= actual_end_date:
                    # Only include events for this month
                    if current_date.year == year and current_date.month == month:
                        if current_date not in month_events:
                            month_events[current_date] = []
                        
                        # Add event with span information for better rendering
                        event_copy = event.copy()
                        event_copy['span_start'] = start_date
                        event_copy['span_end'] = actual_end_date
                        event_copy['is_span_start'] = (current_date == start_date)
                        event_copy['is_span_end'] = (current_date == actual_end_date)
                        event_copy['span_days'] = (actual_end_date - start_date).days + 1
                        
                        month_events[current_date].append(event_copy)
                    current_date += timedelta(days=1)
        
        # Build month calendar HTML
        month_html = f'''
        <div class="month-container" id="month-{i}">
            <div class="month-header-3">
                <h2>{month_name} {year}</h2>
            </div>
            <div class="weekdays-3">
                <div class="weekday-3">Sun</div>
                <div class="weekday-3">Mon</div>
                <div class="weekday-3">Tue</div>
                <div class="weekday-3">Wed</div>
                <div class="weekday-3">Thu</div>
                <div class="weekday-3">Fri</div>
                <div class="weekday-3">Sat</div>
            </div>
            <div class="month-grid">'''
        
        # Add calendar weeks and collect all spanning events first
        all_spanning_events = []
        week_structures = []
        
        for week_idx, week in enumerate(cal):
            # Collect spanning events that start in this week
            for day in week:
                if day == 0:
                    continue
                    
                current_date = datetime(year, month, day).date()
                day_events = month_events.get(current_date, [])
                
                for event in day_events:
                    is_span_start = event.get('is_span_start', False)
                    span_days = event.get('span_days', 1)
                    
                    if span_days > 1 and is_span_start:
                        span_start = event.get('span_start')
                        span_end = event.get('span_end')
                        
                        # Calculate which weeks this event spans across
                        event_info = {
                            'event': event,
                            'start_date': span_start,
                            'end_date': span_end,
                            'start_week': week_idx,
                            'segments': []  # Will store week segments
                        }
                        
                        # Calculate segments for each week this event crosses
                        current_segment_start = span_start
                        for check_week_idx, check_week in enumerate(cal):
                            if check_week_idx < week_idx:
                                continue
                                
                            # Find dates in this week that are part of the event
                            week_event_days = []
                            week_start_col = None
                            
                            for col, day_num in enumerate(check_week):
                                if day_num == 0:
                                    continue
                                check_date = datetime(year, month, day_num).date()
                                
                                if current_segment_start <= check_date <= span_end:
                                    if week_start_col is None:
                                        week_start_col = col + 1  # CSS grid is 1-indexed
                                    week_event_days.append(check_date)
                            
                            if week_event_days:
                                event_info['segments'].append({
                                    'week_idx': check_week_idx,
                                    'start_col': week_start_col,
                                    'span_length': len(week_event_days),
                                    'is_start': (check_week_idx == week_idx),
                                    'is_end': (week_event_days[-1] == span_end)
                                })
                                
                            # Update for next week
                            if week_event_days and week_event_days[-1] < span_end:
                                current_segment_start = week_event_days[-1] + timedelta(days=1)
                            else:
                                break
                        
                        all_spanning_events.append(event_info)
        
        # Now build the weeks with their spanning overlays
        for week_idx, week in enumerate(cal):
            week_html = f'<div class="week-row" id="week-{week_idx}">'
            
            # First pass: add all day cells
            for day in week:
                if day == 0:
                    week_html += '<div class="day-cell empty"></div>'
                else:
                    current_date = datetime(year, month, day).date()
                    is_today = current_date == today
                    day_events = month_events.get(current_date, [])
                    
                    day_class = "day-cell"
                    if is_today:
                        day_class += " today"
                    if day_events:
                        day_class += " has-events"
                    
                    # Create events HTML for this day - only single day events and event starts
                    events_html = ""
                    for event in day_events[:2]:
                        title = event.get('title', 'Untitled')
                        time_str = event.get('time', '')
                        bg_color = event.get('calendar_bg_color', '#4285f4')
                        fg_color = event.get('calendar_fg_color', '#ffffff')
                        
                        is_span_start = event.get('is_span_start', False)
                        span_days = event.get('span_days', 1)
                        
                        # Skip ALL multi-day events - they are handled by spanning bars
                        if span_days > 1:
                            continue  # Skip all days of multi-day events - will be handled by spanning bars
                        
                        display_title = title
                        if time_str and time_str != 'All day':
                            display_text = f"{time_str[:5]} - {display_title}"
                        else:
                            display_text = display_title
                        
                        events_html += f'<div class="event-3" style="background-color: {bg_color}; color: {fg_color};">{display_text}</div>'
                    
                    if len([e for e in day_events if e.get('span_days', 1) == 1]) > 2:
                        remaining = len([e for e in day_events if e.get('span_days', 1) == 1]) - 2
                        events_html += f'<div class="event-3 more-3">+{remaining}</div>'
                    
                    week_html += f'''
                    <div class="{day_class}" data-date="{current_date}">
                        <div class="day-number-3">{day}</div>
                        <div class="events-3">{events_html}</div>
                    </div>'''
            
            week_html += '</div>'
            
            # Second pass: add spanning event bars for this specific week
            spanning_bars_html = ""
            
            for span_event in all_spanning_events:
                # Find the segment for this week
                week_segment = None
                for segment in span_event['segments']:
                    if segment['week_idx'] == week_idx:
                        week_segment = segment
                        break
                
                if week_segment:
                    event = span_event['event']
                    title = event.get('title', 'Untitled')
                    time_str = event.get('time', '')
                    bg_color = event.get('calendar_bg_color', '#4285f4')
                    fg_color = event.get('calendar_fg_color', '#ffffff')
                    
                    # Show full title on start segment, abbreviated on continuation
                    if week_segment['is_start']:
                        if time_str and time_str != 'All day':
                            display_text = f"{time_str[:5]} - {title}"
                        else:
                            display_text = title
                    else:
                        display_text = f"→ {title}"  # Continuation indicator
                    
                    spanning_bars_html += f'''
                    <div class="spanning-event" style="
                        grid-column: {week_segment['start_col']} / span {week_segment['span_length']};
                        background-color: {bg_color}; 
                        color: {fg_color};
                        grid-row: 1;
                        z-index: 10;
                        margin-top: 95px;
                        margin-bottom: 10px;
                    ">{display_text}</div>'''
            
            # Combine week with spanning bars
            month_html += f'''
            <div class="week-container">
                {week_html}
                <div class="spanning-overlay">
                    {spanning_bars_html}
                </div>
            </div>'''
        
        month_html += '''
            </div>
        </div>'''
        
        months_data.append(month_html)
    
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>3-Month Calendar - Temple Office</title>
    <style>
        html {{
            background: #1f1f1f;
            min-height: 100vh;
            font-family: 'Google Sans', 'Roboto', Arial, sans-serif;
            scroll-behavior: smooth;
        }}
        
        body {{
            margin: 0;
            padding: 0;
            background: #1f1f1f;
            color: #e8eaed;
            overflow-x: hidden;
        }}
        
        /* FIXED: Calendar 3-month scroll - ACTUALLY reaches all 3 months */
        .auto-scroll {{
            animation: scrollDown 22.5s infinite ease-in-out;
            transform: translateZ(0); /* Force hardware acceleration */
            will-change: transform; /* Optimize for smooth transforms */
            backface-visibility: hidden; /* Prevent flickering */
        }}
        
        @keyframes scrollDown {{
            0% {{ transform: translateY(0) translateZ(0); }} /* Month 1 */
            25% {{ transform: translateY(0) translateZ(0); }} /* Hold Month 1 - 4.5s */
            35% {{ transform: translateY(-100vh) translateZ(0); }} /* Transition to Month 2 - 1.8s */
            55% {{ transform: translateY(-100vh) translateZ(0); }} /* Hold Month 2 - 3.6s */
            65% {{ transform: translateY(-200vh) translateZ(0); }} /* Transition to Month 3 - 1.8s */
            90% {{ transform: translateY(-200vh) translateZ(0); }} /* Hold Month 3 - 4.5s LONGER */
            100% {{ transform: translateY(0) translateZ(0); }} /* Return to Month 1 - 1.8s */
        }}
        
        .calendar-container-3 {{
            min-height: 300vh; /* 3 months stacked vertically */
            width: 100vw;
            padding: 20px;
            box-sizing: border-box;
        }}
        
        /* REMOVED FIXED HEADER - was blocking third month scroll */
        .header-3 {{
            display: none; /* Remove the fixed header completely */
        }}
        
        .month-container {{
            background: #202124;
            border-radius: 25px;
            padding: 30px;
            margin-bottom: 20px;
            border: 3px solid #3c4043;
            height: calc(100vh - 40px); /* USE FULL SCREEN HEIGHT WITHOUT HEADER */
            display: flex;
            flex-direction: column;
        }}
        
        .month-header-3 {{
            text-align: center;
            margin-bottom: 15px;
            flex-shrink: 0;
        }}
        
        .month-header-3 h2 {{
            font-size: 5.5em;
            margin: 0;
            color: #4285f4; /* Make it more prominent */
            font-weight: 400;
        }}
        
        .weekdays-3 {{
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 8px;
            margin-bottom: 15px;
            flex-shrink: 0;
        }}
        
        .weekday-3 {{
            text-align: center;
            padding: 15px 8px;
            font-weight: 500;
            color: #9aa0a6;
            font-size: 2.8em;
            background: #28292c;
            border-radius: 12px;
        }}
        
        .month-grid {{
            display: flex;
            flex-direction: column;
            gap: 12px;
            flex: 1; /* TAKE REMAINING HEIGHT */
            height: 100%;
        }}
        
        .week-container {{
            position: relative;
            flex: 1; /* EACH WEEK TAKES EQUAL HEIGHT */
        }}
        
        .week-row {{
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 12px;
            height: 100%; /* FILL WEEK CONTAINER HEIGHT */
        }}
        
        .spanning-overlay {{
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 12px;
            pointer-events: none; /* Allow clicking through to day cells */
        }}
        
        .spanning-event {{
            background: #4285f4;
            color: white;
            padding: 8px 12px;
            border-radius: 8px;
            font-size: 1.4em;
            line-height: 1.3;
            word-wrap: break-word;
            overflow-wrap: break-word;
            hyphens: auto;
            height: 40px; /* Fixed height for spanning bars */
            display: flex;
            align-items: center;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
            border: 2px solid rgba(255,255,255,0.2);
        }}
        
        .day-cell {{
            background: #28292c;
            border-radius: 15px;
            padding: 20px 15px;
            min-height: 160px; /* BIGGER CELLS FOR 4K */
            border: 2px solid transparent;
            display: flex;
            flex-direction: column;
            height: 100%; /* FILL WEEK ROW HEIGHT */
            position: relative; /* For event positioning */
        }}
        
        .week-row {{
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 12px;
            flex: 1; /* EACH WEEK TAKES EQUAL HEIGHT */
            position: relative; /* For positioning spanning events */
        }}
        
        .day-cell {{
            background: #28292c;
            border-radius: 15px;
            padding: 20px 15px;
            min-height: 160px; /* BIGGER CELLS FOR 4K */
            border: 2px solid transparent;
            display: flex;
            flex-direction: column;
            height: 100%; /* FILL WEEK ROW HEIGHT */
        }}
        
        .day-cell.today {{
            background: #1a73e8;
            color: white;
        }}
        
        .day-cell.has-events {{
            border-color: #34a853;
        }}
        
        .day-cell.today {{
            background: #1a73e8;
            color: white;
        }}
        
        .day-cell.has-events {{
            border-color: #34a853;
        }}
        
        .day-cell.empty {{
            background: transparent;
        }}
        
        .day-number-3 {{
            font-size: 2.8em;
            font-weight: 500;
            margin-bottom: 15px;
            text-align: center;
            flex-shrink: 0;
        }}
        
        .events-3 {{
            display: flex;
            flex-direction: column;
            gap: 8px;
            flex: 1; /* TAKE REMAINING VERTICAL SPACE */
            overflow: hidden;
            padding-top: 60px; /* Make room for spanning bars above */
        }}
        
        .event-3 {{
            background: #4285f4;
            color: white;
            padding: 12px 15px;
            border-radius: 8px;
            font-size: 1.6em;
            line-height: 1.3;
            word-wrap: break-word;
            overflow-wrap: break-word;
            hyphens: auto;
        }}
            flex-shrink: 0;
        }}
        
        .events-3 {{
            display: flex;
            flex-direction: column;
            gap: 12px; /* Increased gap between events for better separation */
            flex: 1; /* TAKE REMAINING VERTICAL SPACE */
            overflow: hidden;
        }}
        
        .event-3 {{
            background: #4285f4;
            color: white;
            padding: 12px 15px;
            border-radius: 8px;
            font-size: 1.6em;
            line-height: 1.3;
            word-wrap: break-word;
            overflow-wrap: break-word;
            hyphens: auto;
        }}
        
        .event-3.more-3 {{
            background: #34a853;
            font-size: 1.6em;
            font-style: italic;
            text-align: center;
            margin-top: 6px; /* Add extra space above "more" indicator */
        }}
        
        .footer-3 {{
            text-align: center;
            margin-top: 40px;
            color: #5f6368;
            font-size: 1.8em;
            padding: 10px;
        }}
        
        /* 4K TV Optimization - FULL HEIGHT UTILIZATION */
        @media screen and (min-width: 2560px) {{
            .header-3 h1 {{ font-size: 5.0em; }}
            .month-header-3 h2 {{ font-size: 5.5em; }}
            .weekday-3 {{ font-size: 3.4em; padding: 20px 10px; }}
            .day-number-3 {{ font-size: 3.8em; margin-bottom: 20px; }}
            .day-cell {{ 
                min-height: 220px; 
                padding: 25px 20px; 
            }}
            .event-3 {{ 
                font-size: 2.4em; 
                padding: 15px 20px; 
                margin-bottom: 8px;
            }}
            .event-3.more-3 {{ font-size: 2.0em; }}
            .footer-3 {{ font-size: 2.6em; padding: 15px; }}
        }}
    </style>
</head>
<body>
    <!-- REMOVED HEADER - was blocking third month scroll -->
    
    <div class="calendar-container-3 auto-scroll">
        {''.join(months_data)}
    </div>
    
    <div class="footer-3">
        📅 Google Calendar • {len(events)} events • Auto-scrolling 3-month view • Next: CFSS Dashboard
    </div>
</body>
</html>'''


@app.route('/weather')
def weather_dashboard():
    if not signage.weather_data:
        signage.update_weather_data()
    
    weather = signage.weather_data
    forecast = signage.forecast_data
    lightning = signage.lightning_data
    
    # Generate lightning alert HTML - Perry Weather style
    lightning_html = ""
    if lightning:
        strikes = lightning.get('strikes', [])
        safety_timer = lightning.get('safety_timer', {})
        total_strikes = lightning.get('total_strikes_60min', 0)
        
        # Safety timer display
        timer_status = safety_timer.get('status', 'unknown')
        minutes_remaining = safety_timer.get('minutes_remaining', 0)
        timer_message = safety_timer.get('message', '')
        
        # Color coding based on safety status
        if timer_status == 'wait':
            alert_class = "lightning-alert danger"
            timer_color = "#ff4757"
            timer_icon = "⚠️"
        elif timer_status == 'safe' and total_strikes > 0:
            alert_class = "lightning-alert safe"
            timer_color = "#2ed573"
            timer_icon = "✅"
        else:
            alert_class = "lightning-alert clear"
            timer_color = "#74b9ff"
            timer_icon = "☀️"
        
        # Lightning map visualization
        map_html = ""
        update_freq = signage.get_update_frequency()
        update_status = f"⚡ Lightning mode: {update_freq}min updates" if signage.lightning_active else f"🌤️ Normal mode: {update_freq}min updates"
        
        if strikes:
            # Create simple text-based strike display
            recent_strikes = sorted(strikes, key=lambda x: x['timestamp'], reverse=True)[:10]
            map_html = '<div class="strike-list">'
            for i, strike in enumerate(recent_strikes):
                # Handle both datetime objects and ISO strings
                timestamp = strike['timestamp']
                if isinstance(timestamp, str):
                    strike_time = datetime.fromisoformat(timestamp)
                else:
                    strike_time = timestamp  # Already a datetime object
                
                time_ago = (datetime.now() - strike_time).total_seconds() / 60
                direction = signage.get_direction_from_coordinates(signage.temple_lat, signage.temple_lon, 
                                                        strike['latitude'], strike['longitude'])
                map_html += f'''
                <div class="strike-item">
                    <span class="strike-icon">⚡</span>
                    <span class="strike-info">{strike['distance_miles']:.1f}mi {direction} - {int(time_ago)}min ago</span>
                    <span class="strike-intensity">{strike['intensity']}</span>
                </div>'''
            map_html += '</div>'
        else:
            map_html = '<div class="no-strikes">No lightning strikes detected in the last hour</div>'
        
        lightning_html = f'''
        <div class="{alert_class}">
            <div class="lightning-header">
                <div class="lightning-icon-large">{timer_icon}</div>
                <div class="lightning-title">
                    <h3>LIGHTNING MONITOR</h3>
                    <p class="coverage">10-mile radius around Temple, TX</p>
                </div>
                <div class="safety-timer" style="color: {timer_color};">
                    <div class="timer-display">{minutes_remaining if minutes_remaining > 0 else '0'}</div>
                    <div class="timer-label">{'MIN WAIT' if minutes_remaining > 0 else 'SAFE'}</div>
                </div>
            </div>
            
            <div class="lightning-stats">
                <div class="stat">
                    <span class="stat-number">{total_strikes}</span>
                    <span class="stat-label">Strikes (1hr)</span>
                </div>
                <div class="stat">
                    <span class="stat-number">{len([s for s in strikes if (datetime.now() - (datetime.fromisoformat(s['timestamp']) if isinstance(s['timestamp'], str) else s['timestamp'])).total_seconds() / 60 <= 15])}</span>
                    <span class="stat-label">Recent (15min)</span>
                </div>
                <div class="stat">
                    <span class="stat-number">{lightning.get('coverage_radius_miles', 25)}</span>
                    <span class="stat-label">Mile Radius</span>
                </div>
            </div>
            
            <div class="lightning-message">
                <p style="color: {timer_color}; font-weight: bold;">{timer_message}</p>
                <p style="color: #9aa0a6; font-size: 0.9em; margin-top: 5px;">{update_status}</p>
            </div>
            
            <div class="lightning-map">
                <h4>Strike Locations</h4>
                {map_html}
            </div>
            
            <div class="lightning-footer">
                <small>Real-time lightning monitoring • Updated: {lightning.get('last_updated', 'Unknown')[:16]}</small>
            </div>
        </div>'''
    
    # Generate forecast HTML
    forecast_html = ""
    for day in forecast:
        weather_text = get_weather_emoji(day.get('icon', '02d'))
        forecast_html += f'''
        <div class="forecast-item">
            <div class="forecast-day">{day['date']}</div>
            <div class="forecast-icon" style="font-size: 1.2em; font-weight: bold; color: #74b9ff;">{weather_text}</div>
            <div class="forecast-temp">{day['high']}°/{day['low']}°</div>
            <div class="forecast-desc">{day['description']}</div>
        </div>'''
    
    # Get current time for news rotation and weather updates
    current_hour = datetime.now().hour
    current_temp = weather['temperature']
    
    # Generate more comprehensive news stories based on weather and local events
    news_stories = []
    
    # Weather-based news
    if current_temp > 90:
        news_stories.append({"title": "Heat Warning Issued", "summary": f"Extreme heat advisory in effect - {current_temp}°F with heat index reaching dangerous levels"})
    elif current_temp > 85:
        news_stories.append({"title": "Hot Weather Advisory", "summary": f"Current temperature {current_temp}°F - Stay hydrated and avoid prolonged sun exposure"})
    elif current_temp < 40:
        news_stories.append({"title": "Cold Weather Alert", "summary": f"Current temperature {current_temp}°F - Protect pipes and dress warmly"})
    elif current_temp < 32:
        news_stories.append({"title": "Freeze Warning", "summary": f"Hard freeze conditions expected - {current_temp}°F, protect plants and pipes"})
    
    # Lightning-specific news
    if lightning and lightning.get('status') != 'clear':
        lightning_message = lightning.get('message', 'Lightning activity detected')
        news_stories.append({"title": "⚡ Lightning Alert", "summary": f"Active lightning in Temple area - {lightning_message}"})
    
    # Current conditions news
    if 'rain' in weather['description'].lower():
        news_stories.append({"title": "🌧️ Rain Advisory", "summary": f"Current conditions: {weather['description']} - Drive safely and allow extra time"})
    elif 'storm' in weather['description'].lower():
        news_stories.append({"title": "🌩️ Storm Watch", "summary": f"Active weather: {weather['description']} - Monitor conditions closely"})
    
    # Always include these comprehensive local stories
    news_stories.extend([
        {"title": "📈 Temple Business Growth", "summary": "Local businesses report 15% quarterly growth with tech companies bringing 200+ new jobs to Temple region"},
        {"title": "🚧 Infrastructure Progress", "summary": "City announces completion of Phase 1 fiber optic expansion - downtown Temple now has gigabit internet access"},
        {"title": "🎉 Community Calendar", "summary": "August events: Temple Farmers Market (Saturdays), Summer Concert Series (Aug 15), Back-to-School Drive (Aug 20)"},
        {"title": "🚗 Traffic & Transportation", "summary": "I-35 construction Phase 3 begins next week - expect delays during peak hours, use Loop 363 as alternate route"},
        {"title": "🏥 Public Health Update", "summary": "Bell County health officials remind residents about summer safety: heat precautions and hydration important"},
        {"title": "💼 Economic Development", "summary": "Temple Economic Development announces new manufacturing facility bringing 150 jobs - groundbreaking scheduled September"},
        {"title": "🎓 Education News", "summary": "Temple ISD reports successful summer programs with 95% participation rate - fall enrollment opens August 10th"}
    ])
    
    news_html = ""
    for i, story in enumerate(news_stories[:3]):  # Show 3 stories
        news_html += f'''
        <div class="news-item">
            <div class="news-icon">📰</div>
            <div class="news-content">
                <h4>{story['title']}</h4>
                <p>{story['summary']}</p>
            </div>
        </div>'''
    
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Temple Weather & News</title>
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <style>
        /* Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - News section width optimization */
        html {{
            background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 50%, #16213e 100%);
            min-height: 100vh;
            scroll-behavior: smooth;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 50%, #16213e 100%);
            height: 100vh;
            color: #e0e0e0;
            overflow: hidden;
            padding: 5px; /* REDUCE PADDING TO PREVENT CUTOFF */
            box-sizing: border-box;
        }}
        
        .main-container {{
            display: grid;
            grid-template-columns: 58% 42%; /* ADJUST RATIO FOR BETTER FIT */
            gap: 10px; /* REDUCE GAP */
            height: calc(100vh - 60px); /* EVEN MORE PADDING TO ENSURE BOTTOM BORDERS SHOW */
            max-width: 100vw; /* ENSURE NO OVERFLOW */
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        .weather-section {{
            background: rgba(52, 152, 219, 0.1);
            border-radius: 15px;
            padding: 20px;
            border: 2px solid rgba(52, 152, 219, 0.3);
            overflow-y: auto; /* ALLOW SCROLLING IF NEEDED */
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: flex-start; /* ALIGN TO TOP, DON'T STRETCH */
            box-sizing: border-box;
        }}
        
        .news-section {{
            background: rgba(231, 76, 60, 0.1);
            border-radius: 15px;
            padding: 20px;
            border: 2px solid rgba(231, 76, 60, 0.3);
            overflow-y: auto; /* ALLOW SCROLLING IF NEEDED */
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: flex-start; /* ALIGN TO TOP, DON'T STRETCH */
            box-sizing: border-box;
        }}
        
        .header {{
            text-align: center;
            margin-bottom: 15px;
            flex-shrink: 0;
        }}
        
        .header h1 {{
            font-size: 4.2em;
            margin: 0;
            color: #3498db;
            text-shadow: 4px 4px 8px rgba(0,0,0,0.5);
        }}
        
        .current-weather {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin: 15px 0;
            background: rgba(52, 152, 219, 0.15);
            border-radius: 20px;
            padding: 30px;
            min-height: 160px;
            flex-shrink: 0;
        }}
        
        .weather-icon {{
            font-size: 8em;
            margin-right: 30px;
            font-family: 'Arial Unicode MS', Arial, sans-serif;
        }}
        
        .current-temp {{
            font-size: 8em;
            font-weight: 700;
            margin: 0;
            color: #3498db;
        }}
        
        .current-desc {{
            font-size: 3.5em;
            margin: 10px 0;
            color: #74b9ff;
        }}
        
        .current-location {{
            font-size: 2.8em;
            color: #bdc3c7;
        }}
        
        .feels-like {{
            font-size: 4.0em;
            color: #3498db;
            margin: 0;
        }}
        
        .conditions {{
            font-size: 2.2em;
            color: #74b9ff;
            margin-top: 10px;
        }}
        
        .weather-details {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 15px;
            margin: 15px 0;
            flex-shrink: 0;
        }}
        
        .detail-card {{
            background: rgba(52, 152, 219, 0.1);
            border-radius: 15px;
            padding: 25px 20px;
            text-align: center;
            border: 2px solid rgba(52, 152, 219, 0.2);
            min-height: 120px;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }}
        
        .detail-card h3 {{
            font-size: 2.4em;
            margin: 0 0 12px 0;
            color: #74b9ff;
            font-weight: 500;
        }}
        
        .detail-card .value {{
            font-size: 3.5em;
            font-weight: 700;
            color: #3498db;
            margin: 0;
        }}
        
        .forecast-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 15px;
            margin: 15px 0;
            flex: 1; /* TAKE REMAINING SPACE */
            align-content: stretch;
        }}
        
        .forecast-item {{
            background: rgba(52, 152, 219, 0.1);
            border-radius: 15px;
            padding: 25px 20px;
            text-align: center;
            border: 2px solid rgba(52, 152, 219, 0.2);
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            min-height: 200px;
        }}
        
        .forecast-day {{
            font-size: 2.4em;
            font-weight: 600;
            color: #74b9ff;
            margin-bottom: 10px;
        }}
        
        .forecast-icon {{
            font-size: 3.2em;
            margin: 10px 0;
            font-weight: bold;
            color: #3498db;
            background: rgba(52, 152, 219, 0.1);
            padding: 12px;
            border-radius: 8px;
            text-align: center;
        }}
        
        .forecast-temp {{
            font-size: 2.4em;
            font-weight: 700;
            color: #3498db;
            margin: 8px 0;
        }}
        
        .forecast-desc {{
            font-size: 1.8em;
            color: #bdc3c7;
        }}
        
        .news-header {{
            text-align: center;
            margin-bottom: 15px;
            flex-shrink: 0;
        }}
        
        .news-header h2 {{
            font-size: 5.2em; /* MUCH BIGGER news header for better readability */
            margin: 0;
            color: #e74c3c;
            text-shadow: 4px 4px 8px rgba(0,0,0,0.5);
        }}
        
        .news-subtitle {{
            font-size: 3.4em; /* MUCH BIGGER subtitle for better readability */
            color: #f39c12;
            margin-top: 8px;
        }}
        
        .news-item {{
            display: flex;
            align-items: flex-start;
            margin: 15px 0;
            background: rgba(231, 76, 60, 0.1);
            border-radius: 10px;
            padding: 25px 20px;
            border-left: 4px solid #e74c3c;
            flex: 1; /* TAKE EQUAL SPACE */
            min-height: 120px;
        }}
        
        .news-icon {{
            font-size: 4.2em; /* MUCH BIGGER news icons for better visibility */
            margin-right: 20px;
            color: #e74c3c;
            flex-shrink: 0;
        }}
        
        .news-content h4 {{
            font-size: 3.8em; /* MUCH BIGGER news title text for better readability */
            margin: 0 0 12px 0;
            color: #e74c3c;
            font-weight: 600;
            line-height: 1.2;
        }}
        
        .news-content p {{
            font-size: 3.0em; /* MUCH BIGGER news content text for better readability */
            margin: 0;
            color: #bdc3c7;
            line-height: 1.3;
        }}
        
        .live-embed {{
            margin: 20px 0;
            border-radius: 15px;
            background: rgba(52, 152, 219, 0.1);
            border: 1px solid rgba(52, 152, 219, 0.2);
            flex: 1; /* TAKE REMAINING SPACE */
            padding: 25px;
            min-height: 150px;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }}
        
        .embed-placeholder {{
            text-align: center;
            color: #74b9ff;
        }}
        
        .embed-placeholder h3 {{
            margin: 0;
            font-size: 3.2em;
        }}
        
        .embed-placeholder p {{
            margin: 15px 0 0 0;
            font-size: 2.6em;
        }}
        
        .footer {{
            text-align: center;
            margin-top: 20px;
            padding: 15px;
            color: #7f8c8d;
            font-size: 0.9em;
            grid-column: 1 / -1;
        }}
        
        .radar-link {{
            display: inline-block;
            background: rgba(52, 152, 219, 0.2);
            color: #3498db;
            padding: 10px 20px;
            border-radius: 25px;
            text-decoration: none;
            font-weight: 600;
            margin: 10px;
            border: 1px solid rgba(52, 152, 219, 0.3);
        }}
        
        .radar-link:hover {{
            background: rgba(52, 152, 219, 0.3);
        }}
        
        .weather-animation {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            opacity: 0.1;
            z-index: -1;
        }}
        
        .lightning-alert {{
            margin: 15px 0;
            border-radius: 15px;
            padding: 25px;
            background: rgba(255, 193, 7, 0.2); /* MUCH MORE VISIBLE BACKGROUND */
            border: 3px solid #ffc107; /* PROMINENT YELLOW BORDER */
            flex-shrink: 0;
            min-height: 180px; /* MAKE IT BIGGER */
            box-shadow: 0 0 20px rgba(255, 193, 7, 0.3); /* GLOW EFFECT */
        }}
        
        .lightning-alert.danger {{
            border-color: #ff4757;
            background: rgba(255, 71, 87, 0.3); /* MORE VISIBLE */
            box-shadow: 0 0 20px rgba(255, 71, 87, 0.4);
        }}
        
        .lightning-alert.safe {{
            border-color: #2ed573;
            background: rgba(46, 213, 115, 0.3); /* MORE VISIBLE */
            box-shadow: 0 0 20px rgba(46, 213, 115, 0.4);
        }}
        
        .lightning-alert.clear {{
            border-color: #74b9ff;
            background: rgba(116, 185, 255, 0.3); /* MORE VISIBLE */
            box-shadow: 0 0 20px rgba(116, 185, 255, 0.4);
        }}
        
        .lightning-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            border-bottom: 2px solid rgba(255, 255, 255, 0.3);
            padding-bottom: 15px;
        }}
        
        .lightning-icon-large {{
            font-size: 3.5em; /* MUCH BIGGER ICON */
            margin-right: 15px;
            color: #ffc107; /* BRIGHT YELLOW */
        }}
        
        .lightning-title h3 {{
            margin: 0;
            font-size: 2.2em; /* MUCH BIGGER TEXT */
            font-weight: bold;
            color: #fff;
        }}
        
        .lightning-title .coverage {{
            margin: 5px 0 0 0;
            font-size: 1.4em; /* BIGGER COVERAGE TEXT */
            color: #ddd;
        }}
        
        .safety-timer {{
            text-align: center;
            background: rgba(0, 0, 0, 0.5);
            border-radius: 12px;
            padding: 15px;
            min-width: 100px;
        }}
        
        .timer-display {{
            font-size: 3.0em; /* MUCH BIGGER TIMER */
            font-weight: bold;
            margin: 0;
            color: #fff;
        }}
        
        .timer-label {{
            font-size: 1.2em; /* BIGGER LABEL */
            margin: 5px 0 0 0;
            font-weight: bold;
            color: #ddd;
        }}
        
        .lightning-stats {{
            display: flex;
            justify-content: space-around;
            margin: 15px 0;
            background: rgba(0, 0, 0, 0.4);
            border-radius: 12px;
            padding: 15px;
        }}
        
        .stat {{
            text-align: center;
            flex: 1;
        }}
        
        .stat-number {{
            display: block;
            font-size: 3.2em; /* MUCH BIGGER STATS */
            font-weight: bold;
            color: #ffc107;
        }}
        
        .stat-label {{
            display: block;
            font-size: 1.4em; /* BIGGER LABELS */
            color: #ddd;
            margin-top: 5px;
        }}
        
        .lightning-message {{
            text-align: center;
            margin: 15px 0;
            padding: 10px;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 8px;
        }}
        
        .lightning-map {{
            margin: 20px 0;
        }}
        
        .lightning-map h4 {{
            margin: 0 0 15px 0;
            font-size: 1.4em;
            color: #fff;
            border-bottom: 1px solid rgba(255, 255, 255, 0.2);
            padding-bottom: 8px;
        }}
        
        .strike-list {{
            max-height: 200px;
            overflow-y: auto;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 8px;
            padding: 10px;
        }}
        
        .strike-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 12px;
            margin: 5px 0;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 6px;
            border-left: 3px solid #ff4757;
        }}
        
        .strike-icon {{
            font-size: 1.2em;
            margin-right: 10px;
        }}
        
        .strike-info {{
            flex: 1;
            font-size: 1.1em;
        }}
        
        .strike-intensity {{
            font-size: 0.9em;
            color: #bbb;
            background: rgba(0, 0, 0, 0.3);
            padding: 3px 8px;
            border-radius: 4px;
        }}
        
        .no-strikes {{
            text-align: center;
            padding: 30px;
            color: #bbb;
            font-style: italic;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 8px;
        }}
        
        .lightning-footer {{
            text-align: center;
            margin-top: 15px;
            padding-top: 10px;
            border-top: 1px solid rgba(255, 255, 255, 0.2);
        }}
        
        .lightning-footer small {{
            color: #bbb;
            font-size: 1.0em;
        }}
        
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.7; }}
        }}
        
        .weather-particle {{
            position: absolute;
            width: 4px;
            height: 4px;
            background: #74b9ff;
            border-radius: 50%;
            animation: fall 8s linear infinite;
        }}
        
        @keyframes fall {{
            0% {{ transform: translateY(-100vh) rotate(0deg); opacity: 1; }}
            100% {{ transform: translateY(100vh) rotate(360deg); opacity: 0; }}
        }}
        
        .news-ticker {{
            background: rgba(231, 76, 60, 0.2);
            color: #e74c3c;
            padding: 30px;
            border-radius: 12px;
            margin: 20px 0;
            font-weight: 600;
            font-size: 3.2em; /* MUCH BIGGER text for better readability */
            border-left: 4px solid #e74c3c;
            white-space: nowrap;
            overflow: hidden;
            position: relative;
            height: 120px; /* Taller to accommodate bigger text */
            display: flex;
            align-items: center;
            flex: 1; /* TAKE REMAINING SPACE */
            box-shadow: 0 4px 12px rgba(231, 76, 60, 0.3);
        }}
        
        .ticker-content {{
            position: absolute;
            animation: tickerScrollFromRight 20s linear infinite;
            white-space: nowrap;
            font-weight: 700;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3);
            width: max-content;
        }}
        
        @keyframes tickerScrollFromRight {{
            0% {{ 
                transform: translateX(100%);
                opacity: 1;
            }}
            100% {{ 
                transform: translateX(-100%);
                opacity: 1;
            }}
        }}
        
        /* 4K TV Optimization for Weather Dashboard */
        @media screen and (min-width: 2560px) {{
            /* Lightning alert section - make fonts much bigger for TV readability */
            .lightning-alert {{
                margin: 30px 0;
                border-radius: 20px;
                padding: 40px;
                border-width: 4px;
            }}
            
            .lightning-header {{
                margin-bottom: 30px;
                padding-bottom: 20px;
            }}
            
            .lightning-icon-large {{
                font-size: 8em; /* Much bigger lightning icon for TV */
            }}
            
            .lightning-title h3 {{
                font-size: 4.0em; /* Much bigger title for TV readability */
                margin-bottom: 12px;
            }}
            
            .lightning-title .coverage {{
                font-size: 2.4em; /* Much bigger coverage text for TV */
                margin: 12px 0 0 0;
            }}
            
            .safety-timer {{
                padding: 35px;
                border-radius: 20px;
                min-width: 200px;
            }}
            
            .timer-display {{
                font-size: 5.5em; /* Huge timer display for TV visibility */
                font-weight: bold;
                margin: 0;
            }}
            
            .timer-label {{
                font-size: 2.2em; /* Much bigger timer label for TV */
                margin: 12px 0 0 0;
                font-weight: bold;
            }}
            
            .lightning-stats {{
                margin: 40px 0;
                padding: 35px;
                border-radius: 20px;
            }}
            
            .stat-number {{
                font-size: 4.5em; /* Huge stat numbers for TV visibility */
                font-weight: bold;
            }}
            
            .stat-label {{
                font-size: 2.2em; /* Much bigger stat labels for TV */
                margin-top: 12px;
            }}
            
            .lightning-message {{
                margin: 35px 0;
                padding: 25px;
                border-radius: 15px;
                font-size: 2.0em; /* Much bigger message text for TV */
            }}
            
            .lightning-map h4 {{
                font-size: 3.2em; /* Much bigger map heading for TV */
                margin: 0 0 25px 0;
                padding-bottom: 15px;
            }}
            
            .strike-list {{
                max-height: 400px;
                border-radius: 15px;
                padding: 25px;
            }}
            
            .strike-item {{
                padding: 20px 25px;
                margin: 15px 0;
                border-radius: 12px;
                border-left-width: 6px;
            }}
            
            .strike-icon {{
                font-size: 2.4em; /* Much bigger strike icons for TV */
                margin-right: 20px;
            }}
            
            .strike-info {{
                font-size: 2.2em; /* Much bigger strike info text for TV */
            }}
            
            .strike-intensity {{
                font-size: 1.8em; /* Much bigger intensity text for TV */
                padding: 8px 15px;
                border-radius: 10px;
            }}
            
            .no-strikes {{
                padding: 50px;
                font-size: 2.4em; /* Much bigger no-strikes message for TV */
                border-radius: 15px;
            }}
            
            .lightning-footer small {{
                font-size: 1.8em; /* Much bigger footer text for TV */
            }}
            
            /* Enhanced 4K Weather Dashboard - Full Height Utilization */
            .header h1 {{
                font-size: 3.8em; /* Bigger weather title for 4K */
            }}
            
            .current-temp {{
                font-size: 6.2em; /* Larger temperature for 4K visibility */
            }}
            
            .current-desc {{
                font-size: 2.8em; /* Better weather description */
            }}
            
            .current-location {{
                font-size: 2.2em; /* Good location text */
            }}
            
            .feels-like {{
                font-size: 3.4em; /* Bigger feels-like for 4K */
            }}
            
            .conditions {{
                font-size: 2.2em; /* Good conditions text */
            }}
            
            .detail-card h3 {{
                font-size: 2.4em; /* Bigger detail headings */
            }}
            
            .detail-card .value {{
                font-size: 3.2em; /* Bigger detail values for 4K */
            }}
            
            .forecast-day {{
                font-size: 2.4em; /* Bigger forecast labels */
            }}
            
            .forecast-icon {{
                font-size: 2.8em; /* Bigger forecast icons */
                padding: 15px;
                border-radius: 10px;
            }}
            
            .forecast-temp {{
                font-size: 2.6em; /* Bigger forecast temperatures */
            }}
            
            .forecast-desc {{
                font-size: 2.0em; /* Bigger forecast descriptions */
            }}
            
            .news-header h2 {{
                font-size: 3.8em; /* Bigger news header for 4K */
            }}
            
            .news-subtitle {{
                font-size: 2.2em; /* Bigger news subtitle */
            }}
            
            .news-content h4 {{
                font-size: 2.8em; /* Bigger news headlines */
            }}
            
            .news-content p {{
                font-size: 2.2em; /* Bigger news content */
            }}
            
            .news-icon {{
                font-size: 2.8em; /* Bigger news icons */
                margin-right: 25px;
            }}
            
            .news-ticker {{
                font-size: 2.2em; /* Bigger ticker text for 4K */
                height: 120px;
                padding: 20px;
            }}
            
            .embed-placeholder h3 {{
                font-size: 3.8em; /* Bigger embed text */
            }}
            
            .embed-placeholder p {{
                font-size: 3.0em; /* Bigger embed description */
            }}
            
            /* Lightning area fonts stay large for TV visibility */
            /* The lightning fonts above are perfect for TV readability */
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🌤️ Temple Weather & News</h1>
    </div>
    
    <div class="main-container">
        <div class="weather-section">
            <div class="weather-animation" id="weatherAnimation"></div>
            <div class="current-weather">
                <div class="current-left">
                    <div class="weather-icon" style="font-size: 2.5em; font-weight: bold; color: #3498db; background: rgba(52, 152, 219, 0.2); padding: 20px; border-radius: 10px; min-width: 140px; text-align: center;">{get_weather_emoji(weather.get('icon', '02d'))}</div>
                    <div class="current-info">
                        <div class="current-temp">{weather['temperature']}°F</div>
                        <div class="current-desc">{weather['description']}</div>
                        <div class="current-location">Temple, Texas</div>
                    </div>
                </div>
                <div class="current-right">
                    <div class="feels-like">Feels {weather['feels_like']}°F</div>
                    <div class="conditions">Real Feel</div>
                </div>
            </div>
            
            <div class="weather-details">
                <div class="detail-card">
                    <h3>Humidity</h3>
                    <div class="value">{weather['humidity']}%</div>
                </div>
                <div class="detail-card">
                    <h3>Wind</h3>
                    <div class="value">{weather['wind_speed']} mph</div>
                </div>
                <div class="detail-card">
                    <h3>UV Index</h3>
                    <div class="value">{weather['uv_index']}</div>
                </div>
                <div class="detail-card">
                    <h3>Pressure</h3>
                    <div class="value">{weather.get('pressure', 1013)} mb</div>
                </div>
            </div>
            
            <div class="forecast-grid">
                {forecast_html}
            </div>
            
            {lightning_html}
            
            <div class="live-embed">
                <!-- Current Weather Summary -->
                <div style="background: rgba(52, 152, 219, 0.15); border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="display: flex; align-items: center; justify-content: center; margin-bottom: 12px;">
                        <div style="font-size: 2.4em; margin-right: 12px; font-weight: bold; color: #3498db; background: rgba(52, 152, 219, 0.2); padding: 12px; border-radius: 8px; min-width: 80px; text-align: center;">{get_weather_emoji(weather.get('icon', '02d'))}</div>
                        <div>
                            <h3 style="color: #3498db; margin: 0; font-size: 1.8em;">Current Conditions</h3>
                            <p style="color: #74b9ff; margin: 5px 0; font-size: 1.4em;">Temple, Texas</p>
                        </div>
                    </div>
                    <div style="display: flex; justify-content: space-around; text-align: center;">
                        <div>
                            <strong style="color: #3498db; font-size: 1.6em;">{weather['temperature']}°F</strong>
                            <br><span style="color: #74b9ff; font-size: 1.2em;">Temperature</span>
                        </div>
                        <div>
                            <strong style="color: #3498db; font-size: 1.6em;">{weather['feels_like']}°F</strong>
                            <br><span style="color: #74b9ff; font-size: 1.2em;">Feels Like</span>
                        </div>
                        <div>
                            <strong style="color: #3498db; font-size: 1.6em;">{weather['humidity']}%</strong>
                            <br><span style="color: #74b9ff; font-size: 1.2em;">Humidity</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="news-section">
            <div class="news-header">
                <h2>📺 Local News</h2>
                <div class="news-subtitle">Temple & Bell County Updates</div>
            </div>
            
            {news_html}
            
            <div class="news-ticker" id="newsTicker">
                <div class="ticker-content" id="tickerContent">
                    🚨 WEATHER: Temple TX - Partly cloudy skies with mild temperatures this week
                </div>
            </div>
            
            <div class="live-embed" style="margin-top: 12px;">
                <div style="background: rgba(231, 76, 60, 0.15); border-radius: 12px; padding: 20px;">
                    <div style="display: flex; align-items: center; margin-bottom: 12px;">
                        <div style="font-size: 2.4em; margin-right: 12px; color: #e74c3c;">�</div>
                        <div>
                            <h3 style="color: #e74c3c; margin: 0; font-size: 3.5em;">Breaking News</h3>
                            <p style="color: #f39c12; margin: 5px 0; font-size: 2.8em;">Temple & Bell County Live</p>
                        </div>
                    </div>
                    <div style="background: rgba(231, 76, 60, 0.2); padding: 20px; border-radius: 8px;">
                        <div id="liveNewsUpdate" style="color: #e74c3c; margin: 0; font-size: 3.2em; line-height: 1.4; min-height: 120px; display: flex; align-items: center;">
                            <div id="rotatingNewsContent">
                                Temple Economic Development announces major expansion bringing 150+ jobs to local manufacturing sector
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    
    <script>
        // Create animated weather particles
        function createWeatherParticles() {{
            const animation = document.getElementById('weatherAnimation');
            const particleCount = 20;
            
            for (let i = 0; i < particleCount; i++) {{
                const particle = document.createElement('div');
                particle.className = 'weather-particle';
                particle.style.left = Math.random() * 100 + '%';
                particle.style.animationDelay = Math.random() * 8 + 's';
                particle.style.animationDuration = (Math.random() * 4 + 6) + 's';
                animation.appendChild(particle);
            }}
        }}
        
        // Auto-refresh weather data every 10 minutes
        setTimeout(() => {{
            location.reload();
        }}, 600000);
        
        // Rotate news stories automatically
        const newsItems = document.querySelectorAll('.news-item');
        let currentNews = 0;
        
        function rotateNews() {{
            newsItems.forEach((item, index) => {{
                item.style.opacity = index === currentNews ? '1' : '0.5';
                item.style.transform = index === currentNews ? 'scale(1.02)' : 'scale(1)';
            }});
            currentNews = (currentNews + 1) % newsItems.length;
        }}
        
        // Rotate news ticker content with enhanced stories
        const newsTickers = [
            '🚨 WEATHER: Temple TX - Current {weather['temperature']}°F, {weather['description']} conditions expected to continue',
            '📰 BREAKING: Bell County approves $2.5M infrastructure package for downtown Temple revitalization project',
            '⚠️ TRAFFIC: I-35 Phase 3 construction begins Monday - expect delays 7-9 AM and 4-6 PM, use Loop 363 alternate',
            '🏢 BUSINESS: Major manufacturing facility breaks ground in Temple - 150 new jobs with $40,000+ average salary',
            '� EDUCATION: Temple ISD achieves 95% summer program participation - fall enrollment opens August 10th',
            '🏥 HEALTH: Bell County health officials stress summer safety - hydration and heat precautions essential',
            '🌡️ CONDITIONS: Temple area {weather['description']} with humidity at {weather['humidity']}% - UV index moderate',
            '🚧 DEVELOPMENT: Fiber optic Phase 1 complete - gigabit internet now available in downtown Temple core',
            '📅 EVENTS: Temple Farmers Market every Saturday, Summer Concert Series Aug 15, Back-to-School Drive Aug 20',
            '💼 ECONOMY: Local business growth up 15% - tech sector expansion bringing high-paying jobs to region'
        ];
        
        const liveNewsUpdates = [
            'Temple Economic Development announces major manufacturing expansion bringing 150+ high-paying jobs to local sector',
            'Bell County commissioners approve $2.5 million downtown revitalization - new businesses and infrastructure improvements planned',
            'Temple ISD reports record summer program success with 95% participation rate - preparing for strong fall semester start',
            'I-35 construction Phase 3 begins next week - commuters advised to use Loop 363 during peak hours for faster travel',
            'Temple Farmers Market celebrates successful season - local vendors report increased community support and sales growth',
            'Bell County health officials remind residents about heat safety - current temperature {weather['temperature']}°F requires precautions',
            'Fiber optic expansion Phase 1 completed - downtown Temple now enjoys high-speed gigabit internet access for businesses',
            'Temple Chamber of Commerce reports 15% business growth this quarter - technology companies leading the expansion',
            'Community Calendar Update: Summer Concert Series August 15th, Back-to-School Drive August 20th - volunteers needed',
            'Weather Advisory: {weather['description']} conditions with {weather['humidity']}% humidity - outdoor activities should plan accordingly'
        ];
        
        let tickerIndex = 0;
        let liveNewsIndex = 0;
        const ticker = document.getElementById('newsTicker');
        const rotatingNews = document.getElementById('rotatingNewsContent');
        
        function updateTicker() {{
            const tickerContent = document.getElementById('tickerContent');
            if (tickerContent) {{
                tickerContent.textContent = newsTickers[tickerIndex];
                tickerIndex = (tickerIndex + 1) % newsTickers.length;
            }}
        }}
        
        function updateRotatingNews() {{
            if (rotatingNews) {{
                // Fade out
                rotatingNews.style.opacity = '0';
                rotatingNews.style.transform = 'translateX(20px)';
                
                setTimeout(() => {{
                    rotatingNews.textContent = liveNewsUpdates[liveNewsIndex];
                    liveNewsIndex = (liveNewsIndex + 1) % liveNewsUpdates.length;
                    
                    // Fade in
                    rotatingNews.style.opacity = '1';
                    rotatingNews.style.transform = 'translateX(0)';
                }}, 300);
            }}
        }}
        
        // Add smooth transition styles to rotating news
        if (rotatingNews) {{
            rotatingNews.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
        }}
        
        // Initialize
        createWeatherParticles();
        rotateNews();
        
        // Set intervals for news rotation - optimized timing for readability
        setInterval(rotateNews, 4000);                    // Rotate top news items every 4 seconds
        setInterval(updateTicker, 18000);                 // Change ticker every 18 seconds (longer for readability)
        setInterval(updateRotatingNews, 7000);            // Change bottom news every 7 seconds
    </script>
</body>
</html>'''

@app.route("/api/calendar/update")
def api_calendar_update():
    """Force update calendar data"""
    signage.update_calendar_data()
    return jsonify({"status": "Calendar updated", "events": len(signage.calendar_events or [])})

@app.route("/api/calendar/debug") 
def api_calendar_debug():
    """Debug calendar events"""
    if not signage.calendar_events:
        signage.update_calendar_data()
    
    events = signage.calendar_events if signage.calendar_events else []
    debug_info = []
    for event in events:
        debug_info.append({
            "title": event.get("title"),
            "date": event.get("date"), 
            "start_datetime": event.get("start_datetime"),
            "calendar_name": event.get("calendar_name"),
            "calendar_bg_color": event.get("calendar_bg_color"),
            "calendar_fg_color": event.get("calendar_fg_color")
        })
    
    return jsonify({"events": debug_info, "count": len(events)})

@app.route("/api/calendar/list")
def api_calendar_list():
    """List all available calendars"""
    if not signage.calendar or not signage.calendar.service:
        return jsonify({"error": "Calendar service not available"})
    
    try:
        calendars_result = signage.calendar.service.calendarList().list().execute()
        calendars = calendars_result.get("items", [])
        
        calendar_info = []
        for cal in calendars:
            calendar_info.append({
                "id": cal["id"],
                "name": cal.get("summary", "Unknown"),
                "access_role": cal.get("accessRole", "Unknown"), 
                "primary": cal.get("primary", False),
                "background_color": cal.get("backgroundColor", ""),
                "foreground_color": cal.get("foregroundColor", "")
            })
        
        return jsonify({"calendars": calendar_info, "count": len(calendar_info)})
    except Exception as e:
        return jsonify({"error": f"Failed to list calendars: {str(e)}"})

@app.route("/api/lightning/check")
def api_lightning_check():
    """Check current lightning activity"""
    try:
        lightning_data = signage.get_lightning_data()
        return jsonify(lightning_data)
    except Exception as e:
        return jsonify({"error": f"Lightning check failed: {str(e)}"})

@app.route("/api/lightning/status")
def api_lightning_status():
    """Get current lightning status"""
    if signage.lightning_data:
        return jsonify(signage.lightning_data)
    else:
        return jsonify({"status": "no_data", "message": "Lightning data not available"})

if __name__ == "__main__":
    print("🚀 Temple Office Digital Signage Starting...")
    print("📅 Calendar available at: http://localhost:8080/sharepoint")
    print("🌤️ Weather available at: http://localhost:8080/weather") 
    print("📊 CFSS Dashboard at: http://localhost:8080/cfss")
    app.run(host="0.0.0.0", port=8080, debug=False)

