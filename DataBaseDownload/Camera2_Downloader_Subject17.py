"""
Camera2_Downloader_Subject17.py

A specialized script to download only Subject 17 Camera 2 videos from the HAR-UP dataset.
This version uses a sequential approach without threading for maximum reliability.
"""

import os
import time
import json
import random
import io
import requests

from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

"""
*******************************************************************************
Functions
*******************************************************************************
"""

# A function to connect with Google Drive using service account
def connect():
    """Connect to Google Drive using service account credentials"""
    # Create GoogleAuth instance
    gauth = GoogleAuth()
    
    # Try to load saved client credentials
    try:
        # Set the path to the service account credentials
        gauth.settings['client_config_file'] = 'client_secrets.json'
        
        # Set up the service account credentials
        scope = ['https://www.googleapis.com/auth/drive']
        gauth.credentials = ServiceAccountCredentials.from_json_keyfile_name(
            gauth.settings['client_config_file'], scope)
        
        # Create GoogleDrive instance
        drive = GoogleDrive(gauth)
        
        return gauth, drive
    except Exception as e:
        print(f"Error connecting to Google Drive: {str(e)}")
        return None, None

# A function to safely find files with retry logic
def safe_file_finder(name, parent_id, drive, max_attempts=8, initial_delay=1):
    """Find a file with retry logic to handle API errors"""
    # Initialize variables
    attempt = 0
    delay = initial_delay
    flg = False
    file_id = None
    
    # Try to find the file with retry logic
    while attempt < max_attempts and not flg:
        try:
            # List all files in the parent folder
            query = f"'{parent_id}' in parents and title = '{name}' and trashed=false"
            file_list = drive.ListFile({'q': query}).GetList()
            
            # Check if the file was found
            if len(file_list) > 0:
                file_id = file_list[0]['id']
                flg = True
            else:
                file_id = None
                flg = True
        except Exception as e:
            # If an error occurs, increment the attempt counter
            attempt += 1
            
            # If this is the last attempt, give up
            if attempt >= max_attempts:
                print(f"  Error finding {name} after {max_attempts} attempts: {str(e)}")
                return None
            
            # Otherwise, wait and retry
            sleep_time = delay + random.uniform(0, 1)
            print(f"  Error finding {name}. Retrying in {sleep_time:.2f}s (attempt {attempt}/{max_attempts})")
            time.sleep(sleep_time)
            delay *= 2  # Exponential backoff
            
            # Refresh the connection if we've tried a few times
            if attempt > max_attempts / 2:
                gauth, drive = connect()
    
    return file_id

# A function to refresh Google Drive credentials
def refresh_gauth(gauth, drive):
    """Refresh Google Drive credentials"""
    # Try to refresh the credentials
    try:
        # Initialize the saved creds
        gauth.Authorize()
        drive = GoogleDrive(gauth)
        return gauth, drive
    except Exception as e:
        print(f'Error refreshing credentials: {str(e)}')
        return connect()

# Create a Google Drive service using the service account
def create_drive_service():
    """Create a Google Drive service using the service account"""
    scope = ['https://www.googleapis.com/auth/drive']
    credentials = ServiceAccountCredentials.from_json_keyfile_name('client_secrets.json', scope)
    service = build('drive', 'v3', credentials=credentials)
    return service

