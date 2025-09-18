#!/usr/bin/env python3

import os
import json
from datetime import datetime, timedelta
import pytz
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

class GoogleCalendarAPI:
    def __init__(self, credentials_file='credentials.json', token_file='token.json'):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.service = None
        self.timezone = pytz.timezone('America/Chicago')  # CST timezone
        
        # Automatically authenticate during initialization
        if self.authenticate():
            print("Google Calendar authenticated successfully")
        else:
            print("Google Calendar authentication failed")
        
    def authenticate(self):
        """Authenticate with Google Calendar API"""
        creds = None
        
        # The file token.json stores the user's access and refresh tokens.
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
            
        # If there are no (valid) credentials available, try service account first,
        # then fall back to user OAuth flow.
        if not creds or not creds.valid:
            # Service account fallback: set SERVICE_ACCOUNT_FILE to the JSON key path
            service_account_file = os.getenv('SERVICE_ACCOUNT_FILE')
            if service_account_file and os.path.exists(service_account_file):
                try:
                    print(f"Using service account key: {service_account_file}")
                    creds = service_account.Credentials.from_service_account_file(
                        service_account_file, scopes=SCOPES)
                    # No refresh token file for service accounts
                    self.service = build('calendar', 'v3', credentials=creds)
                    return True
                except Exception as e:
                    print(f"Service account authentication failed: {e}")
                    # fall through to user OAuth
            
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    print("Attempting to refresh expired token...")
                    creds.refresh(Request())
                    print("Token refreshed successfully")
                    # Save the refreshed credentials
                    with open(self.token_file, 'w') as token:
                        token.write(creds.to_json())
                except Exception as e:
                    print(f"Error refreshing credentials: {e}")
                    print("Refresh token may be expired - need to re-authenticate")
                    # Delete the invalid token file so we get a fresh auth next time
                    try:
                        os.remove(self.token_file)
                        print(f"Removed invalid token file: {self.token_file}")
                    except:
                        pass
                    return False
            else:
                print("No valid credentials available - starting fresh authentication")
                if not os.path.exists(self.credentials_file):
                    print(f"Credentials file {self.credentials_file} not found!")
                    print("Please download credentials.json from Google Cloud Console")
                    return False
                    
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, SCOPES)
                creds = flow.run_local_server(port=0)
                
                # Save the credentials for the next run
                with open(self.token_file, 'w') as token:
                    token.write(creds.to_json())
        else:
            print("Using valid existing credentials")
                
        try:
            self.service = build('calendar', 'v3', credentials=creds)
            return True
        except HttpError as error:
            print(f'An error occurred: {error}')
            return False
    
    def get_upcoming_events(self, max_results=10, days_ahead=90):
        """Get upcoming events from Google Calendar with extended search range"""
        print(f"Getting upcoming events (max: {max_results}, days: {days_ahead})")
        
        # Verify service is available
        if not self.service:
            print("Google Calendar service not initialized")
            return [
                {
                    'title': 'Calendar Service Error',
                    'time': 'Error',
                    'duration': 'Service not initialized',
                    'description': 'Google Calendar service not available',
                    'location': 'System Error',
                    'is_today': False
                }
            ]
        
        try:
            # Calculate time range - extend to 30 days ahead
            now = datetime.now(self.timezone)
            end_time = now + timedelta(days=days_ahead)
            
            print(f"Searching from {now.isoformat()} to {end_time.isoformat()}")
            
            # List available calendars for debugging
            calendars_result = self.service.calendarList().list().execute()
            calendars = calendars_result.get('items', [])
            print(f"Available calendars ({len(calendars)}):")
            for cal in calendars:
                cal_id = cal['id']
                cal_name = cal.get('summary', 'Unknown')
                print(f"  - {cal_name} ({cal_id})")
            
            # Get events from ALL available calendars (including shared ones)
            print(f"Querying all calendars from {now} to {end_time}")
            
            all_events = []
            seen_ids = set()
            
            # Query each calendar separately
            for cal in calendars:
                cal_id = cal['id']
                cal_name = cal.get('summary', 'Unknown')
                cal_bg_color = cal.get('backgroundColor', '#4285f4')
                cal_fg_color = cal.get('foregroundColor', '#ffffff')
                
                try:
                    print(f"Querying calendar: {cal_name} ({cal_id}) - Color: {cal_bg_color}")
                    events_result = self.service.events().list(
                        calendarId=cal_id,
                        timeMin=now.isoformat(),
                        timeMax=end_time.isoformat(),
                        maxResults=max_results,
                        singleEvents=True,
                        orderBy='startTime'
                    ).execute()
                    
                    calendar_events = events_result.get('items', [])
                    print(f"  Found {len(calendar_events)} events in {cal_name}")
                    
                    # Add events with calendar source info and remove duplicates
                    for event in calendar_events:
                        event_id = event.get('id')
                        if event_id not in seen_ids:
                            seen_ids.add(event_id)
                            # Add calendar source information to event
                            event['calendar_name'] = cal_name
                            event['calendar_id'] = cal_id
                            event['calendar_bg_color'] = cal_bg_color
                            event['calendar_fg_color'] = cal_fg_color
                            all_events.append(event)
                            
                except Exception as e:
                    print(f"  Error querying calendar {cal_name}: {e}")
                    continue
            
            events = all_events
            print(f"Total unique events from all calendars: {len(events)}")
            
            if not events:
                print("No events found in any calendars - creating empty calendar display")
                print("To see events, add them to your Google Calendar or ensure shared calendars have events!")
                return [
                    {
                        'title': 'No Events Scheduled',
                        'time': 'Add events to your Google Calendar',
                        'duration': 'Calendar is empty',
                        'description': 'No events found in any available calendars',
                        'location': 'richard.coleman@iescomm.com',
                        'is_today': False
                    }
                ]
            
            formatted_events = []
            for event in events:
                formatted_event = self._format_event(event)
                if formatted_event:
                    formatted_events.append(formatted_event)
                    print(f"Found event: {formatted_event['title']} on {formatted_event['date']}")
            
            return formatted_events
            
        except Exception as error:
            print(f"Error fetching calendar events: {error}")
            return [
                {
                    'title': 'Calendar Error',
                    'time': 'Error',
                    'duration': 'Troubleshoot',
                    'description': f'Error: {str(error)}',
                    'location': 'System Error',
                    'time': 'Check logs',
                    'date': 'Error',
                    'duration': 'Troubleshoot',
                    'is_today': False
                }
            ]
    
    def _format_event(self, event):
        """Format a Google Calendar event for display"""
        try:
            # Get event start time
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))
            
            # Parse datetime
            if 'T' in start:  # DateTime event
                start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
                
                # Convert to local timezone
                start_local = start_dt.astimezone(self.timezone)
                end_local = end_dt.astimezone(self.timezone)
                
                # Format time and date
                time_str = start_local.strftime('%I:%M %p')
                duration_hours = (end_local - start_local).total_seconds() / 3600
                duration_str = f"{duration_hours:.1f}h" if duration_hours != int(duration_hours) else f"{int(duration_hours)}h"
                
                if start_local.date() == datetime.now(self.timezone).date():
                    date_str = 'Today'
                    is_today = True
                elif start_local.date() == (datetime.now(self.timezone) + timedelta(days=1)).date():
                    date_str = 'Tomorrow'
                    is_today = False
                else:
                    date_str = start_local.strftime('%a, %b %d')
                    is_today = False
                    
                duration = end_local - start_local
                duration_str = f"{int(duration.total_seconds() / 3600)}h {int((duration.total_seconds() % 3600) / 60)}m"
                
            else:  # All-day event
                start_dt = datetime.fromisoformat(start)
                time_str = 'All Day'
                date_str = start_dt.strftime('%a, %b %d')
                duration_str = 'All Day'
            
            return {
                'title': event.get('summary', 'No Title'),
                'description': event.get('description', ''),
                'location': event.get('location', ''),
                'time': time_str,
                'date': date_str,
                'duration': duration_str,
                'start_datetime': start,
                'end_datetime': end,  # ADD THIS - we were missing the end datetime!
                'date_obj': start_local.date() if 'T' in start else datetime.fromisoformat(start).date(),
                'is_today': date_str == 'Today',
                'is_all_day': 'T' not in start,
                'calendar_name': event.get('calendar_name', 'Unknown Calendar'),
                'calendar_id': event.get('calendar_id', ''),
                'calendar_bg_color': event.get('calendar_bg_color', '#4285f4'),
                'calendar_fg_color': event.get('calendar_fg_color', '#ffffff')
            }
            
        except Exception as e:
            print(f"Error formatting event: {e}")
            return None
    
    def _get_fallback_events(self):
        """Return fallback events when API is unavailable"""
        return [
            {
                'title': 'CFSS Team Meeting',
                'description': 'Weekly project status and updates',
                'location': 'Conference Room A',
                'time': '2:00 PM',
                'date': 'Today',
                'duration': '1h 0m',
                'is_today': True
            },
            {
                'title': 'System Maintenance',
                'description': 'Network updates and server maintenance',
                'location': 'Server Room',
                'time': '6:00 PM',
                'date': 'Today',
                'duration': '2h 0m',
                'is_today': True
            },
            {
                'title': 'All Hands Meeting',
                'description': 'Quarterly review and planning session',
                'location': 'Main Conference Room',
                'time': '10:00 AM',
                'date': 'Tomorrow',
                'duration': '1h 30m',
                'is_today': False
            },
            {
                'title': 'Training Session',
                'description': 'New security protocols and procedures',
                'location': 'Training Room B',
                'time': '3:30 PM',
                'date': 'Fri, Aug 8',
                'duration': '2h 0m',
                'is_today': False
            }
        ]

def main():
    """Test the Google Calendar API"""
    calendar = GoogleCalendarAPI()
    events = calendar.get_upcoming_events()
    
    print("Upcoming Events:")
    for event in events:
        print(f"- {event['title']} ({event['date']} at {event['time']})")
        if event['location']:
            print(f"  Location: {event['location']}")
        if event['description']:
            print(f"  Description: {event['description'][:100]}...")
        print()

if __name__ == '__main__':
    main()
