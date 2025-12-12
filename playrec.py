#!/usr/bin/env python3
"""
Real-time MP3 Player for Bassdrive Recordings
Plays MP3 files as they are being recorded using pygame
"""

import argparse
import time
import threading
import os
import sys
import select
import termios
import tty
from pathlib import Path

try:
    import pygame
    pygame.mixer.init()
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

class KeyboardHandler:
    def __init__(self):
        self.key_callbacks = {}
        self.running = False
        self.thread = None

    def add_callback(self, key, callback):
        """Add a callback for a specific key"""
        self.key_callbacks[key] = callback

    def start(self):
        """Start keyboard listening thread"""
        self.running = True
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop keyboard listening"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)

    def _listen_loop(self):
        """Main keyboard listening loop"""
        # Save terminal settings
        old_settings = termios.tcgetattr(sys.stdin)

        try:
            tty.setcbreak(sys.stdin.fileno())

            while self.running:
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    key = self._get_key()
                    if key and key in self.key_callbacks:
                        self.key_callbacks[key]()

        except Exception as e:
            pass  # Silently handle terminal issues
        finally:
            # Restore terminal settings
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

    def _get_key(self):
        """Get a key press, handling escape sequences for special keys"""
        c = sys.stdin.read(1)
        if c == '\x1b':  # Escape sequence
            seq = sys.stdin.read(2)
            if seq == '[A':  # Up arrow
                return 'up'
            elif seq == '[B':  # Down arrow
                return 'down'
            elif seq == '[C':  # Right arrow
                return 'right'
            elif seq == '[D':  # Left arrow
                return 'left'
        elif c == ' ':  # Space
            return 'space'
        elif c == 'q' or c == '\x03':  # q or Ctrl+C
            return 'quit'
        return c

class ProgressBar:
    def __init__(self, width=50):
        self.width = width
        self.last_display = ""

    def update(self, recorded_seconds, playback_seconds):
        """Update progress bar display"""
        if recorded_seconds <= 0:
            return

        # Calculate progress ratio
        progress_ratio = min(playback_seconds / recorded_seconds, 1.0)
        progress_percent = int(progress_ratio * 100)

        # Create progress bar
        filled_width = int(self.width * progress_ratio)
        bar = "█" * filled_width + "░" * (self.width - filled_width)

        # Format times
        recorded_str = self._format_time(recorded_seconds)
        playback_str = self._format_time(playback_seconds)

        # Create status line
        status = f"[{bar}] {progress_percent:3d}% | Recorded: {recorded_str} | Playing: {playback_str}"

        # Only update if different to avoid flicker
        if status != self.last_display:
            # Clear previous line and print new one
            print(f"\r{status}", end="", flush=True)
            self.last_display = status

    def _format_time(self, seconds):
        """Format seconds as MM:SS"""
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"

    def clear(self):
        """Clear the progress bar"""
        print("\r" + " " * len(self.last_display) + "\r", end="", flush=True)

