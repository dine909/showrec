#!/usr/bin/env python3
"""
Example: Using the recording APIs programmatically
Demonstrates threading and result collection
"""

import threading
import time
from queue import Queue

# Import the recording functions
from showrec import record_stream as record_mp3
from showrec_hls import record_stream as record_hls

def example_single_threaded():
    """Example: Single recording in main thread"""
    print("=== Single Threaded Recording ===\n")
    
    result = record_mp3(
        url='http://ice.bassdrive.net:80/stream',
        output_file='test_recording.mp3',
        duration_seconds=10,  # 10 seconds test
        quiet=False
    )
    
    print(f"\nResult: {result}")
    print(f"Success: {result['success']}")
    print(f"File: {result['file']}")
    print(f"Size: {result['size_mb']:.2f} MB")
    print(f"Duration: {result['duration']:.1f}s")


def example_background_thread():
    """Example: Recording in background thread"""
    print("\n=== Background Thread Recording ===\n")
    
    def record_in_background():
        print("Background: Starting recording...")
        result = record_mp3(
            url='http://ice.bassdrive.net:80/stream',
            output_file='background_recording.mp3',
            duration_seconds=10,
            quiet=True  # Quiet mode for threading
        )
        print(f"Background: Recording finished - {result['size_mb']:.2f} MB")
        return result
    
    # Start thread
    thread = threading.Thread(target=record_in_background, daemon=False)
    thread.start()
    
    # Main thread continues...
    print("Main: Recording in progress...")
    for i in range(5):
        print(f"Main: Doing other work... ({i+1}/5)")
        time.sleep(2)
    
    # Wait for recording to finish
    print("Main: Waiting for recording to complete...")
    thread.join()
    print("Main: Recording thread finished!")


def example_multiple_recordings():
    """Example: Multiple concurrent recordings"""
    print("\n=== Multiple Concurrent Recordings ===\n")
    
    results_queue = Queue()
    
    def record_with_result(name, url, duration, recorder):
        print(f"Starting: {name}")
        result = recorder(
            url=url,
            output_file=f"{name}.mp3" if recorder == record_mp3 else f"{name}.m4a",
            duration_seconds=duration,
            quiet=True
        )
        result['name'] = name
        results_queue.put(result)
        print(f"Finished: {name}")
    
    # Define recordings
    recordings = [
        ('Recording-1', 'http://ice.bassdrive.net:80/stream', 10, record_mp3),
        ('Recording-2', 'http://ice.bassdrive.net:80/stream', 10, record_mp3),
    ]
    
    # Start all recordings
    threads = []
    for name, url, duration, recorder in recordings:
        thread = threading.Thread(
            target=record_with_result,
            args=(name, url, duration, recorder),
            daemon=False
        )
        thread.start()
        threads.append(thread)
    
    # Wait for all to complete
    for thread in threads:
        thread.join()
    
    # Collect results
    print("\n--- Results ---")
    while not results_queue.empty():
        result = results_queue.get()
        status = "✓" if result['success'] else "✗"
        print(f"{status} {result['name']}: {result['size_mb']:.2f} MB in {result['duration']:.1f}s")


def example_hls_recording():
    """Example: HLS stream recording"""
    print("\n=== HLS Stream Recording ===\n")
    
    result = record_hls(
        url='http://lsn.lv/bbcradio.m3u8?station=bbc_radio_one&bitrate=320000',
        output_file='hls_test.m4a',
        duration_seconds=10,
        method='auto',
        quiet=False
    )
    
    print(f"\nHLS Result: {result}")


if __name__ == '__main__':
    print("Recording API Examples")
    print("=" * 50)
    
    # Choose which example to run
    import sys
    
    if len(sys.argv) > 1:
        example = sys.argv[1]
        if example == 'single':
            example_single_threaded()
        elif example == 'background':
            example_background_thread()
        elif example == 'multiple':
            example_multiple_recordings()
        elif example == 'hls':
            example_hls_recording()
        else:
            print(f"Unknown example: {example}")
            print("Available: single, background, multiple, hls")
    else:
        print("\nUsage: python3 example_api.py [example]")
        print("\nAvailable examples:")
        print("  single     - Single threaded recording")
        print("  background - Background thread recording")
        print("  multiple   - Multiple concurrent recordings")
        print("  hls        - HLS stream recording")
        print("\nExample: python3 example_api.py background")
