#!/usr/bin/env python3
"""
Status viewer for showrec scheduler
Displays current recording status in a human-friendly format
"""

import json
import sys
import datetime
from pathlib import Path

STATUS_FILE = '/tmp/showrec_status.json'

def format_time(iso_str):
    """Format ISO timestamp to readable format"""
    try:
        dt = datetime.datetime.fromisoformat(iso_str)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return iso_str

def format_duration(seconds):
    """Format duration in seconds to readable format"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"

def show_status():
    """Display recording status"""
    if not Path(STATUS_FILE).exists():
        print("❌ Status file not found")
        print(f"   Expected: {STATUS_FILE}")
        print("   Is the scheduler running?")
        return 1
    
    try:
        with open(STATUS_FILE, 'r') as f:
            status = json.load(f)
    except Exception as e:
        print(f"❌ Error reading status file: {e}")
        return 1
    
    # Header
    print("🎙️  Showrec Scheduler Status")
    print("=" * 70)
    print(f"Last Update: {format_time(status['last_update'])}")
    print()
    
    # Active Recordings
    active = status.get('active_recordings', [])
    print(f"🔴 Active Recordings: {len(active)}")
    print("-" * 70)
    if active:
        for rec in active:
            print(f"  📻 {rec['title']}")
            print(f"     Started: {format_time(rec['recording_started'])}")
            print(f"     Duration: {rec['duration_minutes']} minutes")
            print(f"     File: {rec['filename']}")
            print(f"     Thread: {'✓ Running' if rec['thread_alive'] else '✗ Stopped'}")
            print()
    else:
        print("  (none)")
        print()
    
    # Queued Recordings
    queued = status.get('queued_recordings', [])
    print(f"⏳ Queued Recordings: {len(queued)}")
    print("-" * 70)
    if queued:
        for rec in queued:
            print(f"  📅 {rec['title']}")
            print(f"     Starts: {format_time(rec['start_time'])}")
            print(f"     Duration: {rec['duration_minutes']} minutes")
            print(f"     File: {rec['filename']}")
            
            # Calculate time until start
            try:
                start_dt = datetime.datetime.fromisoformat(rec['start_time'])
                now = datetime.datetime.now(start_dt.tzinfo)
                wait_seconds = (start_dt - now).total_seconds()
                if wait_seconds > 0:
                    print(f"     Starts in: {format_duration(wait_seconds)}")
                else:
                    print(f"     Status: Starting now...")
            except:
                pass
            print()
    else:
        print("  (none)")
        print()
    
    # Completed Recordings (last 10)
    completed = status.get('completed_recordings', [])
    print(f"✅ Completed Recordings: {len(completed)} (showing last 10)")
    print("-" * 70)
    if completed:
        for rec in completed[-10:]:
            status_icon = "✅" if rec.get('success') else "❌"
            print(f"  {status_icon} {rec['title']}")
            print(f"     Start: {format_time(rec['start_time'])}")
            print(f"     End: {format_time(rec['end_time'])}")
            if rec.get('success'):
                print(f"     Size: {rec.get('size_mb', 0):.1f} MB")
                print(f"     Duration: {format_duration(rec.get('duration', 0))}")
                
                # Show upload/backup status
                if rec.get('uploaded'):
                    print(f"     📤 Uploaded to Drive")
                if rec.get('deleted'):
                    print(f"     🗑️  Local file deleted")
                elif rec.get('backed_up'):
                    print(f"     💾 Moved to backup (upload failed)")
                else:
                    print(f"     File: {rec['filename']}")
                
                if rec.get('upload_error'):
                    print(f"     Upload error: {rec['upload_error']}")
            else:
                print(f"     Error: {rec.get('error', 'Unknown error')}")
            print()
    else:
        print("  (none)")
        print()
    
    # Summary
    print("=" * 70)
    print(f"Total: {len(active)} active, {len(queued)} queued, {len(completed)} completed")
    
    return 0

def watch_status(interval=5):
    """Watch status with auto-refresh"""
    import time
    import os
    
    try:
        while True:
            # Clear screen
            os.system('clear' if os.name == 'posix' else 'cls')
            show_status()
            print(f"\n🔄 Refreshing every {interval} seconds... (Ctrl+C to stop)")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n\n👋 Stopped watching")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="View showrec scheduler status",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s              # Show current status
  %(prog)s --watch      # Watch status (refresh every 5 seconds)
  %(prog)s --watch 10   # Watch with 10 second refresh
  %(prog)s --json       # Output raw JSON
        """
    )
    
    parser.add_argument(
        '--watch',
        nargs='?',
        const=5,
        type=int,
        metavar='SECONDS',
        help='Watch mode - refresh every N seconds (default: 5)'
    )
    
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output raw JSON'
    )
    
    args = parser.parse_args()
    
    if args.json:
        # Just cat the JSON file
        if Path(STATUS_FILE).exists():
            with open(STATUS_FILE, 'r') as f:
                print(f.read())
            return 0
        else:
            print(f"Error: {STATUS_FILE} not found", file=sys.stderr)
            return 1
    
    if args.watch is not None:
        watch_status(args.watch)
    else:
        return show_status()

if __name__ == '__main__':
    sys.exit(main())
