#!/usr/bin/env python3
"""
Radio Stream Recorder for Bassdrive
Records MP3 stream with configurable start time and duration
"""

import argparse
import datetime
import time
import requests
import sys
import os
import random
from pathlib import Path

def wait_until_start_time(start_time_str):
    """Wait until the specified start time"""
    try:
        start_time = datetime.datetime.strptime(start_time_str, "%H:%M").time()
        now = datetime.datetime.now()
        start_datetime = datetime.datetime.combine(now.date(), start_time)
        
        # If start time is earlier than now, assume it's for tomorrow
        if start_datetime <= now:
            start_datetime += datetime.timedelta(days=1)
        
        wait_seconds = (start_datetime - now).total_seconds()
        
        if wait_seconds > 0:
            print(f"Waiting until {start_datetime.strftime('%Y-%m-%d %H:%M:%S')} to start recording...")
            print(f"Time to wait: {int(wait_seconds // 3600)}h {int((wait_seconds % 3600) // 60)}m {int(wait_seconds % 60)}s")
            time.sleep(wait_seconds)
        
    except ValueError:
        print("Error: Invalid time format. Please use HH:MM format (24-hour)")
        sys.exit(1)

def record_stream(url, output_file, duration_seconds, max_retries=500, retry_delay=5, connection_timeout=30):
    """Record the stream for the specified duration with retry logic and append support"""
    # Create output directory if it doesn't exist
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    
    # Check if file already exists and get its size for resuming
    file_exists = os.path.exists(output_file)
    initial_bytes = 0
    if file_exists:
        initial_bytes = os.path.getsize(output_file)
        print(f"Existing file found: {output_file} ({initial_bytes / (1024 * 1024):.1f} MB)")
        print("Will append to existing file upon connection")
    
    print(f"Starting recording from {url}")
    print(f"Output file: {output_file}")
    print(f"Duration: {duration_seconds // 3600}h {(duration_seconds % 3600) // 60}m {duration_seconds % 60}s")
    print(f"Max retries: {max_retries}, Retry delay: {retry_delay}s, Timeout: {connection_timeout}s")
    
    start_time = time.time()
    total_bytes_written = initial_bytes
    retry_count = 0
    current_retry_delay = retry_delay
    
    while True:
        try:
            print(f"\n{'='*50}")
            if retry_count == 0:
                print("Attempting initial connection...")
            else:
                print(f"Retry attempt {retry_count}/{max_retries}...")
            
            # Calculate elapsed time and remaining duration
            elapsed_time = time.time() - start_time
            remaining_duration = duration_seconds - elapsed_time
            
            if remaining_duration <= 0:
                print("Recording duration completed!")
                break
            
            print(f"Remaining time: {int(remaining_duration // 3600)}h {int((remaining_duration % 3600) // 60)}m {int(remaining_duration % 60)}s")
            
            # Attempt connection
            response = requests.get(url, stream=True, timeout=connection_timeout)
            response.raise_for_status()
            
            print("✓ Connection established successfully!")
            retry_count = 0  # Reset retry count on successful connection
            current_retry_delay = retry_delay  # Reset delay
            
            # Open file in append mode
            mode = 'ab' if file_exists else 'wb'
            with open(output_file, mode) as f:
                chunk_start_time = time.time()
                last_progress_time = time.time()
                
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        total_bytes_written += len(chunk)
                        
                        # Check if we've recorded for the specified duration
                        current_time = time.time()
                        total_elapsed = current_time - start_time
                        
                        if total_elapsed >= duration_seconds:
                            print("Recording duration reached!")
                            return
                        
                        # Print progress every 30 seconds
                        if current_time - last_progress_time >= 30:
                            remaining_time = duration_seconds - total_elapsed
                            mb_written = total_bytes_written / (1024 * 1024)
                            print(f"Recording... {int(total_elapsed)}s elapsed, "
                                  f"{int(remaining_time)}s remaining, "
                                  f"{mb_written:.1f} MB total")
                            last_progress_time = current_time
            
            # If we reach here, the stream ended naturally
            print("Stream ended naturally")
            break
            
        except KeyboardInterrupt:
            print("\nRecording interrupted by user")
            print(f"Partial recording saved: {output_file}")
            print(f"Total size: {total_bytes_written / (1024 * 1024):.1f} MB")
            sys.exit(0)
            
        except (requests.exceptions.RequestException, OSError) as e:
            retry_count += 1
            print(f"✗ Connection failed: {e}")
            
            if retry_count > max_retries:
                print(f"Maximum retry attempts ({max_retries}) exceeded. Giving up.")
                print(f"Partial recording saved: {output_file}")
                print(f"Total size: {total_bytes_written / (1024 * 1024):.1f} MB")
                sys.exit(1)
            
            # Calculate elapsed time to check if we should continue
            elapsed_time = time.time() - start_time
            if elapsed_time >= duration_seconds:
                print("Recording duration completed during retry attempts!")
                break
            
            # Exponential backoff with jitter
            jitter = random.uniform(0.5, 1.5)
            sleep_time = current_retry_delay * jitter
            print(f"Waiting {sleep_time:.1f} seconds before retry...")
            time.sleep(sleep_time)
            
            # Increase delay for next retry (exponential backoff)
            current_retry_delay = min(current_retry_delay * 2, 60)  # Cap at 60 seconds
            
            # File exists now if we wrote anything
            if total_bytes_written > initial_bytes:
                file_exists = True
        
        except Exception as e:
            print(f"Unexpected error during recording: {e}")
            print(f"Partial recording saved: {output_file}")
            print(f"Total size: {total_bytes_written / (1024 * 1024):.1f} MB")
            sys.exit(1)
    
    print(f"\nRecording completed! File saved as: {output_file}")
    print(f"Total size: {total_bytes_written / (1024 * 1024):.1f} MB")
    if initial_bytes > 0:
        new_bytes = total_bytes_written - initial_bytes
        print(f"New data written: {new_bytes / (1024 * 1024):.1f} MB")

