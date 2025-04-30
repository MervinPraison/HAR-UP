"""
Camera2_Downloader_Simple.py

A simplified script to download Camera 2 videos from the HAR-UP dataset.
This version uses a sequential approach without threading for maximum reliability.
"""

import os
import time
import json
import random

from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
from createFolder import createFolder
from oauth2client.service_account import ServiceAccountCredentials

"""
*******************************************************************************
Functions
*******************************************************************************
"""

# A function to connect with Google Drive using service account
def connect():
    gauth = GoogleAuth()
    # Use service account directly
    scope = ["https://www.googleapis.com/auth/drive"]
    gauth.credentials = ServiceAccountCredentials.from_json_keyfile_name('client_secrets.json', scope)
    drive = GoogleDrive(gauth)  
    return gauth, drive

# A function to safely find files with retry logic
def safe_file_finder(name, parent_id, drive, max_attempts=8, initial_delay=1):
    """Find a file with retry logic to handle API errors"""
    attempt = 0
    delay = initial_delay
    
    while attempt < max_attempts:
        try:
            # Search for the file
            query = f"title='{name}' and '{parent_id}' in parents and trashed=false"
            file_list = drive.ListFile({'q': query}).GetList()
            
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
            
            # Add jitter to avoid synchronized retries
            sleep_time = delay + random.uniform(0, 1)
            print(f"API error when finding {name}: {str(e)}. Retrying in {sleep_time:.2f}s (attempt {attempt}/{max_attempts})")
            time.sleep(sleep_time)
            delay *= 2  # Exponential backoff
            
            # If we're getting close to max attempts, wait longer
            if attempt > max_attempts / 2:
                extra_wait = 5 * (attempt - max_attempts / 2)
                print(f"Adding extra wait time of {extra_wait:.1f} seconds")
                time.sleep(extra_wait)

# A function to generate, refresh or authenticate Google Drive credentials
def refresh_gauth(gauth, drive):
    flg = False
    try:
        drive.GetAbout()
    except:
        gauth, drive = connect()
        flg = True
    return gauth, drive, flg

# A function to download a single file with retry logic
def download_file(file_id, path, file_name, drive, max_attempts=5):
    """Download a file with retry logic"""
    file_path = os.path.join(path, file_name)
    
    # Skip if file already exists and has content
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        print(f"Skipping: {file_name} (already downloaded)")
        return True
    
    # Ensure directory exists
    os.makedirs(path, exist_ok=True)
    
    # Implement retry with exponential backoff
    attempt = 0
    delay = 1
    
    while attempt < max_attempts:
        try:
            # Try to download the file
            f = drive.CreateFile({'id': file_id})
            f.GetContentFile(file_path)
            
            # Verify file was downloaded correctly
            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                print(f"Complete: {file_name}")
                return True
            else:
                # File exists but is empty - delete and retry
                if os.path.exists(file_path):
                    os.remove(file_path)
                raise Exception("Downloaded file is empty")
                
        except Exception as e:
            attempt += 1
            # If this is our last attempt, give up and report the error
            if attempt >= max_attempts:
                print(f"Error downloading {file_name} after {max_attempts} attempts: {str(e)}")
                # Remove partial file if it exists
                if os.path.exists(file_path):
                    os.remove(file_path)
                return False
            
            # Otherwise, wait and retry
            sleep_time = delay + random.uniform(0, 1)
            print(f"Error downloading {file_name}: {str(e)}. Retrying in {sleep_time:.2f}s (attempt {attempt}/{max_attempts})")
            time.sleep(sleep_time)
            delay *= 2  # Exponential backoff
    
    return False

