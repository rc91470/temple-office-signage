#!/usr/bin/env python3
"""
Simple Google Calendar authentication script
"""
import os
import sys
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

def authenticate():
    """Authenticate Google Calendar API"""
    creds = None
    token_file = os.getenv('TOKEN_FILE', '/home/pi/RCcode/temple-office-signage/token.json')
    credentials_file = os.getenv('CREDENTIALS_FILE', '/home/pi/RCcode/temple-office-signage/credentials.json')
    
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            # Support headless console auth when RUN_HEADLESS=1 is set
            headless = os.getenv('RUN_HEADLESS', '0').lower() in ('1', 'true', 'yes')
            if headless:
                auth_url, _ = flow.authorization_url(prompt='consent')
                print('\nPlease visit this URL on another device and paste the authorization code here:\n')
                print(auth_url + '\n')
                code = input('Enter authorization code: ').strip()
                flow.fetch_token(code=code)
                creds = flow.credentials
            else:
                # Default: open local server and complete OAuth via browser
                creds = flow.run_local_server(port=0)
        
        with open(token_file, 'w') as token:
            token.write(creds.to_json())
    
    # Test the authentication
    service = build('calendar', 'v3', credentials=creds)
    print("✅ Authentication successful!")
    
    # Test getting calendar list
    calendars = service.calendarList().list().execute()
    print(f"✅ Found {len(calendars.get('items', []))} calendars")
    
    return True

if __name__ == '__main__':
    try:
        authenticate()
        print("🎉 Google Calendar authentication completed successfully!")
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        sys.exit(1)
