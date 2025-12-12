#!/usr/bin/env python3
"""
HLS Stream Recorder (m3u8)
Records HLS/m3u8 streams with configurable start time and duration
Supports both streamlink (preferred) and ffmpeg methods
"""

import argparse
import datetime
import time
import subprocess
import sys
import os
import signal
import threading
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

def check_streamlink():
    """Check if streamlink is installed"""
    try:
        result = subprocess.run(['streamlink', '--version'], 
                              capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def check_ffmpeg():
    """Check if ffmpeg is installed"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def fix_file_format(output_file, quiet=False):
    """
    Fix the file format using ffmpeg copy operation to resolve any format issues
    
    Args:
        output_file: Path to the recorded file
        quiet: If True, suppress output messages
        
    Returns:
        bool: True if successful, False if failed
    """
    if not os.path.exists(output_file):
        if not quiet:
            print(f"❌ Error: File {output_file} not found for fixing")
        return False
    
    if not check_ffmpeg():
        if not quiet:
            print("❌ Warning: ffmpeg not available, skipping file format fix")
        return False
    
    # Create temporary filename for the fixed file
    temp_file = output_file.replace('.m4a', '_fixed.m4a')
    
    if not quiet:
        print(f"\n🔧 Fixing file format...")
        print(f"   Source: {os.path.basename(output_file)}")
        print(f"   Temp:   {os.path.basename(temp_file)}")
    
    try:
        # Run ffmpeg to copy the file and fix format issues
        cmd = [
            'ffmpeg',
            '-i', output_file,
            '-c', 'copy',
            '-y',  # Overwrite output file if it exists
            temp_file
        ]
        
        # Run the command with suppressed output unless there's an error
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0:
            # Success - replace original with fixed file
            os.remove(output_file)
            os.rename(temp_file, output_file)
            
            if not quiet:
                print(f"✅ File format fixed successfully")
            return True
        else:
            # Error - clean up temp file if it exists
            if os.path.exists(temp_file):
                os.remove(temp_file)
            
            if not quiet:
                print(f"❌ Error fixing file format:")
                print(f"   Return code: {result.returncode}")
                if result.stderr:
                    print(f"   Error: {result.stderr.strip()}")
            return False
            
    except subprocess.TimeoutExpired:
        if not quiet:
            print("❌ Error: ffmpeg timeout during file format fix")
        # Clean up temp file if it exists
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False
    except Exception as e:
        if not quiet:
            print(f"❌ Error during file format fix: {e}")
        # Clean up temp file if it exists
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False

def record_with_streamlink(url, output_file, duration_seconds, quiet=False):
    """Record HLS stream using streamlink (preferred method)"""
    if not quiet:
        print("Using streamlink for recording...")
    
    # Streamlink command
    # --force: overwrite output file
    # --output: output filename
    # --hls-duration: duration to record in seconds
    cmd = [
        'streamlink',
        '--force',
        '--output', output_file,
        '--hls-duration', str(duration_seconds),
        url,
        'best'  # Use best quality stream
    ]
    
    if not quiet:
        print(f"Command: {' '.join(cmd)}")
    
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                  text=True, bufsize=1)
        
        # Monitor progress
        start_time = time.time()
        progress_bar = ProgressBar(width=40) if not quiet else None
        
        # Thread to update progress
        stop_event = threading.Event()
        
        def update_progress():
            while not stop_event.is_set():
                elapsed = time.time() - start_time
                if elapsed >= duration_seconds:
                    break
                
                # Get file size if it exists
                file_size = 0
                if os.path.exists(output_file):
                    file_size = os.path.getsize(output_file)
                
                if progress_bar:
                    mb_written = file_size / (1024 * 1024)
                    progress_bar.update(elapsed, duration_seconds, 
                                      prefix="Recording", 
                                      suffix=f" ({mb_written:.1f} MB)")
                time.sleep(1)
        
        if not quiet:
            progress_thread = threading.Thread(target=update_progress, daemon=True)
            progress_thread.start()
        
        # Read output
        for line in process.stdout:
            # Optionally print streamlink output for debugging
            if not quiet and ('error' in line.lower() or 'warning' in line.lower()):
                if progress_bar:
                    progress_bar.clear()
                print(f"\n{line.strip()}")
        
        # Wait for process to complete
        return_code = process.wait()
        stop_event.set()
        if not quiet:
            progress_thread.join(timeout=2)
        if progress_bar:
            progress_bar.clear()
        
        if return_code == 0:
            if not quiet:
                print("\n✓ Recording completed successfully!")
            return True
        else:
            if not quiet:
                print(f"\n✗ Streamlink exited with code {return_code}")
            return False
            
    except KeyboardInterrupt:
        if not quiet:
            print("\n⚠️  Recording interrupted by user")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        if progress_bar:
            progress_bar.clear()
        return False
    except Exception as e:
        if not quiet:
            print(f"\n✗ Error during streamlink recording: {e}")
        return False

def record_with_ffmpeg(url, output_file, duration_seconds, quiet=False):
    """Record HLS stream using ffmpeg (fallback method)"""
    if not quiet:
        print("Using ffmpeg for recording...")
    
    # FFmpeg command for HLS recording
    # -i: input URL
    # -t: duration in seconds
    # -vn: no video (audio only)
    # -acodec copy: copy audio stream without re-encoding
    # Output to M4A for AAC audio (most compatible, no re-encoding needed)
    cmd = [
        'ffmpeg',
        '-i', url,
        '-t', str(duration_seconds),
        '-vn',  # No video
        '-acodec', 'copy',  # Copy audio without re-encoding
        '-y',  # Overwrite output file
        output_file
    ]
    
    if not quiet:
        print(f"Command: {' '.join(cmd)}")
    
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, bufsize=1)
        
        # Monitor progress
        start_time = time.time()
        progress_bar = ProgressBar(width=40) if not quiet else None
        
        # Thread to update progress
        stop_event = threading.Event()
        
        def update_progress():
            while not stop_event.is_set():
                elapsed = time.time() - start_time
                if elapsed >= duration_seconds:
                    break
                
                # Get file size if it exists
                file_size = 0
                if os.path.exists(output_file):
                    file_size = os.path.getsize(output_file)
                
                if progress_bar:
                    mb_written = file_size / (1024 * 1024)
                    progress_bar.update(elapsed, duration_seconds, 
                                      prefix="Recording", 
                                      suffix=f" ({mb_written:.1f} MB)")
                time.sleep(1)
        
        if not quiet:
            progress_thread = threading.Thread(target=update_progress, daemon=True)
            progress_thread.start()
        
        # Collect stderr for error reporting
        stderr_output = []
        for line in process.stderr:
            stderr_output.append(line)
            # Show important messages
            if not quiet and ('error' in line.lower() or 'invalid' in line.lower()):
                if progress_bar:
                    progress_bar.clear()
                print(f"\n{line.strip()}")
        
        # Wait for process to complete
        return_code = process.wait()
        stop_event.set()
        if not quiet:
            progress_thread.join(timeout=2)
        if progress_bar:
            progress_bar.clear()
        
        if return_code == 0:
            if not quiet:
                print("\n✓ Recording completed successfully!")
            return True
        else:
            if not quiet:
                print(f"\n✗ FFmpeg exited with code {return_code}")
                # Show last few lines of stderr for debugging
                if stderr_output:
                    print("\nFFmpeg error output (last 10 lines):")
                    for line in stderr_output[-10:]:
                        print(f"  {line.strip()}")
            return False
            
    except KeyboardInterrupt:
        if not quiet:
            print("\n⚠️  Recording interrupted by user")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        if progress_bar:
            progress_bar.clear()
        return False
    except Exception as e:
        if not quiet:
            print(f"\n✗ Error during ffmpeg recording: {e}")
        return False

def record_stream(url, output_file, duration_seconds, method='auto', quiet=False):
    """
    Record the HLS stream for the specified duration
    
    Args:
        url: HLS stream URL (m3u8)
        output_file: Output filename
        duration_seconds: Duration to record in seconds
        method: Recording method ('auto', 'streamlink', or 'ffmpeg')
        quiet: If True, suppress progress output (for background threading)
    
    Returns:
        dict: Recording result with 'success', 'file', 'size_mb', 'duration', 'error' keys
    """
    # Create output directory if it doesn't exist
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    
    if not quiet:
        print(f"HLS Stream Recorder")
        print(f"{'='*50}")
        print(f"Stream URL: {url}")
        print(f"Output file: {output_file}")
        print(f"Duration: {duration_seconds // 3600}h {(duration_seconds % 3600) // 60}m {duration_seconds % 60}s")
        print()
    
    # Determine recording method
    if method == 'auto':
        if check_streamlink():
            method = 'streamlink'
        elif check_ffmpeg():
            method = 'ffmpeg'
        else:
            error_msg = "Neither streamlink nor ffmpeg found!"
            if not quiet:
                print(f"❌ Error: {error_msg}")
                print("\nPlease install one of the following:")
                print("  - streamlink: pip install streamlink")
                print("  - ffmpeg: brew install ffmpeg  (macOS)")
                print("           apt-get install ffmpeg  (Linux)")
            return {
                'success': False,
                'file': output_file,
                'size_mb': 0,
                'duration': 0,
                'error': error_msg
            }
    
    # Record using chosen method
    if method == 'streamlink':
        if not check_streamlink():
            error_msg = "streamlink not found!"
            if not quiet:
                print(f"❌ Error: {error_msg}")
                print("Install with: pip install streamlink")
            return {
                'success': False,
                'file': output_file,
                'size_mb': 0,
                'duration': 0,
                'error': error_msg
            }
        success = record_with_streamlink(url, output_file, duration_seconds, quiet)
    elif method == 'ffmpeg':
        if not check_ffmpeg():
            error_msg = "ffmpeg not found!"
            if not quiet:
                print(f"❌ Error: {error_msg}")
                print("Install with: brew install ffmpeg (macOS) or apt-get install ffmpeg (Linux)")
            return {
                'success': False,
                'file': output_file,
                'size_mb': 0,
                'duration': 0,
                'error': error_msg
            }
        success = record_with_ffmpeg(url, output_file, duration_seconds, quiet)
    else:
        error_msg = f"Unknown method '{method}'"
        if not quiet:
            print(f"❌ Error: {error_msg}")
        return {
            'success': False,
            'file': output_file,
            'size_mb': 0,
            'duration': 0,
            'error': error_msg
        }
    
    # Show final file info
    file_size = 0
    if success and os.path.exists(output_file):
        # Fix file format after successful recording
        fix_success = fix_file_format(output_file, quiet)
        if not fix_success and not quiet:
            print("⚠️  Warning: File format fix failed, but recording is still usable")
        
        file_size = os.path.getsize(output_file)
        if not quiet:
            print(f"\n📁 Recording saved: {output_file}")
            print(f"📊 File size: {file_size / (1024 * 1024):.1f} MB")
    
    return {
        'success': success,
        'file': output_file if success else None,
        'size_mb': file_size / (1024 * 1024) if file_size > 0 else 0,
        'duration': duration_seconds if success else 0,
        'error': None if success else 'Recording failed'
    }

def main():
    parser = argparse.ArgumentParser(
        description="Record HLS/m3u8 streams to M4A (AAC audio, no re-encoding)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --url https://example.com/stream.m3u8 --duration 120
  %(prog)s --url https://example.com/stream.m3u8 --start-time 20:00 --duration 90
  %(prog)s --url https://example.com/stream.m3u8 --duration 60 --output myshow.m4a

Note: Output is M4A format which supports AAC audio without re-encoding.
      M4A files play in all modern players (iTunes, VLC, QuickTime, etc.)

Requirements:
  One of the following:
    - streamlink: pip install streamlink  (recommended)
    - ffmpeg: brew install ffmpeg (macOS) or apt-get install ffmpeg (Linux)
        """
    )
    
    parser.add_argument(
        '--url',
        required=True,
        help='HLS stream URL (m3u8 file)'
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
        help='Output filename (default: hls_stream_YYYYMMDD_HHMM.m4a - AAC audio without re-encoding)'
    )
    
    parser.add_argument(
        '--method',
        choices=['auto', 'streamlink', 'ffmpeg'],
        default='auto',
        help='Recording method: auto (detect), streamlink (preferred), or ffmpeg (default: auto)'
    )
    
    args = parser.parse_args()
    
    # Convert duration to seconds
    duration_seconds = args.duration * 60
    
    # Wait until start time if specified
    if args.start_time:
        wait_until_start_time(args.start_time)
    
    # Generate default output filename if not specified
    if not args.output:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        args.output = f"hls_stream_{timestamp}.m4a"
    
    # Start recording
    result = record_stream(args.url, args.output, duration_seconds, args.method)
    
    # Exit with appropriate code
    sys.exit(0 if result['success'] else 1)

if __name__ == "__main__":
    main()