# Download a file directly using the Google Drive API v3
def direct_download(file_id, destination_path):
    """Download a file directly using the Google Drive API v3"""
    service = create_drive_service()
    
    # Get the file metadata first to check if it exists
    try:
        # Just check if the file exists, we don't need to use the metadata
        service.files().get(fileId=file_id).execute()
    except Exception as e:
        print(f"Error getting file metadata: {str(e)}")
        return False
    
    # Now download the file
    try:
        request = service.files().get_media(fileId=file_id)
        fh = io.FileIO(destination_path, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        return True
    except Exception as e:
        print(f"Error during direct download: {str(e)}")
        return False

# A function to download a single file with retry logic
def download_file(file_id, file_name, parent_dir='', drive=None, max_attempts=5):
    """Download a single file with multiple retry methods"""
    # Create path for saving the file
    if not parent_dir:
        path = ''
    else:
        path = parent_dir
        # Create the directory if it doesn't exist
        os.makedirs(path, exist_ok=True)
    
    file_path = os.path.join(path, file_name)
    
    # Skip if file already exists and has content
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        print(f"Skipping: {file_name} (already downloaded)")
        return False
    
    # Implement retry with exponential backoff
    attempt = 0
    delay = 1
    last_error = None
    
    while attempt < max_attempts:
        try:
            # Different download methods based on attempt number
            if attempt == 0:
                # Method 1: Standard PyDrive download
                print(f"Downloading {file_name}... (Method 1: PyDrive)")
                f = drive.CreateFile({'id': file_id})
                f.GetContentFile(file_path)
            elif attempt == 1:
                # Method 2: Try with a fresh drive connection
                print(f"Downloading {file_name}... (Method 2: Fresh connection)")
                temp_gauth, temp_drive = connect()
                temp_file = temp_drive.CreateFile({'id': file_id})
                temp_file.GetContentFile(file_path)
            elif attempt == 2:
                # Method 3: Try using the direct Google Drive API
                print(f"Downloading {file_name}... (Method 3: Direct API)")
                success = direct_download(file_id, file_path)
                if not success:
                    raise Exception("Direct download failed")
            else:
                # Method 4: Last resort - try a completely different approach
                print(f"Downloading {file_name}... (Method 4: Alternative methods)")
                # Use requests to download from the Google Drive API
                try:
                    # Create a new service for this attempt
                    service = create_drive_service()
                    request = service.files().get_media(fileId=file_id)
                    
                    # Stream the file to disk
                    with open(file_path, 'wb') as f:
                        downloader = MediaIoBaseDownload(f, request)
                        done = False
                        while done is False:
                            status, done = downloader.next_chunk()
                except Exception as inner_e:
                    # If that fails too, try one more approach with requests
                    print(f"API download failed, trying direct HTTP: {str(inner_e)}")
                    # This is a fallback method that might work for some files
                    url = f"https://drive.google.com/uc?export=download&id={file_id}"
                    response = requests.get(url, stream=True)
                    
                    if response.status_code == 200:
                        with open(file_path, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192): 
                                f.write(chunk)
                    else:
                        raise Exception(f"HTTP download failed with status {response.status_code}")
            
            # If we got here, download succeeded - verify file has content
            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                print(f"Complete: {file_name}")
                return True
            else:
                # File exists but is empty - delete and retry
                if os.path.exists(file_path):
                    os.remove(file_path)
                raise Exception("Downloaded file is empty")
            
        except Exception as e:
            last_error = str(e)
            attempt += 1
            
            # If this is our last attempt, give up and report the error
            if attempt >= max_attempts:
                print(f"Error downloading {file_name} after {max_attempts} attempts: {last_error}")
                # Remove partial file if it exists
                if os.path.exists(file_path):
                    os.remove(file_path)
                return False
            
            # Otherwise, wait and retry
            sleep_time = delay + random.uniform(0, 1)
            print(f"Error downloading {file_name}: {last_error}. Retrying in {sleep_time:.2f}s (attempt {attempt}/{max_attempts})")
            time.sleep(sleep_time)
            delay *= 2  # Exponential backoff
    
    return False

# Function to download Camera 2 videos
def download_camera2_videos(parent_dir='', n_act=[1,11], n_trl=[1,3], use_cache=True):
    """
    Download Camera 2 videos from the HAR-UP dataset
    
    Parameters:
    parent_dir (str): Parent directory where files will be saved
    n_act (list): Range of activities to download [min, max]
    n_trl (list): Range of trials to download [min, max]
    use_cache (bool): Whether to use folder ID caching
    """
    
    # Initialize variables
    folder_cache = {}
    cache_file = 'folder_ids_cache.json'
    
    # Load cache if it exists and use_cache is True
    if use_cache and os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                folder_cache = json.load(f)
            print(f"Loaded cache with {len(folder_cache)} folder IDs")
        except Exception as e:
            print(f"Error loading cache: {str(e)}")
            folder_cache = {}
    
    # Connect to Google Drive
    gauth, drive = connect()
    
    # Parent folder's ID in Google Drive
    p_id = '1AItqj3Ue-iv7NSdR7Qta1Ez4spRjCo58'
    
    print("Preparing to download files...")
    
    # Find the Subject17 folder
    print("Finding Subject17...")
    subject_id = None
    
    # Check if the Subject17 folder ID is in the cache
    cache_key = f"{p_id}_Subject17"
    if cache_key in folder_cache:
        print("  Using cached ID for Subject17")
        subject_id = folder_cache[cache_key]
    else:
        # List all files in the parent folder
        query = f"'{p_id}' in parents and trashed=false"
        file_list = drive.ListFile({'q': query}).GetList()
        
        # Find the Subject17 folder
        for file in file_list:
            if file['title'] == 'Subject17':
                subject_id = file['id']
                folder_cache[cache_key] = subject_id
                break
    
    # Save the cache
    if use_cache:
        try:
            with open(cache_file, 'w') as f:
                json.dump(folder_cache, f)
            print(f"Saved cache with {len(folder_cache)} folder IDs")
        except Exception as e:
            print(f"Error saving cache: {str(e)}")
    
    if not subject_id:
        print("Could not find Subject17 folder")
        return 0, 0
    
    # Create the parent directory if it doesn't exist
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)
        print(f"Created directory {parent_dir}")
        
    # Download the subject
    return download_subject(subject_id, "Subject17", parent_dir, n_act, n_trl, drive, use_cache)