def main():
    parser = argparse.ArgumentParser(
        description="Record Bassdrive radio stream",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --start-time 20:00                    # Record at 8 PM for 2 hours
  %(prog)s --start-time 14:30 --duration 90      # Record at 2:30 PM for 90 minutes
  %(prog)s --duration 60                         # Record now for 60 minutes
        """
    )
    
    parser.add_argument(
        '--start-time',
        help='Start time in HH:MM format (24-hour). If not specified, recording starts immediately.'
    )
    
    parser.add_argument(
        '--duration',
        type=int,
        default=120,
        help='Recording duration in minutes (default: 120 minutes = 2 hours)'
    )
    
    parser.add_argument(
        '--output',
        help='Output filename (default: bassdrive_YYYYMMDD_HHMM.mp3)'
    )
    
    parser.add_argument(
        '--url',
        default='http://ice.bassdrive.net:80/stream',
        help='Stream URL (default: Bassdrive stream)'
    )
    
    parser.add_argument(
        '--max-retries',
        type=int,
        default=500,
        help='Maximum number of retry attempts on connection failure (default: 500)'
    )
    
    parser.add_argument(
        '--retry-delay',
        type=int,
        default=5,
        help='Initial delay between retries in seconds (default: 5)'
    )
    
    parser.add_argument(
        '--connection-timeout',
        type=int,
        default=30,
        help='Connection timeout in seconds (default: 30)'
    )
    
    args = parser.parse_args()
    
    # Generate default output filename if not specified
    if not args.output:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        args.output = f"bassdrive_{timestamp}.mp3"
    
    # Ensure output file has .mp3 extension
    if not args.output.lower().endswith('.mp3'):
        args.output += '.mp3'
    
    # Convert duration to seconds
    duration_seconds = args.duration * 60
    
    print("Bassdrive Stream Recorder")
    print("=" * 25)
    
    # Wait until start time if specified
    if args.start_time:
        wait_until_start_time(args.start_time)
    
    # Start recording
    record_stream(args.url, args.output, duration_seconds, 
                  args.max_retries, args.retry_delay, args.connection_timeout)

if __name__ == "__main__":
    main()