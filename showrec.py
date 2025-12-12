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

class ProgressBar:
    def __init__(self, width=50, show_time=True):
        self.width = width
        self.show_time = show_time
        self.last_display = ""

    def update(self, current, total, prefix="Progress", suffix="", countdown=False):
        """Update progress bar display"""
        if total <= 0:
            return

        if countdown:
            # For countdown: show remaining time as shrinking bar
            remaining = max(0, total - current)
            progress_ratio = remaining / total
            progress_percent = int((remaining / total) * 100)
            time_display = self._format_time(remaining) if self.show_time else ""
        else:
            # Normal progress: show elapsed time as growing bar
            progress_ratio = min(current / total, 1.0)
            progress_percent = int(progress_ratio * 100)
            time_display = ""
            if self.show_time:
                current_time_str = self._format_time(current)
                total_time_str = self._format_time(total)
                time_display = f" {current_time_str}/{total_time_str}"

        # Create progress bar
        filled_width = int(self.width * progress_ratio)
        if countdown:
            # For countdown: filled bar represents remaining time
            bar = "█" * filled_width + "░" * (self.width - filled_width)
        else:
            # Normal: filled bar represents progress
            bar = "█" * filled_width + "░" * (self.width - filled_width)

        # Create status line
        if countdown:
            status = f"{prefix}: [{bar}] remaining ({time_display}){suffix}"
        else:
            status = f"{prefix}: [{bar}] {progress_percent:3d}%{time_display}{suffix}"

        # Only update if different to avoid flicker
        if status != self.last_display:
            # Clear previous line and print new one
            print(f"\r{status}", end="", flush=True)
            self.last_display = status

    def _format_time(self, seconds):
        """Format seconds as MM:SS or H:MM:SS"""
        seconds = int(seconds)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"

    def clear(self):
        """Clear the progress bar"""
        print("\r" + " " * len(self.last_display) + "\r", end="", flush=True)
        self.last_display = ""

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
            
            progress_bar = ProgressBar(width=40)
            start_wait_time = time.time()
            
            while True:
                elapsed = time.time() - start_wait_time
                remaining = max(0, wait_seconds - elapsed)
                
                progress_bar.update(elapsed, wait_seconds, 
                                  prefix="Waiting", 
                                  suffix="", 
                                  countdown=True)
                
                if elapsed >= wait_seconds:
                    break
                    
                time.sleep(1)
            
            progress_bar.clear()
            print("Starting recording now!")
        
    except ValueError:
        print("Error: Invalid time format. Please use HH:MM format (24-hour)")
        sys.exit(1)

