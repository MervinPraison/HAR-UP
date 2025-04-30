#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CSV_Downloader.py - A dedicated script to download CSV files from HAR-UP dataset
Based on the Camera2_Downloader.py with optimizations for faster downloads without threads
"""

import os
import time
import json
import io
import requests

from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
# Import only what's needed
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
    """Connect to Google Drive"""
    gauth = GoogleAuth()
    scope = ['https://www.googleapis.com/auth/drive']
    gauth.credentials = ServiceAccountCredentials.from_json_keyfile_name('client_secrets.json', scope)
    drive = GoogleDrive(gauth)
    return gauth, drive

def create_drive_service():
    """Create a Google Drive service using the service account"""
    scope = ['https://www.googleapis.com/auth/drive']
    credentials = ServiceAccountCredentials.from_json_keyfile_name('client_secrets.json', scope)
    service = build('drive', 'v3', credentials=credentials)
    return service

def direct_download(file_id, destination_path):
    """Download a file directly using the Google Drive API v3"""
    service = create_drive_service()
    
    # Get the file metadata first to check if it exists
    try:
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

# A function to safely find files with retry logic
def safe_file_finder(name, parent_id, drive, max_attempts=2, initial_delay=0.5):
    """Find a file with retry logic to handle API errors"""
    attempt = 0
    
    while attempt < max_attempts:
        try:
            # Search for the file
            print(f"    Searching for '{name}' in parent '{parent_id}'...")
            query = f"title='{name}' and '{parent_id}' in parents and trashed=false"
            file_list = drive.ListFile({'q': query, 'maxResults': 10, 'orderBy': 'title'}).GetList()
            
            if file_list and len(file_list) > 0:
                return file_list[0]['id']
            else:
                print(f"File '{name}' not found in parent '{parent_id}'")
                return ''
                
        except Exception as e:
            attempt += 1
            if attempt >= max_attempts:
                print(f"Max retries reached for {name}. Skipping.")
                return ''
            
            # Minimal retry delay for faster operation
            sleep_time = 0.5
            print(f"API error when finding {name}: {str(e)}. Retrying immediately (attempt {attempt}/{max_attempts})")
            time.sleep(sleep_time)

# A function to generate, refresh or authenticate Google Drive credentials
def refresh_gauth(gauth, drive):
    flg = False
    try:
        # Initialize the saved creds
        gauth.Authorize()
        drive = GoogleDrive(gauth)
    except Exception as e:
        print('An error occurred: ' + str(e))
        flg = True
    return gauth, drive, flg

# A function that handles downloads
def download_task(sub, act, trl, t_id, parent_dir, gauth, drive, max_attempts=3):
    """Download a single CSV file with retry logic"""
    # Create path for saving the file
    path = os.path.join(parent_dir, sub, act, trl)
    f_name = sub + act + trl + '.csv'
    file_path = os.path.join(path, f_name)
    
    # Skip only if file already exists and has content
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        print(f"Skipping: {f_name} (already downloaded)")
        return {'success': True, 'skipped': True}
    
    # Ensure directory exists
    os.makedirs(path, exist_ok=True)
    
    # Implement retry logic
    attempt = 0
    last_error = None
    
    while attempt < max_attempts:
        try:
            # Different download methods based on attempt number
            if attempt == 0:
                # Method 1: Standard PyDrive download
                f = drive.CreateFile({'id': t_id})
                f.GetContentFile(file_path)
            elif attempt == 1:
                # Method 2: Try with a fresh drive connection
                temp_gauth, temp_drive = connect()
                temp_file = temp_drive.CreateFile({'id': t_id})
                temp_file.GetContentFile(file_path)
            elif attempt == 2:
                # Method 3: Try using the direct Google Drive API
                success = direct_download(t_id, file_path)
                if not success:
                    raise Exception("Direct download failed")
            else:
                # Method 4: Last resort - try a completely different approach
                # Use requests to download from the Google Drive API
                try:
                    # Create a new service for this attempt
                    service = create_drive_service()
                    request = service.files().get_media(fileId=t_id)
                    
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
                    url = f"https://drive.google.com/uc?export=download&id={t_id}"
                    response = requests.get(url, stream=True)
                    
                    if response.status_code == 200:
                        with open(file_path, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192): 
                                f.write(chunk)
                    else:
                        raise Exception(f"HTTP download failed with status {response.status_code}")
            
            # If we got here, download succeeded - verify file has content
            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                print(f"Complete: {f_name}")
                return {'success': True, 'skipped': False}
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
                print(f"Error downloading {f_name} after {max_attempts} attempts: {last_error}")
                # Remove partial file if it exists
                if os.path.exists(file_path):
                    os.remove(file_path)
                return {'success': False, 'error': last_error}
            
            # Minimal retry delay for faster operation
            sleep_time = 0.5
            print(f"Error downloading {f_name}: {last_error}. Retrying immediately (attempt {attempt}/{max_attempts})")
            time.sleep(sleep_time)
    
    # This should never be reached, but just in case
    return {'success': False, 'error': 'Unknown error'}

# Function to download CSV files without threading
def download_csv_files(parent_dir='', n_sub=[1,17], n_act=[1,11], n_trl=[1,3], use_cache=True, timeout=10):
    """
    Download CSV files for specified subjects, activities, and trials
    without using threads for maximum reliability
    
    Parameters:
    -----------
    parent_dir : str
        Parent directory where files will be saved
    n_sub : list
        Range of subjects to download [start, end]
    n_act : list
        Range of activities to download [start, end]
    n_trl : list
        Range of trials to download [start, end]
    use_cache : bool
        Whether to use cached folder IDs to speed up preparation
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
    
    # Find the HAR-UP folder
    p_id = '1AItqj3Ue-iv7NSdR7Qta1Ez4spRjCo58'
    
    print("Preparing to download CSV files...")
    
    # Create a list to store download tasks
    download_tasks = []
    
    # Find subjects
    for i in range(n_sub[0], n_sub[1] + 1):
        sub = f'Subject{i}'
        print(f"Finding {sub}... ({i}/{n_sub[1]})")
        
        # Find subject folder
        cache_key = f"{p_id}_{sub}"
        if use_cache and cache_key in folder_cache:
            s_id = folder_cache[cache_key]
            print(f"  Using cached ID for {sub}")
        else:
            s_id = safe_file_finder(sub, p_id, drive)
            if s_id:
                folder_cache[cache_key] = s_id
                
        if not s_id:
            print(f"  Subject {sub} not found. Skipping.")
            continue
            
        # Find activities
        for j in range(n_act[0], n_act[1] + 1):
            act = f'Activity{j}'
            
            # Find activity folder
            cache_key = f"{s_id}_{act}"
            if use_cache and cache_key in folder_cache:
                a_id = folder_cache[cache_key]
            else:
                a_id = safe_file_finder(act, s_id, drive)
                if a_id:
                    folder_cache[cache_key] = a_id
                    
            if not a_id:
                print(f"  Activity {act} not found for {sub}. Skipping.")
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
                    print(f"  Trial {trl} not found for {sub} {act}. Skipping.")
                    continue
                
                # Find CSV file
                csv_name = f"{sub}{act}{trl}.csv"
                cache_key = f"{t_id}_{csv_name}"
                
                if use_cache and cache_key in folder_cache:
                    csv_id = folder_cache[cache_key]
                else:
                    csv_id = safe_file_finder(csv_name, t_id, drive)
                    if csv_id:
                        folder_cache[cache_key] = csv_id
                
                if not csv_id:
                    print(f"  CSV file {csv_name} not found. Skipping.")
                    continue
                
                # Add to download tasks
                download_tasks.append({
                    'sub': sub,
                    'act': act,
                    'trl': trl,
                    't_id': csv_id
                })
    
    # Save updated cache
    if use_cache:
        try:
            with open(cache_file, 'w') as f:
                json.dump(folder_cache, f)
            print(f"Saved cache with {len(folder_cache)} folder IDs")
        except Exception as e:
            print(f"Error saving cache: {str(e)}")
    
    # Process download tasks sequentially
    print(f"Starting downloads for {len(download_tasks)} CSV files...")
    
    success_count = 0
    skip_count = 0
    error_count = 0
    
    for idx, task in enumerate(download_tasks):
        print(f"Processing download {idx+1}/{len(download_tasks)}: {task['sub']}/{task['act']}/{task['trl']}")
        
        # Check if we need to refresh credentials
        if idx > 0 and idx % 10 == 0:
            print("Refreshing Google Drive credentials...")
            gauth, drive, refreshed = refresh_gauth(gauth, drive)
            if refreshed:
                print("Credentials refreshed successfully")
        
        # Download the file
        result = download_task(
            task['sub'], 
            task['act'], 
            task['trl'], 
            task['t_id'], 
            parent_dir, 
            gauth, 
            drive
        )
        
        if result['success']:
            if result.get('skipped', False):
                skip_count += 1
            else:
                success_count += 1
        else:
            error_count += 1
    
    # Print summary
    print("\nDownload Summary:")
    print(f"  Total files: {len(download_tasks)}")
    print(f"  Successfully downloaded: {success_count}")
    print(f"  Skipped (already exist): {skip_count}")
    print(f"  Failed: {error_count}")
    
    return success_count, skip_count, error_count