# Function to download Camera 2 videos
def download_camera2_videos(parent_dir='', n_sub=[1,17], n_act=[1,11], n_trl=[1,3], use_cache=True):
    """
    Download Camera 2 videos from the HAR-UP dataset
    
    Parameters:
    parent_dir (str): Parent directory where files will be saved
    n_sub (list): Range of subjects to download [min, max]
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
    
    # Find the HAR-UP folder
    p_id = '0B_5qLZ-EZsRbWHYtQmJEWjRFQmc'
    
    print("Preparing to download files...")
    
    # Create a list to store download tasks
    download_tasks = []
    
    # Find subjects
    for i in range(n_sub[0], n_sub[1] + 1):
        sub = f'Subject{i}'
        print(f"Finding {sub}...")
        
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
                
                # Add to download tasks
                download_tasks.append((sub, act, trl, t_id))
                
    # Save cache
    if use_cache:
        try:
            with open(cache_file, 'w') as f:
                json.dump(folder_cache, f)
            print(f"Saved cache with {len(folder_cache)} folder IDs")
        except Exception as e:
            print(f"Error saving cache: {str(e)}")
    
    # Print summary
    total_files = len(download_tasks)
    print(f"Found {total_files} files to download")
    
    # Pre-check for already downloaded files
    print("\nPre-checking for already downloaded files...")
    already_downloaded = 0
    for sub, act, trl, _ in download_tasks[:]:
        path = os.path.join(parent_dir, sub, act, trl)
        f_name = sub + act + trl + 'Camera2.zip'
        file_path = os.path.join(path, f_name)
        
        # Create directory if it doesn't exist
        os.makedirs(path, exist_ok=True)
        
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            print(f"  Skipping: {f_name} (already downloaded)")
            already_downloaded += 1
            download_tasks.remove((sub, act, trl, _))
    
    print(f"Skipping {already_downloaded} already downloaded files. {len(download_tasks)} files to download.")
    
    # If no files to download, we're done
    if not download_tasks:
        print("All files have already been downloaded!")
        return
    
    # Download files sequentially
    successful_downloads = 0
    for i, (sub, act, trl, t_id) in enumerate(download_tasks):
        print(f"\nDownloading file {i+1}/{len(download_tasks)}")
        path = os.path.join(parent_dir, sub, act, trl)
        f_name = sub + act + trl + 'Camera2.zip'
        
        # Download the file
        if download_file(t_id, path, f_name, drive):
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

def main():
    # Set the parent directory where files will be saved
    # Change this to your desired download location
    parent_dir = ''
    
    # Check which subjects are already completed or partially completed
    print("Checking subject completion status...")
    subject_status = {}
    for i in range(1, 18):
        downloaded, total = check_subject_completion(parent_dir, i)
        subject_status[i] = (downloaded, total)
        print(f"Subject {i}: {downloaded}/{total} files downloaded")
    
    # Find subjects that need downloading (less than 100% complete)
    incomplete_subjects = [i for i in range(1, 18) if subject_status[i][0] < subject_status[i][1]]
    
    if not incomplete_subjects:
        print("All subjects are fully downloaded!")
        return
    
    print(f"\nIncomplete subjects: {incomplete_subjects}")
    
    # Sort subjects by completion percentage (download least complete first)
    incomplete_subjects.sort(key=lambda x: subject_status[x][0] / subject_status[x][1])
    
    # Process subjects one by one
    for subject in incomplete_subjects:
        print(f"\nProcessing subject {subject} ({subject_status[subject][0]}/{subject_status[subject][1]} files already downloaded)")
        
        try:
            # Download Camera 2 videos for a single subject
            download_camera2_videos(
                parent_dir=parent_dir,
                n_sub=[subject, subject],  # Just this one subject
                n_act=[1, 11],  # All activities (1-11)
                n_trl=[1, 3],   # All trials (1-3)
                use_cache=True   # Use caching to speed up subsequent runs
            )
            print(f"Completed subject {subject}")
            
            # Add a pause between subjects to avoid rate limiting
            if subject != incomplete_subjects[-1]:  # Don't pause after the last subject
                pause_time = 20 + random.uniform(0, 10)
                print(f"Pausing for {pause_time:.1f} seconds before next subject...")
                time.sleep(pause_time)
                
        except KeyboardInterrupt:
            print("\nDownload interrupted by user. You can restart the script to continue downloading.")
            break
        except Exception as e:
            print(f"\nAn error occurred with subject {subject}: {str(e)}")
            print("Continuing with next subject...")
            # Add a longer pause after an error
            time.sleep(45)
    
    print("\nDownload process completed. Run the script again to download any remaining files.")

if __name__ == "__main__":
    main()