def download_subject(subject_id, subject_name, parent_dir, n_act, n_trl, drive, use_cache):
    # Initialize variables
    folder_cache = {}
    cache_file = 'folder_ids_cache.json'
    
    # Load cache if it exists and use_cache is True
    if use_cache and os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                folder_cache = json.load(f)
            print(f"Loaded cache with {len(folder_cache)} folder IDs")
        except Exception as e:
            print(f"Error loading cache: {str(e)}")
            folder_cache = {}
    
    # Download tasks
    download_tasks = []
    
    # Find activities
    for i in range(n_act[0], n_act[1] + 1):
        act = f'Activity{i}'
        
        # Find activity folder
        cache_key = f"{subject_id}_{act}"
        if use_cache and cache_key in folder_cache:
            a_id = folder_cache[cache_key]
        else:
            a_id = safe_file_finder(act, subject_id, drive)
            if a_id:
                folder_cache[cache_key] = a_id
                
        if not a_id:
            print(f"  Activity {act} not found for {subject_name}. Skipping.")
            continue
        
        # Find trials
        for k in range(n_trl[0], n_trl[1] + 1):
            trl = f'Trial{k}'
            
            # Find trial folder
            cache_key = f"{a_id}_{trl}"
            if use_cache and cache_key in folder_cache:
                t_id = folder_cache[cache_key]
            else:
                t_id = safe_file_finder(trl, a_id, drive)
                if t_id:
                    folder_cache[cache_key] = t_id
                    
            if not t_id:
                print(f"  Trial {trl} not found for {subject_name} {act}. Skipping.")
                continue
            
            # Find Camera 2 video
            file_name = f"{subject_name}{act}{trl}Camera2.zip"
            cache_key = f"{t_id}_{file_name}"
            if use_cache and cache_key in folder_cache:
                file_id = folder_cache[cache_key]
            else:
                file_id = safe_file_finder(file_name, t_id, drive)
                if file_id:
                    folder_cache[cache_key] = file_id
                    
            if not file_id:
                print(f"  File {file_name} not found. Skipping.")
                continue
                
            # Add to download tasks
            download_tasks.append((subject_name, act, trl, file_id))
            
    # Save cache
    if use_cache:
        try:
            with open(cache_file, 'w') as f:
                json.dump(folder_cache, f)
            print(f"Saved cache with {len(folder_cache)} folder IDs")
        except Exception as e:
            print(f"Error saving cache: {str(e)}")
    
    # Check if there are any files to download
    if len(download_tasks) == 0:
        print("Found 0 files to download")
        return 0, 0
    
    # Download files sequentially
    print(f"\nDownloading {len(download_tasks)} files...")
    successful_downloads = 0
    
    for i, (sub, act, trl, file_id) in enumerate(download_tasks):
        print(f"\nDownloading file {i+1}/{len(download_tasks)}")
        
        # Create path for the file
        path = os.path.join(parent_dir, sub)
        
        # Create the file name
        f_name = sub + act + trl + 'Camera2.zip'
        
        # Download the file
        if download_file(file_id, f_name, path, drive):
            successful_downloads += 1
        
        # Add a small pause between downloads to avoid rate limiting
        if i < len(download_tasks) - 1:  # Don't pause after the last file
            pause_time = 2 + random.uniform(0, 1)
            print(f"Pausing for {pause_time:.1f} seconds before next download...")
            time.sleep(pause_time)
    
    print(f'\nDownload complete! {successful_downloads}/{len(download_tasks)} Camera 2 video files were downloaded.')

def check_subject_completion(parent_dir, subject_num):
    """Check if a subject's Camera2 files are already fully downloaded"""
    sub = f'Subject{subject_num}'
    total_files = 11 * 3  # 11 activities * 3 trials
    downloaded_files = 0
    
    for act_num in range(1, 12):
        act = f'Activity{act_num}'
        for trl_num in range(1, 4):
            trl = f'Trial{trl_num}'
            path = os.path.join(parent_dir, sub, act, trl)
            f_name = sub + act + trl + 'Camera2.zip'
            file_path = os.path.join(path, f_name)
            
            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                downloaded_files += 1
    
    return downloaded_files, total_files