def record_stream(url, output_file, duration_seconds, max_retries=500, retry_delay=5, connection_timeout=30, quiet=False):
    """
    Record the stream for the specified duration with retry logic and append support
    
    Args:
        url: Stream URL to record from
        output_file: Output filename
        duration_seconds: Duration to record in seconds
        max_retries: Maximum retry attempts on failure
        retry_delay: Initial delay between retries
        connection_timeout: Connection timeout in seconds
        quiet: If True, suppress progress output (for background threading)
    
    Returns:
        dict: Recording result with 'success', 'file', 'size_mb', 'duration', 'error' keys
    """
    # Create output directory if it doesn't exist
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    
    # Check if file already exists and get its size for resuming
    file_exists = os.path.exists(output_file)
    initial_bytes = 0
    if file_exists:
        initial_bytes = os.path.getsize(output_file)
        if not quiet:
            print(f"Existing file found: {output_file} ({initial_bytes / (1024 * 1024):.1f} MB)")
            print("Will append to existing file upon connection")
    
    if not quiet:
        print(f"Starting recording from {url}")
        print(f"Output file: {output_file}")
        print(f"Duration: {duration_seconds // 3600}h {(duration_seconds % 3600) // 60}m {duration_seconds % 60}s")
        print(f"Max retries: {max_retries}, Retry delay: {retry_delay}s, Timeout: {connection_timeout}s")
    
    start_time = time.time()
    total_bytes_written = initial_bytes
    retry_count = 0
    current_retry_delay = retry_delay
    
    # Initialize progress bar
    progress_bar = ProgressBar(width=40) if not quiet else None
    last_progress_update = 0
    
    while True:
        try:
            if not quiet:
                print(f"\n{'='*50}")
                if retry_count == 0:
                    print("Attempting initial connection...")
                else:
                    print(f"Retry attempt {retry_count}/{max_retries}...")
            
            # Calculate elapsed time and remaining duration
            elapsed_time = time.time() - start_time
            remaining_duration = duration_seconds - elapsed_time
            
            if remaining_duration <= 0:
                if not quiet:
                    print("Recording duration completed!")
                break
            
            if not quiet:
                print(f"Remaining time: {int(remaining_duration // 3600)}h {int((remaining_duration % 3600) // 60)}m {int(remaining_duration % 60)}s")
            
            # Attempt connection
            response = requests.get(url, stream=True, timeout=connection_timeout)
            response.raise_for_status()
            
            if not quiet:
                print("✓ Connection established successfully!")
            retry_count = 0  # Reset retry count on successful connection
            current_retry_delay = retry_delay  # Reset delay
            
            # Open file in append mode
            mode = 'ab' if file_exists else 'wb'
            with open(output_file, mode) as f:
                chunk_start_time = time.time()
                
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        total_bytes_written += len(chunk)
                        
                        # Check if we've recorded for the specified duration
                        current_time = time.time()
                        total_elapsed = current_time - start_time
                        
                        if total_elapsed >= duration_seconds:
                            if progress_bar:
                                progress_bar.clear()
                            if not quiet:
                                print("\nRecording duration reached!")
                            return {
                                'success': True,
                                'file': output_file,
                                'size_mb': total_bytes_written / (1024 * 1024),
                                'duration': total_elapsed,
                                'error': None
                            }
                        
                        # Update progress bar continuously
                        if progress_bar and current_time - last_progress_update >= 1.0:  # Update every second
                            mb_written = total_bytes_written / (1024 * 1024)
                            progress_bar.update(total_elapsed, duration_seconds, 
                                              prefix="Recording", 
                                              suffix=f" ({mb_written:.1f} MB)")
                            last_progress_update = current_time
            
            # If we reach here, the stream ended but duration not complete
            # This is likely a disconnection, not a natural end - retry!
            elapsed_time = time.time() - start_time
            if elapsed_time < duration_seconds:
                retry_count += 1
                if progress_bar:
                    progress_bar.clear()
                if not quiet:
                    print(f"\n⚠️  Stream disconnected early (after {int(elapsed_time)}s of {duration_seconds}s)")
                    print(f"   Progress: {total_bytes_written / (1024 * 1024):.1f} MB recorded")
                    print(f"   This was retry attempt {retry_count}/{max_retries}")
                
                if retry_count > max_retries:
                    if not quiet:
                        print(f"\n✗ Maximum retry attempts ({max_retries}) exceeded. Giving up.")
                        print(f"Partial recording saved: {output_file}")
                        print(f"Total size: {total_bytes_written / (1024 * 1024):.1f} MB")
                    return {
                        'success': False,
                        'file': output_file,
                        'size_mb': total_bytes_written / (1024 * 1024),
                        'duration': elapsed_time,
                        'error': f'Max retries ({max_retries}) exceeded'
                    }
                
                # Exponential backoff with jitter
                jitter = random.uniform(0.5, 1.5)
                sleep_time = current_retry_delay * jitter
                if not quiet:
                    print(f"   Waiting {sleep_time:.1f} seconds before retry...")
                time.sleep(sleep_time)
                
                # Increase delay for next retry
                current_retry_delay = min(current_retry_delay * 2, 60)
                
                # We have data now, so append mode for next attempt
                file_exists = True
                continue
            else:
                if progress_bar:
                    progress_bar.clear()
                if not quiet:
                    print("\nRecording duration completed!")
                return {
                    'success': True,
                    'file': output_file,
                    'size_mb': total_bytes_written / (1024 * 1024),
                    'duration': elapsed_time,
                    'error': None
                }
            
        except KeyboardInterrupt:
            if progress_bar:
                progress_bar.clear()
            if not quiet:
                print("\nRecording interrupted by user")
                print(f"Partial recording saved: {output_file}")
                print(f"Total size: {total_bytes_written / (1024 * 1024):.1f} MB")
            return {
                'success': False,
                'file': output_file,
                'size_mb': total_bytes_written / (1024 * 1024),
                'duration': time.time() - start_time,
                'error': 'User interrupted'
            }
            
        except (requests.exceptions.RequestException, OSError) as e:
            retry_count += 1
            if not quiet:
                print(f"✗ Connection failed: {e}")
            
            if retry_count > max_retries:
                if progress_bar:
                    progress_bar.clear()
                if not quiet:
                    print(f"\nMaximum retry attempts ({max_retries}) exceeded. Giving up.")
                    print(f"Partial recording saved: {output_file}")
                    print(f"Total size: {total_bytes_written / (1024 * 1024):.1f} MB")
                return {
                    'success': False,
                    'file': output_file,
                    'size_mb': total_bytes_written / (1024 * 1024),
                    'duration': time.time() - start_time,
                    'error': str(e)
                }
            
            # Calculate elapsed time to check if we should continue
            elapsed_time = time.time() - start_time
            if elapsed_time >= duration_seconds:
                if progress_bar:
                    progress_bar.clear()
                if not quiet:
                    print("\nRecording duration completed during retry attempts!")
                return {
                    'success': True,
                    'file': output_file,
                    'size_mb': total_bytes_written / (1024 * 1024),
                    'duration': elapsed_time,
                    'error': None
                }
            
            # Exponential backoff with jitter
            jitter = random.uniform(0.5, 1.5)
            sleep_time = current_retry_delay * jitter
            if not quiet:
                print(f"Waiting {sleep_time:.1f} seconds before retry...")
            time.sleep(sleep_time)
            
            # Increase delay for next retry (exponential backoff)
            current_retry_delay = min(current_retry_delay * 2, 60)  # Cap at 60 seconds
            
            # File exists now if we wrote anything
            if total_bytes_written > initial_bytes:
                file_exists = True
        
        except Exception as e:
            if progress_bar:
                progress_bar.clear()
            if not quiet:
                print(f"\nUnexpected error during recording: {e}")
                print(f"Partial recording saved: {output_file}")
                print(f"Total size: {total_bytes_written / (1024 * 1024):.1f} MB")
            return {
                'success': False,
                'file': output_file,
                'size_mb': total_bytes_written / (1024 * 1024),
                'duration': time.time() - start_time,
                'error': str(e)
            }
    
    # Should not reach here, but just in case
    if progress_bar:
        progress_bar.clear()
    if not quiet:
        print(f"\nRecording completed! File saved as: {output_file}")
        print(f"Total size: {total_bytes_written / (1024 * 1024):.1f} MB")
        if initial_bytes > 0:
            new_bytes = total_bytes_written - initial_bytes
            print(f"New data written: {new_bytes / (1024 * 1024):.1f} MB")
    
    return {
        'success': True,
        'file': output_file,
        'size_mb': total_bytes_written / (1024 * 1024),
        'duration': time.time() - start_time,
        'error': None
    }

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
    
    # Convert duration to seconds
    duration_seconds = args.duration * 60
    
    print("Bassdrive Stream Recorder")
    print("=" * 25)
    
    # Wait until start time if specified
    if args.start_time:
        wait_until_start_time(args.start_time)
    
    # Generate default output filename if not specified (after waiting, so it uses recording start time)
    if not args.output:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        args.output = f"bassdrive_{timestamp}.mp3"
    
    # Ensure output file has .mp3 extension
    if not args.output.lower().endswith('.mp3'):
        args.output += '.mp3'
    
    # Start recording
    result = record_stream(args.url, args.output, duration_seconds, 
                  args.max_retries, args.retry_delay, args.connection_timeout)
    
    # Exit with appropriate code
    sys.exit(0 if result['success'] else 1)

if __name__ == "__main__":
    main()