class RealtimePlayer:
    def __init__(self, filename):
        self.filename = filename
        self.is_playing = False
        self.is_paused = False
        self.progress_bar = ProgressBar()
        self.playback_start_time = None
        self.current_playback_position = 0  # Track current position in seconds
        self.mp3_bitrate_kbps = 160  # Estimate for time calculation
        self.keyboard_handler = KeyboardHandler()
        self._setup_keyboard_callbacks()

        if not PYGAME_AVAILABLE:
            raise ImportError("pygame is required for audio playback. Install with: pip install pygame")

    def _setup_keyboard_callbacks(self):
        """Setup keyboard event callbacks"""
        self.keyboard_handler.add_callback('left', self._seek_backward)
        self.keyboard_handler.add_callback('right', self._seek_forward)
        self.keyboard_handler.add_callback('space', self._toggle_pause)
        self.keyboard_handler.add_callback('quit', self._handle_quit)

    def _seek_backward(self):
        """Seek 10 seconds backward"""
        old_pos = self.current_playback_position
        self.current_playback_position = max(0, self.current_playback_position - 10)
        self._restart_playback_at_position()
        print(f"\rSeeking backward: {old_pos:.1f}s → {self.current_playback_position:.1f}s", end="", flush=True)

    def _seek_forward(self):
        """Seek 10 seconds forward"""
        old_pos = self.current_playback_position
        # Allow seeking beyond current recording - the file is growing!
        self.current_playback_position += 10
        self._restart_playback_at_position()
        print(f"\rSeeking forward: {old_pos:.1f}s → {self.current_playback_position:.1f}s", end="", flush=True)

    def _toggle_pause(self):
        """Toggle pause/play"""
        if pygame.mixer.music.get_busy():
            if self.is_paused:
                pygame.mixer.music.unpause()
                self.is_paused = False
                print("\rResumed playback", end="", flush=True)
            else:
                pygame.mixer.music.pause()
                self.is_paused = True
                print("\rPaused playback", end="", flush=True)

    def _handle_quit(self):
        """Handle quit command"""
        self.stop()

    def _bytes_to_seconds(self, bytes_count):
        """Convert bytes to estimated seconds based on MP3 bitrate"""
        # MP3 bitrate * 1000 / 8 = bytes per second
        bytes_per_second = (self.mp3_bitrate_kbps * 1000) / 8
        return bytes_count / bytes_per_second

    def _restart_playback_at_position(self):
        """Restart playback at current position"""
        pygame.mixer.music.stop()

        current_file_size = os.path.getsize(self.filename)
        current_recorded_seconds = self._bytes_to_seconds(current_file_size)

        # If seeking beyond current content, start from near the end instead
        actual_start_position = min(self.current_playback_position, max(0, current_recorded_seconds - 1))

        # Always reload the file to get the latest content
        pygame.mixer.music.load(self.filename)
        pygame.mixer.music.play(start=actual_start_position)

        # Adjust playback start time - if we had to adjust position, update accordingly
        if actual_start_position != self.current_playback_position:
            self.current_playback_position = actual_start_position

        self.playback_start_time = time.time() - self.current_playback_position

    def start(self):
        """Start the real-time playback"""
        if not os.path.exists(self.filename):
            print(f"Waiting for file: {self.filename}")
            while not os.path.exists(self.filename):
                time.sleep(0.1)

        print(f"Starting real-time playback of: {self.filename}")
        print("Controls: ← → seek ±10s, SPACE pause/unpause, Q quit")
        print("Note: Seeking beyond current recording will jump to live position")
        self.is_playing = True

        # Start keyboard handler
        self.keyboard_handler.start()

        # Start playback thread
        playback_thread = threading.Thread(target=self._playback_loop, daemon=True)
        playback_thread.start()

        return True

    def stop(self):
        """Stop playback"""
        self.is_playing = False
        self.keyboard_handler.stop()
        self.progress_bar.clear()
        pygame.mixer.music.stop()

    def _playback_loop(self):
        """Main playback loop"""
        # Wait a bit for some data to be written
        time.sleep(3)

        last_file_size = 0
        last_size_change_time = time.time()

        while self.is_playing:
            try:
                # Check if file exists and has some content
                if not os.path.exists(self.filename):
                    time.sleep(1)
                    continue

                current_size = os.path.getsize(self.filename)
                current_time = time.time()

                # Check if file is still growing (recording is active)
                if current_size > last_file_size:
                    last_file_size = current_size
                    last_size_change_time = current_time

                # If file hasn't grown for 10 seconds, recording might be done
                time_since_last_change = current_time - last_size_change_time

                if current_size < 1024:  # Wait for at least 1KB of data
                    time.sleep(1)
                    continue

                # Start playback if not already playing
                if not pygame.mixer.music.get_busy() and not self.is_paused:
                    current_file_size = os.path.getsize(self.filename)
                    current_recorded_seconds = self._bytes_to_seconds(current_file_size)

                    # If we're trying to play beyond current content, jump to current end
                    if self.current_playback_position >= current_recorded_seconds:
                        self.current_playback_position = max(0, current_recorded_seconds - 1)  # Start near the end

                    self._restart_playback_at_position()

                # Update progress bar
                if self.playback_start_time and pygame.mixer.music.get_busy():
                    recorded_seconds = self._bytes_to_seconds(current_size)
                    # Update current position based on elapsed time, but don't overwrite if we just seeked
                    elapsed = current_time - self.playback_start_time
                    if not self.is_paused and elapsed > self.current_playback_position + 1:  # Allow some drift
                        self.current_playback_position = elapsed
                    self.progress_bar.update(recorded_seconds, self.current_playback_position)

                # If recording appears complete (no growth for 10+ seconds), let player finish
                if time_since_last_change > 10:
                    # Clear progress bar
                    self.progress_bar.clear()
                    print("\nRecording appears complete, playback finished")
                    break

                time.sleep(1)  # Update progress every second

            except Exception as e:
                print(f"Playback error: {e}")
                time.sleep(2)

def play_realtime(filename):
    """Play a file in real-time as it's being recorded"""
    try:
        player = RealtimePlayer(filename)
    except ImportError as e:
        print(f"Error: {e}")
        return

    if not player.start():
        return

    try:
        # Keep the main thread alive
        while player.is_playing:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping playback...")
        player.stop()
    except Exception as e:
        print(f"Error: {e}")
        player.stop()

def main():
    parser = argparse.ArgumentParser(
        description="Play MP3 files in real-time as they are being recorded",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s bassdrive_20251001_2000.mp3    # Play specific file
  %(prog)s --file my_recording.mp3        # Play custom file

Requirements:
  pygame library (pip install pygame)
        """
    )

    parser.add_argument(
        'filename',
        nargs='?',
        help='MP3 file to play (if not specified, will auto-detect latest)'
    )

    parser.add_argument(
        '--file',
        help='Specify MP3 file to play'
    )

    args = parser.parse_args()

    # Determine filename
    if args.file:
        filename = args.file
    elif args.filename:
        filename = args.filename
    else:
        # Auto-detect latest bassdrive file
        mp3_files = list(Path('.').glob('bassdrive_*.mp3'))
        if not mp3_files:
            print("No bassdrive MP3 files found in current directory")
            sys.exit(1)

        # Sort by modification time (newest first)
        mp3_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        filename = str(mp3_files[0])
        print(f"Auto-selected latest file: {filename}")

    # Ensure file has .mp3 extension
    if not filename.lower().endswith('.mp3'):
        filename += '.mp3'

    print("Real-time MP3 Player")
    print("=" * 22)
    print(f"Playing: {filename}")
    print("Press Ctrl+C to stop")

    play_realtime(filename)

if __name__ == "__main__":
    main()