def get_harup_folder_id():
    """Get the HAR-UP folder ID"""
    # We now have the correct parent folder ID
    return '1AItqj3Ue-iv7NSdR7Qta1Ez4spRjCo58'

def list_subjects(harup_folder_id):
    """List all subjects available in the HAR-UP folder"""
    if not harup_folder_id:
        print("Cannot list subjects without HAR-UP folder ID")
        return []
        
    # Connect to Google Drive
    gauth, drive = connect()
    
    print(f"\nListing all available subjects in the HAR-UP folder (ID: {harup_folder_id})...")
    
    # Get all files in the HAR-UP folder
    query = f"'{harup_folder_id}' in parents and trashed=false"
    file_list = drive.ListFile({'q': query}).GetList()
    
    # Print all files/folders
    print(f"Found {len(file_list)} items:")
    for file in file_list:
        print(f"  {file['title']} (ID: {file['id']})")
    
    # Filter only folders that look like subjects
    subjects = [file for file in file_list if file['title'].startswith('Subject')]
    
    print(f"\nFound {len(subjects)} subject folders:")
    for subject in subjects:
        print(f"  {subject['title']}")
    
    return subjects

def explore_folder_structure(folder_id, folder_name, drive, depth=0, max_depth=3):
    """Recursively explore the folder structure"""
    indent = "  " * depth
    print(f"{indent}Exploring {folder_name} (ID: {folder_id})")
    
    if depth >= max_depth:
        print(f"{indent}Reached max depth, stopping exploration")
        return
    
    # Get all items in the folder
    query = f"'{folder_id}' in parents and trashed=false"
    file_list = drive.ListFile({'q': query}).GetList()
    
    print(f"{indent}Found {len(file_list)} items:")
    for file in file_list:
        is_folder = file.get('mimeType') == 'application/vnd.google-apps.folder'
        file_type = "Folder" if is_folder else "File"
        print(f"{indent}- {file['title']} ({file_type}, ID: {file['id']})")
        
        # Recursively explore folders
        if is_folder:
            explore_folder_structure(file['id'], file['title'], drive, depth + 1, max_depth)

def main():
    # Set the parent directory where files will be saved
    # Change this to your desired download location
    parent_dir = 'Subject17_Downloads'
    
    # Get the HAR-UP folder ID
    harup_folder_id = get_harup_folder_id()
    print(f"Using HAR-UP folder ID: {harup_folder_id}")
    
    # List all available subjects
    subjects = list_subjects(harup_folder_id)
    
    if not subjects:
        print("No subjects found in the HAR-UP folder")
        return
    
    # Check if Subject 17 exists
    subject_17 = next((s for s in subjects if s['title'] == 'Subject17'), None)
    
    if subject_17:
        print(f"\nFound Subject 17 (ID: {subject_17['id']})")
        
        # Connect to Google Drive
        gauth, drive = connect()
        
        # Explore the Subject17 folder structure
        print("\nExploring Subject17 folder structure:")
        explore_folder_structure(subject_17['id'], subject_17['title'], drive)
        
        print("\nImportant Note: The service account may not have permission to download these files.")
        print("If you encounter 403 Forbidden errors, you may need to:")
        print("1. Share the HAR-UP folder with the service account email")
        print("2. Make sure the service account has viewer access to the files")
        print("3. Try using a different authentication method if necessary")
        
        print("\nTrying to download Subject 17 videos...")
        try:
            # Download Camera 2 videos for Subject 17 only
            download_camera2_videos(
                parent_dir=parent_dir,
                n_act=[1, 11],  # All activities (1-11)
                n_trl=[1, 3],   # All trials (1-3)
                use_cache=True   # Use caching to speed up subsequent runs
            )
            print("Completed Subject 17")
        except KeyboardInterrupt:
            print("\nDownload interrupted by user. You can restart the script to continue downloading.")
        except Exception as e:
            print(f"\nAn error occurred: {str(e)}")
            print("You can restart the script to continue downloading.")
    else:
        print("\nSubject 17 not found in the HAR-UP folder.")
        print("Available subjects:")
        for i, subject in enumerate(subjects):
            print(f"  {i+1}. {subject['title']}")
        print("\nPlease modify the script to download one of these subjects instead.")
    
    print("\nProcess completed.")

if __name__ == "__main__":
    main()
