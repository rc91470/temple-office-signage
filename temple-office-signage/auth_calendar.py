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
    token_file = 'token.json'
    credentials_file = 'credentials.json'
    
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            # Use localhost redirect for proper OAuth flow
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
