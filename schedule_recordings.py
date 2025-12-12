#!/usr/bin/env python3
"""
Google Calendar to Recording Scheduler
Scrapes Google Calendar events and automatically schedules recordings using threaded API
"""

import argparse
import datetime
import time
import subprocess
import sys
import os
import re
import json
import threading
from pathlib import Path

# Import the recording APIs
try:
    from showrec import record_stream as record_mp3
    from showrec_hls import record_stream as record_hls
    RECORDERS_AVAILABLE = True
except ImportError:
    RECORDERS_AVAILABLE = False
    record_mp3 = None
    record_hls = None

# Import Google Drive uploader
try:
    from gdrive_upload import DriveUploader
    GDRIVE_AVAILABLE = True
except ImportError:
    GDRIVE_AVAILABLE = False
    DriveUploader = None

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    GOOGLE_APIS_AVAILABLE = True
except ImportError:
    GOOGLE_APIS_AVAILABLE = False

class CalendarRecordingScheduler:
    def __init__(self, calendar_id='primary', credentials_file='credentials.json', token_file='token.json', status_file='/tmp/showrec_status.json', output_path='.', upload_folder=None, backup_path=None, drive_credentials='credentials.json', drive_token='drive_token.json'):
        self.calendar_id = calendar_id
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.status_file = status_file
        self.output_path = os.path.abspath(output_path)
        self.service = None
        
        # Google Drive upload settings
        self.upload_folder = upload_folder
        self.backup_path = os.path.abspath(backup_path) if backup_path else None
        self.drive_uploader = None
        
        # Initialize Drive uploader if upload is enabled
        if self.upload_folder:
            if not GDRIVE_AVAILABLE:
                print("⚠️  Warning: Google Drive upload requested but gdrive_upload module not available")
                print("   Recordings will be kept locally")
                self.upload_folder = None
            else:
                try:
                    self.drive_uploader = DriveUploader(
                        credentials_file=drive_credentials,
                        token_file=drive_token
                    )
                    # Authenticate now to catch any issues early
                    self.drive_uploader.authenticate()
                    print(f"✓ Google Drive upload enabled - folder: {self.upload_folder}")
                except Exception as e:
                    print(f"⚠️  Warning: Could not initialize Drive uploader: {e}")
                    print("   Recordings will be kept locally")
                    self.upload_folder = None
                    self.drive_uploader = None
        
        # Ensure output directory exists
        os.makedirs(self.output_path, exist_ok=True)
        
        # Ensure backup directory exists if specified
        if self.backup_path:
            os.makedirs(self.backup_path, exist_ok=True)
            print(f"✓ Backup path configured: {self.backup_path}")
        
        # Track active and queued recordings
        self.active_recordings = {}  # {event_id: {thread, info, start_time}}
        self.queued_recordings = {}  # {event_id: {info, scheduled_time}}
        self.completed_recordings = []  # [{info, result, end_time}]
        
        # Status lock for thread safety
        self.status_lock = threading.Lock()
        
        # Recording-related patterns in location field
        self.stream_patterns = {
            'bassdrive': 'http://ice.bassdrive.net:80/stream',
            'dnbradio': 'http://dnbradio.co.uk:8000/dnbradio_main.mp3',
            'default': 'http://ice.bassdrive.net:80/stream'
        }
        
        if not RECORDERS_AVAILABLE:
            print("⚠️  Warning: Recording modules not available")
            print("   Make sure showrec.py and showrec_hls.py are in the same directory")
        
        if not GOOGLE_APIS_AVAILABLE:
            raise ImportError("Google APIs not available. Install with: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")

    def authenticate(self):
        """Authenticate with Google Calendar API"""
        creds = None
        scopes = ['https://www.googleapis.com/auth/calendar.readonly']
        
        # Check if token.json exists
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, scopes)
        
        # If there are no (valid) credentials available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_file):
                    print(f"Error: {self.credentials_file} not found!")
                    print("Please download your Google Calendar API credentials from:")
                    print("https://console.cloud.google.com/apis/credentials")
                    sys.exit(1)
                
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, scopes)
                creds = flow.run_local_server(port=0)
            
            # Save the credentials for the next run
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())
        
        self.service = build('calendar', 'v3', credentials=creds)
        print("✓ Successfully authenticated with Google Calendar")

    def resolve_calendar_id(self, calendar_name_or_id):
        """Resolve calendar name to ID, or return ID if already valid"""
        if not self.service:
            self.authenticate()
        
        # If it looks like an email or already contains @, assume it's an ID
        if '@' in calendar_name_or_id or calendar_name_or_id == 'primary':
            return calendar_name_or_id
        
        try:
            # Get all calendars and search for matching name
            calendar_list = self.service.calendarList().list().execute()
            calendars = calendar_list.get('items', [])
            
            # First try exact match
            for calendar in calendars:
                summary = calendar.get('summary', '')
                if summary.lower() == calendar_name_or_id.lower():
                    cal_id = calendar['id']
                    print(f"✓ Resolved '{calendar_name_or_id}' to calendar ID: {cal_id}")
                    return cal_id
            
            # Then try partial match
            for calendar in calendars:
                summary = calendar.get('summary', '')
                if calendar_name_or_id.lower() in summary.lower():
                    cal_id = calendar['id']
                    print(f"✓ Resolved '{calendar_name_or_id}' to calendar: {summary} ({cal_id})")
                    return cal_id
            
            # If no match found, show available calendars
            print(f"❌ Calendar '{calendar_name_or_id}' not found!")
            print("Available calendars:")
            for calendar in calendars:
                summary = calendar.get('summary', 'No name')
                primary = ' (PRIMARY)' if calendar.get('primary', False) else ''
                print(f"  - {summary}{primary}")
            
            return None
            
        except Exception as e:
            print(f"❌ Error resolving calendar: {e}")
            return calendar_name_or_id  # Return original if error
        """List all available calendars"""
        if not self.service:
            self.authenticate()
        
        print("📅 Available Calendars:")
        print("=" * 40)
        
        try:
            calendar_list = self.service.calendarList().list().execute()
            calendars = calendar_list.get('items', [])
            
            for calendar in calendars:
                cal_id = calendar['id']
                summary = calendar.get('summary', 'No name')
                primary = ' (PRIMARY)' if calendar.get('primary', False) else ''
                access_role = calendar.get('accessRole', 'unknown')
                
                print(f"📋 {summary}{primary}")
                print(f"   ID: {cal_id}")
                print(f"   Access: {access_role}")
                print()
                
        except Exception as e:
            print(f"❌ Error listing calendars: {e}")

    def get_upcoming_events(self, hours_ahead=24):
        """Get events from the next specified hours"""
        now = datetime.datetime.utcnow()
        time_min = now.isoformat() + 'Z'
        time_max = (now + datetime.timedelta(hours=hours_ahead)).isoformat() + 'Z'
        
        events_result = self.service.events().list(
            calendarId=self.calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        return events

    def parse_event_for_recording(self, event):
        """Parse a calendar event to determine if it should trigger a recording"""
        # Check if event has required fields
        if 'start' not in event or 'summary' not in event:
            return None
        
        start = event['start'].get('dateTime')
        end = event['end'].get('dateTime') if 'end' in event else None
        
        # Skip all-day events
        if not start or not end:
            return None
        
        # Parse times
        start_time = datetime.datetime.fromisoformat(start.replace('Z', '+00:00'))
        end_time = datetime.datetime.fromisoformat(end.replace('Z', '+00:00'))
        
        # Convert to local time
        start_local = start_time.astimezone()
        end_local = end_time.astimezone()
        
        duration_minutes = int((end_local - start_local).total_seconds() / 60)
        
        # Get event details
        title = event.get('summary', 'Untitled Event')
        location = event.get('location', '').lower()
        description = event.get('description', '')
        
        # Determine stream URL from location field
        stream_url = self._get_stream_url(location, description)
        
        # Only process events that have a recognizable stream
        if not stream_url:
            return None
        
        # Create safe filename from event title
        safe_title = self._sanitize_filename(title)
        timestamp = start_local.strftime("%Y%m%d_%H%M")
        
        # Determine file extension based on stream type
        if '.m3u8' in stream_url.lower():
            filename = f"{safe_title}_{timestamp}.m4a"  # HLS streams -> M4A
        else:
            filename = f"{safe_title}_{timestamp}.mp3"  # Regular streams -> MP3
        
        # Construct full path
        full_path = os.path.join(self.output_path, filename)
        
        return {
            'title': title,
            'start_time': start_local,
            'end_time': end_local,
            'duration_minutes': duration_minutes,
            'stream_url': stream_url,
            'filename': full_path,
            'location': event.get('location', ''),
            'description': description
        }

    def _get_stream_url(self, location, description):
        """Extract stream URL from location or description"""
        text = (location + ' ' + description).lower()
        
        # Skip Teams/Zoom/Meet URLs
        skip_patterns = ['teams.microsoft.com', 'zoom.us', 'meet.google.com', 'aka.ms/jointeamsmeeting']
        for pattern in skip_patterns:
            if pattern in text:
                return None
        
        # Look for direct streaming URLs (audio/radio streams)
        streaming_patterns = [
            r'https?://[^\s]*\.m3u8[^\s]*',  # HLS streams (check first)
            r'https?://[^\s]*\.mp3[^\s]*',
            r'https?://[^\s]*stream[^\s]*',
            r'https?://[^\s]*radio[^\s]*',
            r'https?://ice\.[^\s]*',
            r'https?://[^\s]*:8000[^\s]*',
            r'https?://[^\s]*:80[^\s]*'
        ]
        
        for pattern in streaming_patterns:
            urls = re.findall(pattern, location + ' ' + description, re.IGNORECASE)
            if urls:
                return urls[0]
        
        # Look for known stream keywords
        for keyword, url in self.stream_patterns.items():
            if keyword in text:
                return url
        
        return None

    def _sanitize_filename(self, title):
        """Create a safe filename from event title"""
        # Remove/replace problematic characters
        safe = re.sub(r'[<>:"/\\|?*]', '_', title)
        safe = re.sub(r'\s+', '_', safe)
        safe = safe.strip('._')
        return safe[:50]  # Limit length
    
    def _get_event_id(self, event):
        """Get unique ID for an event"""
        return event.get('id', f"{event.get('summary', 'unknown')}_{event['start'].get('dateTime', '')}")
    
    def _update_status(self):
        """Update status JSON file"""
        with self.status_lock:
            status = {
                'last_update': datetime.datetime.now().isoformat(),
                'active_recordings': [
                    {
                        'title': info['title'],
                        'start_time': info['start_time'].isoformat(),
                        'duration_minutes': info['duration_minutes'],
                        'filename': info['filename'],
                        'stream_url': info['stream_url'],
                        'recording_started': start_time.isoformat(),
                        'thread_alive': thread.is_alive()
                    }
                    for event_id, (thread, info, start_time) in self.active_recordings.items()
                ],
                'queued_recordings': [
                    {
                        'title': info['title'],
                        'start_time': info['start_time'].isoformat(),
                        'duration_minutes': info['duration_minutes'],
                        'filename': info['filename'],
                        'stream_url': info['stream_url'],
                        'scheduled_for': scheduled_time.isoformat()
                    }
                    for event_id, (info, scheduled_time) in self.queued_recordings.items()
                ],
                'completed_recordings': self.completed_recordings[-20:]  # Last 20
            }
            
            try:
                with open(self.status_file, 'w') as f:
                    json.dump(status, f, indent=2)
            except Exception as e:
                print(f"Warning: Could not write status file: {e}")
    
    def get_status(self):
        """Get current status"""
        with self.status_lock:
            return {
                'active': len(self.active_recordings),
                'queued': len(self.queued_recordings),
                'completed': len(self.completed_recordings)
            }

    def schedule_recording(self, recording_info, dry_run=False):
        """Schedule a recording based on event info using threaded API"""
        now = datetime.datetime.now().astimezone()
        start_time = recording_info['start_time']
        event_id = recording_info.get('event_id', f"{recording_info['title']}_{start_time.isoformat()}")
        
        # Check if already queued or active
        with self.status_lock:
            if event_id in self.queued_recordings:
                print(f"⏭️  Skipping '{recording_info['title']}' - already queued")
                return False
            if event_id in self.active_recordings:
                print(f"⏭️  Skipping '{recording_info['title']}' - already recording")
                return False
        
        if start_time <= now:
            print(f"⚠️  Event '{recording_info['title']}' has already started or passed")
            return False
        
        # Determine which recorder to use based on stream URL
        stream_url = recording_info['stream_url']
        if '.m3u8' in stream_url.lower():
            recorder = record_hls
            stream_type = '📡 HLS (m3u8)'
            extension = '.m4a'
        else:
            recorder = record_mp3
            stream_type = '📻 HTTP Stream'
            extension = '.mp3'
        
        # Ensure filename has correct extension
        if not recording_info['filename'].lower().endswith(extension):
            recording_info['filename'] = os.path.splitext(recording_info['filename'])[0] + extension
        
        print(f"📅 Event: {recording_info['title']}")
        print(f"⏰ Start: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"⏱️  Duration: {recording_info['duration_minutes']} minutes")
        print(f"{stream_type}: {stream_url}")
        print(f"📁 File: {recording_info['filename']}")
        
        if dry_run:
            print("🔍 DRY RUN - Not scheduled")
            return True
        
        # Add to queued recordings
        with self.status_lock:
            self.queued_recordings[event_id] = (recording_info, now)
        
        # Start scheduler thread for this recording
        scheduler_thread = threading.Thread(
            target=self._wait_and_record,
            args=(event_id, recording_info, recorder),
            daemon=False
        )
        scheduler_thread.start()
        
        print(f"✅ Recording queued! Will start at {start_time.strftime('%H:%M:%S')}")
        self._update_status()
        return True
    
    def _wait_and_record(self, event_id, recording_info, recorder):
        """Wait until start time, then start recording"""
        start_time = recording_info['start_time']
        now = datetime.datetime.now().astimezone()
        
        # Wait until start time
        wait_seconds = (start_time - now).total_seconds()
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        
        # Move from queued to active
        with self.status_lock:
            if event_id in self.queued_recordings:
                del self.queued_recordings[event_id]
        
        print(f"\n🎬 Starting recording: {recording_info['title']}")
        recording_start = datetime.datetime.now()
        
        # Start recording thread
        recording_thread = threading.Thread(
            target=self._execute_recording,
            args=(event_id, recording_info, recorder, recording_start),
            daemon=False
        )
        
        with self.status_lock:
            self.active_recordings[event_id] = (recording_thread, recording_info, recording_start)
        
        recording_thread.start()
        self._update_status()
        recording_thread.join()  # Wait for completion
    
    def _execute_recording(self, event_id, recording_info, recorder, start_time):
        """Execute the actual recording"""
        try:
            result = recorder(
                url=recording_info['stream_url'],
                output_file=recording_info['filename'],
                duration_seconds=recording_info['duration_minutes'] * 60,
                quiet=True
            )
            
            # Handle upload and cleanup if recording succeeded
            uploaded = False
            backed_up = False
            deleted = False
            upload_error = None
            
            if result['success'] and self.upload_folder and self.drive_uploader:
                print(f"📤 Uploading {recording_info['title']} to Drive...")
                upload_result = self.drive_uploader.upload_file(
                    file_path=recording_info['filename'],
                    folder_name=self.upload_folder,
                    quiet=True
                )
                
                if upload_result['success']:
                    uploaded = True
                    print(f"✅ Uploaded to Drive: {upload_result['web_link']}")
                    
                    # Delete local file after successful upload
                    try:
                        os.remove(recording_info['filename'])
                        deleted = True
                        print(f"🗑️  Deleted local file: {os.path.basename(recording_info['filename'])}")
                    except Exception as e:
                        print(f"⚠️  Could not delete local file: {e}")
                else:
                    upload_error = upload_result['error']
                    print(f"❌ Upload failed: {upload_error}")
                    
                    # Move to backup folder if upload failed
                    if self.backup_path:
                        try:
                            backup_file = os.path.join(
                                self.backup_path,
                                os.path.basename(recording_info['filename'])
                            )
                            os.rename(recording_info['filename'], backup_file)
                            backed_up = True
                            print(f"💾 Moved to backup: {backup_file}")
                        except Exception as e:
                            print(f"⚠️  Could not move to backup: {e}")
            
            # Move to completed
            with self.status_lock:
                if event_id in self.active_recordings:
                    del self.active_recordings[event_id]
                
                completion = {
                    'title': recording_info['title'],
                    'filename': recording_info['filename'],
                    'start_time': start_time.isoformat(),
                    'end_time': datetime.datetime.now().isoformat(),
                    'success': result['success'],
                    'size_mb': result.get('size_mb', 0),
                    'duration': result.get('duration', 0),
                    'error': result.get('error'),
                    'uploaded': uploaded,
                    'backed_up': backed_up,
                    'deleted': deleted,
                    'upload_error': upload_error
                }
                self.completed_recordings.append(completion)
            
            if result['success']:
                status_parts = [f"✅ Completed: {recording_info['title']} ({result['size_mb']:.1f} MB)"]
                if uploaded:
                    status_parts.append("📤 Uploaded")
                if deleted:
                    status_parts.append("🗑️ Deleted")
                if backed_up:
                    status_parts.append("💾 Backed up")
                print(" | ".join(status_parts))
            else:
                print(f"❌ Failed: {recording_info['title']} - {result['error']}")
            
        except Exception as e:
            print(f"❌ Exception recording {recording_info['title']}: {e}")
            with self.status_lock:
                if event_id in self.active_recordings:
                    del self.active_recordings[event_id]
                self.completed_recordings.append({
                    'title': recording_info['title'],
                    'filename': recording_info['filename'],
                    'start_time': start_time.isoformat(),
                    'end_time': datetime.datetime.now().isoformat(),
                    'success': False,
                    'error': str(e),
                    'uploaded': False,
                    'backed_up': False,
                    'deleted': False
                })
        
        finally:
            self._update_status()

    def run_scheduler(self, hours_ahead=24, dry_run=False, continuous=False):
        """Main scheduler loop - checks calendar every hour"""
        print("🎙️  Google Calendar Recording Scheduler (Threaded)")
        print("=" * 50)
        print(f"📊 Status file: {self.status_file}")
        print("=" * 50)
        
        if not self.service:
            self.authenticate()
        
        # Resolve calendar name to ID
        resolved_calendar_id = self.resolve_calendar_id(self.calendar_id)
        if not resolved_calendar_id:
            print("❌ Cannot proceed without valid calendar")
            return
        
        # Update calendar_id with resolved value
        self.calendar_id = resolved_calendar_id
        
        check_count = 0
        while True:
            try:
                check_count += 1
                print(f"\n🔍 Calendar check #{check_count} at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
                events = self.get_upcoming_events(hours_ahead)
                recording_events = []
                
                for event in events:
                    recording_info = self.parse_event_for_recording(event)
                    if recording_info:
                        # Add event ID for duplicate detection
                        recording_info['event_id'] = self._get_event_id(event)
                        recording_events.append(recording_info)
                
                # Show current status
                status = self.get_status()
                print(f"📊 Status: {status['active']} active, {status['queued']} queued, {status['completed']} completed")
                
                if not recording_events:
                    print(f"📭 No new recording events found in the next {hours_ahead} hours")
                else:
                    print(f"🎵 Found {len(recording_events)} event(s) in calendar:")
                    print()
                    
                    scheduled_count = 0
                    for recording_info in recording_events:
                        success = self.schedule_recording(recording_info, dry_run)
                        if success:
                            scheduled_count += 1
                        print("-" * 40)
                    
                    if scheduled_count > 0:
                        print(f"✅ Scheduled {scheduled_count} new recording(s)")
                
                # Update status file
                self._update_status()
                
                if not continuous:
                    break
                
                # Wait 1 hour before checking again
                next_check = datetime.datetime.now() + datetime.timedelta(hours=1)
                print(f"\n⏰ Next calendar check at {next_check.strftime('%H:%M:%S')}")
                print(f"� Sleeping for 1 hour...")
                print("   (Press Ctrl+C to stop scheduler)")
                time.sleep(3600)
                
            except KeyboardInterrupt:
                print("\n\n👋 Scheduler stopped by user")
                print(f"📊 Final status: {self.get_status()}")
                self._update_status()
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                import traceback
                traceback.print_exc()
                if not continuous:
                    break
                print("🔄 Retrying in 5 minutes...")
                time.sleep(300)

def main():
    parser = argparse.ArgumentParser(
        description="Schedule recordings from Google Calendar events (Threaded API)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Setup Instructions:
1. Enable Google Calendar API in Google Cloud Console
2. Download credentials.json file
3. Place credentials.json in same directory as this script

Event Requirements:
- Event must have start and end time (not all-day)
- Location field must contain stream URL or keyword (bassdrive, dnbradio)
- Event title will be used for filename

Stream Types:
- HLS (m3u8) streams: Automatically uses HLS recorder -> outputs .m4a
- HTTP streams (mp3): Uses MP3 recorder -> outputs .mp3

Status Monitoring:
- Status written to: /tmp/showrec_status.json
- View with: cat /tmp/showrec_status.json | jq
- Or use: ./show_status.py (companion utility)

Continuous Mode:
- Checks calendar every hour
- Only schedules new recordings (skips duplicates)
- Updates status file after each check
- Runs until Ctrl+C

Google Drive Upload (Optional):
- Use --upload to auto-upload completed recordings to Drive
- Successful uploads auto-delete the local file
- Use --backup to move failed uploads to a backup folder
- Requires Google Drive API enabled (see GDRIVE_SETUP.md)

Examples:
  %(prog)s --list-calendars                        # List all available calendars
  %(prog)s --dry-run                               # See what would be scheduled
  %(prog)s --calendar BDRecord --dry-run           # Use BDRecord calendar
  %(prog)s --hours 48                              # Check next 48 hours
  %(prog)s --continuous                            # Run as service (hourly checks)
  %(prog)s --calendar "your-calendar@gmail.com"    # Use specific calendar by email
  %(prog)s --upload "Radio Archive"                # Auto-upload to Drive folder
  %(prog)s --upload "Archive" --backup ./failed    # Upload with backup on failure
  %(prog)s --continuous --upload "Shows"           # Service with auto-upload
        """
    )
    
    parser.add_argument(
        '--list-calendars',
        action='store_true',
        help='List all available calendars and their IDs'
    )
    
    parser.add_argument(
        '--calendar',
        default='primary',
        help='Calendar name or ID to monitor (default: primary). Examples: "BDRecord", "primary", "user@gmail.com"'
    )
    
    parser.add_argument(
        '--hours',
        type=int,
        default=24,
        help='Hours ahead to check for events (default: 24)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be scheduled without actually starting recordings'
    )
    
    parser.add_argument(
        '--continuous',
        action='store_true',
        help='Run continuously, checking every hour'
    )
    
    parser.add_argument(
        '--credentials',
        default='credentials.json',
        help='Path to Google Calendar API credentials file'
    )
    
    parser.add_argument(
        '--token',
        default='token.json',
        help='Path to store authentication token'
    )
    
    parser.add_argument(
        '--path',
        default='.',
        help='Directory to save recordings (default: current directory)'
    )
    
    parser.add_argument(
        '--upload',
        dest='upload_folder',
        help='Google Drive folder name to upload completed recordings (auto-deletes local file on success)'
    )
    
    parser.add_argument(
        '--backup',
        dest='backup_path',
        help='Local backup directory for recordings if upload fails (no auto-delete)'
    )
    
    parser.add_argument(
        '--drive-credentials',
        default='credentials.json',
        help='Path to Google Drive API credentials file (default: credentials.json)'
    )
    
    parser.add_argument(
        '--drive-token',
        default='drive_token.json',
        help='Path to Google Drive token file (default: drive_token.json)'
    )
    
    args = parser.parse_args()
    
    try:
        scheduler = CalendarRecordingScheduler(
            calendar_id=args.calendar,
            credentials_file=args.credentials,
            token_file=args.token,
            output_path=args.path,
            upload_folder=args.upload_folder,
            backup_path=args.backup_path,
            drive_credentials=args.drive_credentials,
            drive_token=args.drive_token
        )
        
        # If user wants to list calendars, do that and exit
        if args.list_calendars:
            scheduler.list_calendars()
            return
        
        scheduler.run_scheduler(
            hours_ahead=args.hours,
            dry_run=args.dry_run,
            continuous=args.continuous
        )
        
    except ImportError as e:
        print("❌ Missing dependencies!")
        print("Install with: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()