def check_subject_completion(parent_dir, subject_num):
    """
    Check if a subject's CSV files are already fully downloaded
    
    Parameters:
    -----------
    parent_dir : str
        Parent directory where files are saved
    subject_num : int
        Subject number to check
    
    Returns:
    --------
    bool
        True if all CSV files for the subject are downloaded, False otherwise
    """
    sub = f'Subject{subject_num}'
    sub_dir = os.path.join(parent_dir, sub)
    
    if not os.path.exists(sub_dir):
        return False
    
    # Check all activities and trials
    for act_num in range(1, 12):  # Activities 1-11
        act = f'Activity{act_num}'
        act_dir = os.path.join(sub_dir, act)
        
        if not os.path.exists(act_dir):
            return False
        
        for trl_num in range(1, 4):  # Trials 1-3
            trl = f'Trial{trl_num}'
            csv_file = os.path.join(act_dir, trl, f"{sub}{act}{trl}.csv")
            
            if not os.path.exists(csv_file) or os.path.getsize(csv_file) == 0:
                return False
    
    return True

def main():
    """Main function to download CSV files"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Download CSV files from HAR-UP dataset')
    parser.add_argument('--dir', type=str, default='', help='Parent directory to save files')
    parser.add_argument('--subject', type=int, default=None, help='Specific subject to download (1-17)')
    parser.add_argument('--activity', type=int, default=None, help='Specific activity to download (1-11)')
    parser.add_argument('--trial', type=int, default=None, help='Specific trial to download (1-3)')
    parser.add_argument('--no-cache', action='store_true', help='Disable folder ID caching')
    parser.add_argument('--timeout', type=int, default=10, help='Timeout for API calls in seconds')
    parser.add_argument('--test', action='store_true', help='Run in test mode (only download Subject1/Activity1/Trial1)')
    
    args = parser.parse_args()
    
    # Set up download parameters
    parent_dir = args.dir
    use_cache = not args.no_cache
    
    # Set up subject, activity, and trial ranges
    if args.test:
        print("Running in TEST MODE - only downloading Subject1/Activity1/Trial1")
        n_sub = [1, 1]
        n_act = [1, 1]
        n_trl = [1, 1]
    else:
        if args.subject:
            n_sub = [args.subject, args.subject]
        else:
            n_sub = [1, 17]
            
        if args.activity:
            n_act = [args.activity, args.activity]
        else:
            n_act = [1, 11]
            
        if args.trial:
            n_trl = [args.trial, args.trial]
        else:
            n_trl = [1, 3]
    
    # Don't check for completion, always try to download files
    # This ensures we attempt to download even if folders exist but files don't
    
    # Download CSV files
    success, skipped, errors = download_csv_files(
        parent_dir=parent_dir,
        n_sub=n_sub,
        n_act=n_act,
        n_trl=n_trl,
        use_cache=use_cache,
        timeout=args.timeout
    )
    
    print(f"\nDownload complete. {success} new files downloaded, {skipped} skipped, {errors} errors.")

if __name__ == "__main__":
    main()
