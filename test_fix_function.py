#!/usr/bin/env python3
"""
Test script to verify the file format fix functionality
"""
import os
import tempfile
from showrec_hls import fix_file_format, check_ffmpeg

def test_fix_function():
    print("Testing file format fix function...")
    
    # Check if ffmpeg is available
    if not check_ffmpeg():
        print("❌ ffmpeg not available - cannot test fix function")
        return False
    
    # Create a temporary test file (simulate a recorded file)
    with tempfile.NamedTemporaryFile(suffix='.m4a', delete=False) as temp_file:
        # Write some dummy content to simulate a recorded file
        temp_file.write(b"dummy audio data for testing")
        temp_filename = temp_file.name
    
    print(f"Created test file: {temp_filename}")
    
    try:
        # Test the fix function (this will fail but we can test the logic)
        result = fix_file_format(temp_filename, quiet=False)
        
        if result:
            print("✅ Fix function completed successfully")
        else:
            print("⚠️  Fix function failed (expected for dummy data)")
        
        return True
        
    finally:
        # Clean up test file
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
            print(f"Cleaned up test file: {temp_filename}")

if __name__ == "__main__":
    test_fix_function()