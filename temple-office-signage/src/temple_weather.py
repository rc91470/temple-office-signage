#!/usr/bin/env python3

# Temple, TX Weather Integration
# Uses OpenWeatherMap API (free tier: 1000 calls/day)

import requests
import json
from datetime import datetime

class TempleWeather:
    def __init__(self, api_key):
        self.api_key = api_key
        self.city = "Temple"
        self.state = "TX"
        self.country = "US"
        self.lat = 31.0982  # Temple, TX coordinates
        self.lon = -97.3428
        
    def get_current_weather(self):
        """Get current weather for Temple, TX"""
        url = f"http://api.openweathermap.org/data/2.5/weather"
        params = {
            'lat': self.lat,
            'lon': self.lon,
            'appid': self.api_key,
            'units': 'imperial'  # Fahrenheit
        }
        
        try:
            response = requests.get(url, params=params)
            data = response.json()
            
            return {
                'temperature': round(data['main']['temp']),
                'feels_like': round(data['main']['feels_like']),
                'humidity': data['main']['humidity'],
                'description': data['weather'][0]['description'].title(),
                'icon': data['weather'][0]['icon'],
                'wind_speed': round(data['wind']['speed']),
                'pressure': data['main']['pressure'],
                'visibility': data.get('visibility', 0) // 1609,  # Convert to miles
                'uv_index': self.get_uv_index()
            }
        except Exception as e:
            print(f"Weather API error: {e}")
            return self.get_fallback_weather()
    
    def get_forecast(self, days=5):
        """Get 5-day forecast for Temple, TX"""
        url = f"http://api.openweathermap.org/data/2.5/forecast"
        params = {
            'lat': self.lat,
            'lon': self.lon,
            'appid': self.api_key,
            'units': 'imperial',
            'cnt': days * 8  # 8 forecasts per day (3-hour intervals)
        }
        
        try:
            response = requests.get(url, params=params)
            data = response.json()
            
            # Group by day
            daily_forecast = []
            current_day = None
            day_data = {'temps': [], 'descriptions': [], 'icons': []}
            
            for item in data['list']:
                date = datetime.fromtimestamp(item['dt']).date()
                
                if current_day != date:
                    if current_day is not None:
                        # Process previous day
                        daily_forecast.append({
                            'date': current_day.strftime('%a'),
                            'high': max(day_data['temps']),
                            'low': min(day_data['temps']),
                            'description': max(set(day_data['descriptions']), key=day_data['descriptions'].count),
                            'icon': max(set(day_data['icons']), key=day_data['icons'].count)
                        })
                    
                    current_day = date
                    day_data = {'temps': [], 'descriptions': [], 'icons': []}
                
                day_data['temps'].append(round(item['main']['temp']))
                day_data['descriptions'].append(item['weather'][0]['description'].title())
                day_data['icons'].append(item['weather'][0]['icon'])
            
            return daily_forecast[:days]
            
        except Exception as e:
            print(f"Forecast API error: {e}")
            return self.get_fallback_forecast()
    
    def get_uv_index(self):
        """Get UV index for Temple, TX"""
        url = f"http://api.openweathermap.org/data/2.5/uvi"
        params = {
            'lat': self.lat,
            'lon': self.lon,
            'appid': self.api_key
        }
        
        try:
            response = requests.get(url, params=params)
            data = response.json()
            return round(data['value'])
        except:
            return 5  # Default moderate UV
    
    def get_weather_alerts(self):
        """Get weather alerts for Bell County, TX"""
        url = f"http://api.openweathermap.org/data/2.5/onecall"
        params = {
            'lat': self.lat,
            'lon': self.lon,
            'appid': self.api_key,
            'exclude': 'minutely,hourly,daily'
        }
        
        try:
            response = requests.get(url, params=params)
            data = response.json()
            
            alerts = []
            if 'alerts' in data:
                for alert in data['alerts']:
                    alerts.append({
                        'title': alert['event'],
                        'description': alert['description'][:200] + '...',
                        'start': datetime.fromtimestamp(alert['start']),
                        'end': datetime.fromtimestamp(alert['end'])
                    })
            
            return alerts
        except:
            return []
    
    def get_fallback_weather(self):
        """Fallback weather data when API fails"""
        return {
            'temperature': 75,
            'feels_like': 78,
            'humidity': 60,
            'description': 'Partly Cloudy',
            'icon': '02d',
            'wind_speed': 8,
            'pressure': 1013,
            'visibility': 10,
            'uv_index': 6
        }
    
    def get_fallback_forecast(self):
        """Fallback forecast when API fails"""
        return [
            {'date': 'Tomorrow', 'high': 78, 'low': 65, 'description': 'Sunny', 'icon': '01d'},
            {'date': 'Wednesday', 'high': 82, 'low': 68, 'description': 'Partly Cloudy', 'icon': '02d'},
            {'date': 'Thursday', 'high': 75, 'low': 62, 'description': 'Rain', 'icon': '09d'},
            {'date': 'Friday', 'high': 79, 'low': 66, 'description': 'Cloudy', 'icon': '03d'}
        ]

# Weather icon mapping for display - using more compatible text symbols
WEATHER_ICONS = {
    '01d': 'SUNNY',      # Clear sky day
    '01n': 'CLEAR',      # Clear sky night
    '02d': 'PARTLY CLOUDY',  # Few clouds day
    '02n': 'PARTLY CLOUDY',  # Few clouds night
    '03d': 'CLOUDY',     # Scattered clouds
    '03n': 'CLOUDY',     # Scattered clouds
    '04d': 'OVERCAST',   # Broken clouds
    '04n': 'OVERCAST',   # Broken clouds
    '09d': 'SHOWERS',    # Shower rain
    '09n': 'SHOWERS',    # Shower rain
    '10d': 'RAIN',       # Rain day
    '10n': 'RAIN',       # Rain night
    '11d': 'STORMS',     # Thunderstorm
    '11n': 'STORMS',     # Thunderstorm
    '13d': 'SNOW',       # Snow
    '13n': 'SNOW',       # Snow
    '50d': 'FOG',        # Mist/fog
    '50n': 'FOG'         # Mist/fog
}

def get_weather_emoji(icon_code):
    """Convert weather icon code to text description"""
    return WEATHER_ICONS.get(icon_code, 'PARTLY CLOUDY')

# Example usage:
if __name__ == "__main__":
    # Get your free API key from: https://openweathermap.org/api
    API_KEY = "YOUR_API_KEY_HERE"
    
    weather = TempleWeather(API_KEY)
    current = weather.get_current_weather()
    forecast = weather.get_forecast(4)
    alerts = weather.get_weather_alerts()
    
    print(f"Temple, TX Weather:")
    print(f"Current: {current['temperature']}°F, {current['description']}")
    print(f"Forecast: {forecast[0]['high']}°/{forecast[0]['low']}° - {forecast[0]['description']}")
    
    if alerts:
        print(f"Alerts: {len(alerts)} active")
    
    print("\nTo use in your dashboard:")
    print("1. Get free API key from openweathermap.org")
    print("2. Replace 'YOUR_API_KEY_HERE' with your key")
    print("3. Import this module in your dashboard code")
