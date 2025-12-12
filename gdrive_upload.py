#!/usr/bin/env python3
"""
Google Drive Upload Module

Upload files to Google Drive with proper error handling and progress tracking.
Can be used as a Python module or standalone CLI tool.

Requirements:
    pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib

Setup:
    1. Enable Google Drive API in Google Cloud Console
    2. Download credentials.json file
    3. Place credentials.json in same directory as this script
    4. First run will open browser for authentication
"""

import os
import sys
import argparse
from pathlib import Path

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
    GOOGLE_APIS_AVAILABLE = True
except ImportError:
    GOOGLE_APIS_AVAILABLE = False

# Google Drive API scopes
# Using 'drive' scope for full access to read/write files and folders
# If you want more restricted access, use 'drive.file' (only app-created files)
SCOPES = ['https://www.googleapis.com/auth/drive']

class DriveUploader:
    """Google Drive file uploader with authentication and error handling"""
    
    def __init__(self, credentials_file='credentials.json', token_file='drive_token.json'):
        """
        Initialize Drive uploader
        
        Args:
            credentials_file: Path to OAuth credentials JSON
            token_file: Path to store/load authentication token
        """
        if not GOOGLE_APIS_AVAILABLE:
            raise ImportError(
                "Google APIs not available. Install with: "
                "pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
            )
        
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.service = None
    
    def authenticate(self):
        """Authenticate with Google Drive API"""
        creds = None
        
        # Check if token.json exists
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
        
        # If there are no (valid) credentials available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_file):
                    raise FileNotFoundError(
                        f"{self.credentials_file} not found!\n"
                        "Please download your Google Drive API credentials from:\n"
                        "https://console.cloud.google.com/apis/credentials"
                    )
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, SCOPES
                )
                creds = flow.run_local_server(port=0)
            
            # Save the credentials for the next run
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())
        
        self.service = build('drive', 'v3', credentials=creds)
        return True
    
    def find_folder(self, folder_name):
        """
        Find folder by name in Drive
        
        Args:
            folder_name: Name of folder to find
            
        Returns:
            Folder ID if found, None otherwise
        """
        if not self.service:
            self.authenticate()
        
        try:
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)',
                pageSize=10
            ).execute()
            
            files = results.get('files', [])
            if files:
                return files[0]['id']
            return None
        except HttpError as error:
            self._handle_http_error(error, "finding folder")
            return None
    
    def create_folder(self, folder_name, parent_id=None):
        """
        Create a folder in Drive
        
        Args:
            folder_name: Name of folder to create
            parent_id: Optional parent folder ID
            
        Returns:
            Folder ID if successful, None otherwise
        """
        if not self.service:
            self.authenticate()
        
        try:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            if parent_id:
                file_metadata['parents'] = [parent_id]
            
            folder = self.service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()
            
            return folder.get('id')
        except HttpError as error:
            self._handle_http_error(error, "creating folder")
            return None
    
    def upload_file(self, file_path, folder_id=None, folder_name=None, mime_type=None, quiet=False):
        """
        Upload a file to Google Drive
        
        Args:
            file_path: Path to file to upload
            folder_id: Optional folder ID to upload to
            folder_name: Optional folder name (will find or create)
            mime_type: Optional MIME type (auto-detected if not provided)
            quiet: If True, suppress progress output
            
        Returns:
            dict: {
                'success': bool,
                'file_id': str or None,
                'file_name': str,
                'file_size_mb': float,
                'web_link': str or None,
                'error': str or None
            }
        """
        if not self.service:
            self.authenticate()
        
        # Validate file
        if not os.path.exists(file_path):
            return {
                'success': False,
                'file_id': None,
                'file_name': file_path,
                'file_size_mb': 0,
                'web_link': None,
                'error': f"File not found: {file_path}"
            }
        
        file_path = os.path.abspath(file_path)
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        file_size_mb = file_size / (1024 * 1024)
        
        # Resolve folder
        target_folder_id = folder_id
        if folder_name and not folder_id:
            if not quiet:
                print(f"🔍 Looking for folder: {folder_name}")
            target_folder_id = self.find_folder(folder_name)
            if not target_folder_id:
                if not quiet:
                    print(f"📁 Creating folder: {folder_name}")
                target_folder_id = self.create_folder(folder_name)
        
        # Auto-detect MIME type if not provided
        if not mime_type:
            ext = os.path.splitext(file_name)[1].lower()
            mime_types = {
                '.mp3': 'audio/mpeg',
                '.m4a': 'audio/mp4',
                '.wav': 'audio/wav',
                '.flac': 'audio/flac',
                '.ogg': 'audio/ogg',
                '.mp4': 'video/mp4',
                '.mkv': 'video/x-matroska',
                '.avi': 'video/x-msvideo',
            }
            mime_type = mime_types.get(ext, 'application/octet-stream')
        
        try:
            # Prepare file metadata
            file_metadata = {'name': file_name}
            if target_folder_id:
                file_metadata['parents'] = [target_folder_id]
            
            # Create media upload
            media = MediaFileUpload(
                file_path,
                mimetype=mime_type,
                resumable=True
            )
            
            if not quiet:
                print(f"📤 Uploading: {file_name} ({file_size_mb:.1f} MB)")
            
            # Upload file
            request = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,name,webViewLink,size'
            )
            
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status and not quiet:
                    progress = int(status.progress() * 100)
                    print(f"  Progress: {progress}%", end='\r')
            
            if not quiet:
                print(f"  Progress: 100%")
                print(f"✅ Upload complete!")
            
            return {
                'success': True,
                'file_id': response.get('id'),
                'file_name': file_name,
                'file_size_mb': file_size_mb,
                'web_link': response.get('webViewLink'),
                'error': None
            }
            
        except HttpError as error:
            error_msg = f"HTTP error: {error}"
            if not quiet:
                print(f"❌ Upload failed: {error_msg}")
            return {
                'success': False,
                'file_id': None,
                'file_name': file_name,
                'file_size_mb': file_size_mb,
                'web_link': None,
                'error': error_msg
            }
        except Exception as error:
            error_msg = str(error)
            if not quiet:
                print(f"❌ Upload failed: {error_msg}")
            return {
                'success': False,
                'file_id': None,
                'file_name': file_name,
                'file_size_mb': file_size_mb,
                'web_link': None,
                'error': error_msg
            }
    
    def list_folders(self):
        """List all folders in Drive"""
        if not self.service:
            self.authenticate()
        
        try:
            query = "mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name, createdTime)',
                pageSize=100,
                orderBy='name'
            ).execute()
            
            folders = results.get('files', [])
            
            if not folders:
                print("No folders found in Drive")
                return
            
            print("\n📁 Available Folders:")
            print("-" * 60)
            for folder in folders:
                print(f"  {folder['name']}")
                print(f"    ID: {folder['id']}")
            print()
            
        except HttpError as error:
            print(f"Error listing folders: {error}")


