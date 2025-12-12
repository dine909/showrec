#!/usr/bin/env python3
"""
Example: Using gdrive_upload as a Python module

This demonstrates how to integrate Google Drive uploads
with your recording workflow.
"""

from gdrive_upload import DriveUploader

def example_basic_upload():
    """Basic file upload example"""
    print("Example 1: Basic Upload")
    print("-" * 50)
    
    uploader = DriveUploader()
    result = uploader.upload_file('example.mp3')
    
    if result['success']:
        print(f"✅ Uploaded: {result['file_name']}")
        print(f"   File ID: {result['file_id']}")
        print(f"   Size: {result['file_size_mb']:.1f} MB")
        print(f"   Link: {result['web_link']}")
    else:
        print(f"❌ Failed: {result['error']}")
    
    return result

def example_upload_to_folder():
    """Upload to a specific folder"""
    print("\nExample 2: Upload to Folder")
    print("-" * 50)
    
    uploader = DriveUploader()
    result = uploader.upload_file(
        file_path='recording.mp3',
        folder_name='Recordings',  # Will be created if it doesn't exist
        quiet=False
    )
    
    return result

def example_quiet_upload():
    """Quiet upload for background processing"""
    print("\nExample 3: Quiet Upload (for threading)")
    print("-" * 50)
    
    uploader = DriveUploader()
    result = uploader.upload_file(
        file_path='background.mp3',
        folder_name='Recordings',
        quiet=True  # No progress output
    )
    
    # Just check the result
    if result['success']:
        print(f"✅ Silently uploaded {result['file_size_mb']:.1f} MB")
    else:
        print(f"❌ Upload failed: {result['error']}")
    
    return result

def example_batch_upload():
    """Upload multiple files"""
    print("\nExample 4: Batch Upload")
    print("-" * 50)
    
    files = ['file1.mp3', 'file2.mp3', 'file3.m4a']
    uploader = DriveUploader()
    
    results = []
    for file_path in files:
        result = uploader.upload_file(
            file_path=file_path,
            folder_name='Batch Upload',
            quiet=True
        )
        results.append(result)
    
    successful = sum(1 for r in results if r['success'])
    print(f"✅ Uploaded {successful}/{len(results)} files")
    
    return results

def example_recording_integration():
    """
    Example: Integrate with showrec recording workflow
    Record a stream, then upload to Drive
    """
    print("\nExample 5: Recording + Upload Integration")
    print("-" * 50)
    
    # Simulate recording result
    recording_result = {
        'success': True,
        'file': 'show_20251010_2000.mp3',
        'size_mb': 45.2,
        'duration': 1800.0
    }
    
    if recording_result['success']:
        print(f"✅ Recording complete: {recording_result['file']}")
        print(f"📤 Starting upload...")
        
        uploader = DriveUploader()
        upload_result = uploader.upload_file(
            file_path=recording_result['file'],
            folder_name='Radio Recordings',
            quiet=False
        )
        
        if upload_result['success']:
            print(f"✅ Upload complete!")
            print(f"🔗 {upload_result['web_link']}")
            return True
        else:
            print(f"❌ Upload failed: {upload_result['error']}")
            return False
    
    return False

def example_custom_credentials():
    """Use custom credentials file"""
    print("\nExample 6: Custom Credentials")
    print("-" * 50)
    
    uploader = DriveUploader(
        credentials_file='my_credentials.json',
        token_file='my_drive_token.json'
    )
    
    result = uploader.upload_file('file.mp3')
    return result


if __name__ == '__main__':
    print("Google Drive Upload Module Examples")
    print("=" * 50)
    print()
    print("Note: These are code examples.")
    print("Modify file paths to match your actual files.")
    print()
    
    # Uncomment to run specific examples:
    # example_basic_upload()
    # example_upload_to_folder()
    # example_quiet_upload()
    # example_batch_upload()
    # example_recording_integration()
    # example_custom_credentials()
