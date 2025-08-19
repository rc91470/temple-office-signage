#!/usr/bin/env python3

"""
Manual Google Calendar Authentication Script
This script handles the OAuth flow to get a fresh token from your published Google Cloud app.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from google_calendar import GoogleCalendarAPI

def main():
    print("🔐 Starting Google Calendar Authentication...")
    print("This will create a fresh token from your published Google Cloud app.")
    print()
    
    # Initialize the Google Calendar API (this will trigger authentication)
    calendar_api = GoogleCalendarAPI()
    
    if calendar_api.service:
        print("✅ Authentication successful!")
        print("🔗 Testing calendar access...")
        
        # Test by getting some events
        events = calendar_api.get_upcoming_events(max_results=3, days_ahead=7)
        
        if events and len(events) > 0:
            print(f"📅 Successfully retrieved {len(events)} upcoming events:")
            for event in events:
                print(f"  • {event.get('summary', 'No title')}")
        else:
            print("📅 No upcoming events found (this is normal if calendar is empty)")
            
        print()
        print("🎉 Google Calendar is now authenticated with your published app!")
        print("💡 The token should now have extended lifetime (no more frequent re-auth)")
        
    else:
        print("❌ Authentication failed")
        return 1
        
    return 0

if __name__ == "__main__":
    exit(main())