def main():
    """CLI interface for Drive uploader"""
    parser = argparse.ArgumentParser(
        description="Upload files to Google Drive",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s file.mp3                              # Upload to root
  %(prog)s file.mp3 --folder Recordings          # Upload to folder (create if needed)
  %(prog)s file.mp3 --folder-id abc123           # Upload to specific folder ID
  %(prog)s *.mp3 --folder Music                  # Upload multiple files
  %(prog)s --list-folders                        # List available folders
  %(prog)s --credentials mycreds.json file.mp3   # Use custom credentials

Setup:
  1. Enable Google Drive API in Google Cloud Console
  2. Download credentials.json file
  3. Place credentials.json in same directory as this script
  4. First run will open browser for authentication
        """
    )
    
    parser.add_argument(
        'files',
        nargs='*',
        help='Files to upload'
    )
    
    parser.add_argument(
        '--folder',
        help='Folder name to upload to (will be created if it does not exist)'
    )
    
    parser.add_argument(
        '--folder-id',
        help='Folder ID to upload to (takes precedence over --folder)'
    )
    
    parser.add_argument(
        '--credentials',
        default='credentials.json',
        help='Path to credentials file (default: credentials.json)'
    )
    
    parser.add_argument(
        '--token',
        default='drive_token.json',
        help='Path to token file (default: drive_token.json)'
    )
    
    parser.add_argument(
        '--list-folders',
        action='store_true',
        help='List all folders in Drive'
    )
    
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress progress output'
    )
    
    args = parser.parse_args()
    
    if not GOOGLE_APIS_AVAILABLE:
        print("❌ Missing dependencies!")
        print("Install with: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
        sys.exit(1)
    
    try:
        uploader = DriveUploader(
            credentials_file=args.credentials,
            token_file=args.token
        )
        
        # Authenticate
        uploader.authenticate()
        if not args.quiet:
            print("✓ Successfully authenticated with Google Drive")
        
        # List folders if requested
        if args.list_folders:
            uploader.list_folders()
            return
        
        # Check if files were provided
        if not args.files:
            parser.print_help()
            sys.exit(1)
        
        # Upload each file
        results = []
        for file_path in args.files:
            if not os.path.exists(file_path):
                print(f"⚠️  Skipping {file_path} - file not found")
                continue
            
            result = uploader.upload_file(
                file_path=file_path,
                folder_id=args.folder_id,
                folder_name=args.folder,
                quiet=args.quiet
            )
            results.append(result)
            
            if result['success'] and not args.quiet:
                print(f"🔗 Link: {result['web_link']}")
                print()
        
        # Summary
        if not args.quiet and len(results) > 1:
            successful = sum(1 for r in results if r['success'])
            failed = len(results) - successful
            total_mb = sum(r['file_size_mb'] for r in results if r['success'])
            
            print("=" * 60)
            print(f"✅ Uploaded: {successful} files ({total_mb:.1f} MB)")
            if failed > 0:
                print(f"❌ Failed: {failed} files")
        
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
