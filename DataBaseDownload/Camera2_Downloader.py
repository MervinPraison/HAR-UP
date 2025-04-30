#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Camera2_Downloader.py - A dedicated script to download only Camera 2 videos from HAR-UP dataset
Based on the original Downloader_pydrive.py with optimizations for faster downloads
"""

import os
import time
import json
import random
import concurrent.futures
from tqdm import tqdm

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
        # Initialize the saved creds
        gauth.Authorize()
        drive = GoogleDrive(gauth)
    except Exception as e:
        print('An error occurred: ' + str(e))
        flg = True
    return gauth, drive, flg

# A function that handles downloads
def download_task(sub, act, trl, t_id, parent_dir, gauth, drive, max_attempts=5):
    """Download a single Camera 2 video file with retry logic"""
    # Create path for saving the file
    path = os.path.join(parent_dir, sub, act, trl)
    f_name = sub + act + trl + 'Camera2.zip'
    file_path = os.path.join(path, f_name)
    
    # Skip if file already exists and has content
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        print(f"Skipping: {f_name} (already downloaded)")
        return {'success': True, 'skipped': True}
    
    # Ensure directory exists
    os.makedirs(path, exist_ok=True)
    
    # Implement retry with exponential backoff
    attempt = 0
    delay = 1
    
    while attempt < max_attempts:
        try:
            # Try alternative download methods if previous attempts failed
            if attempt < 2:
                # Method 1: Standard PyDrive download
                f = drive.CreateFile({'id': t_id})
                f.GetContentFile(file_path)
            else:
                # Method 2: Try to get the file using alternative approach
                # First get file metadata
                f = drive.CreateFile({'id': t_id})
                f.FetchMetadata()
                
                # Check if we can get a download URL
                if 'downloadUrl' in f:
                    f.GetContentFile(file_path)
                elif 'exportLinks' in f and len(f['exportLinks']) > 0:
                    # Try to use export links if available
                    for mime_type, download_url in f['exportLinks'].items():
                        f.GetContentFile(file_path, mimetype=mime_type)
                        break
                else:
                    # Try one more approach - get the file directly
                    # Create a new drive connection to avoid any cached issues
                    temp_gauth, temp_drive = connect()
                    temp_file = temp_drive.CreateFile({'id': t_id})
                    temp_file.GetContentFile(file_path)
            
            # If we got here, download succeeded
            print(f"Complete: {f_name}")
            return {'success': True, 'skipped': False}
            
        except Exception as e:
            attempt += 1
            # If this is our last attempt, give up and report the error
            if attempt >= max_attempts:
                print(f"Error downloading {f_name} after {max_attempts} attempts: {str(e)}")
                # Remove partial file if it exists
                if os.path.exists(file_path):
                    os.remove(file_path)
                return {'success': False, 'error': str(e)}
            
            # Otherwise, wait and retry
            sleep_time = delay + random.uniform(0, 1)
            print(f"Error downloading {f_name}: {str(e)}. Retrying in {sleep_time:.2f}s (attempt {attempt}/{max_attempts})")
            time.sleep(sleep_time)
            delay *= 2  # Exponential backoff

# Function to download only Camera 2 videos with multithreading
def download_camera2_videos(parent_dir='', n_sub=[1,17], n_act=[1,11], n_trl=[1,3], max_workers=8, use_cache=True, batch_size=20):
    """
    Download only Camera 2 videos for specified subjects, activities, and trials
    using multithreading for faster downloads
    
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
    max_workers : int
        Maximum number of concurrent download threads
    use_cache : bool
        Whether to use cached folder IDs to speed up preparation
    """
    gauth, drive = connect()
    
    # Parent folder's ID in Google Drive
    p_id = '1AItqj3Ue-iv7NSdR7Qta1Ez4spRjCo58'
    
    # Prepare download tasks
    download_tasks = []
    
    # Cache file for folder IDs
    cache_file = 'folder_ids_cache.json'
    folder_cache = {}
    
    # Try to load cache
    if use_cache and os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                folder_cache = json.load(f)
            print(f"Loaded cache with {len(folder_cache)} folder IDs")
        except Exception as e:
            print(f"Error loading cache: {e}")
            folder_cache = {}
            
    # Create a separate connection for folder discovery to avoid conflicts
    discovery_gauth, discovery_drive = connect()
    
    print("Preparing download tasks...")
    # Use a more compact progress display
    progress_format = "{subject}: {count}/{total} paths found"
    
    for i in range(n_sub[0], n_sub[1] + 1):
        sub = 'Subject' + str(i)
        paths_found = 0
        total_paths = (n_act[1] - n_act[0] + 1) * (n_trl[1] - n_trl[0] + 1)
        print(f"Finding {sub}...")
        
        # Try to get subject ID from cache
        cache_key = f"subject_{i}"
        if use_cache and cache_key in folder_cache:
            s_id = folder_cache[cache_key]
            print(f"  Using cached ID for {sub}")
        else:
            s_id = safe_file_finder(sub, p_id, discovery_drive)
            if s_id:
                folder_cache[cache_key] = s_id
                
        if not s_id:
            print(f'The folder "{sub}" could not be found!')
            continue
            
        for j in range(n_act[0], n_act[1] + 1):
            act = 'Activity' + str(j)
            
            # Try to get activity ID from cache
            cache_key = f"subject_{i}_activity_{j}"
            if use_cache and cache_key in folder_cache:
                a_id = folder_cache[cache_key]
            else:
                a_id = safe_file_finder(act, s_id, discovery_drive)
                if a_id:
                    folder_cache[cache_key] = a_id
                    
            if not a_id:
                print(f'  The folder "{act}" could not be found in {sub}!')
                continue
                
            for k in range(n_trl[0], n_trl[1] + 1):
                trl = 'Trial' + str(k)
                
                # Create folder structure in advance
                path = os.path.join(parent_dir, sub, act, trl)
                createFolder(path)
                
                # Try to get trial ID from cache
                cache_key = f"subject_{i}_activity_{j}_trial_{k}"
                if use_cache and cache_key in folder_cache:
                    t_id = folder_cache[cache_key]
                else:
                    t_id = safe_file_finder(trl, a_id, discovery_drive)
                    if t_id:
                        folder_cache[cache_key] = t_id
                        
                if not t_id:
                    print(f'  The folder "{trl}" could not be found in {sub}/{act}!')
                    continue
                
                # Add to download tasks
                download_tasks.append((sub, act, trl, t_id))
                paths_found += 1
                
                # Update progress
                print(f"\r{progress_format.format(subject=sub, count=paths_found, total=total_paths)}", end="")
                
                # Save cache periodically
                if use_cache and len(download_tasks) % 20 == 0:
                    try:
                        with open(cache_file, 'w') as f:
                            json.dump(folder_cache, f)
                    except Exception as e:
                        print(f"\nError saving cache: {e}")
            
            # Print newline after each activity is complete
            print("")
    
    # Save final cache
    if use_cache:
        try:
            with open(cache_file, 'w') as f:
                json.dump(folder_cache, f)
            print(f"Saved cache with {len(folder_cache)} folder IDs")
        except Exception as e:
            print(f"Error saving cache: {e}")
    
    total_files = len(download_tasks)
    print(f"Found {total_files} files to download")
    
    # Execute downloads with multithreading in batches to avoid overwhelming the API
    successful_downloads = 0
    
    # Pre-check which files already exist to skip them entirely
    print("\nPre-checking for already downloaded files...")
    filtered_tasks = []
    skipped_count = 0
    
    # Create directories in advance to ensure accurate file checks
    for task in download_tasks:
        sub, act, trl, t_id = task
        path = os.path.join(parent_dir, sub, act, trl)
        createFolder(path)  # Create the directory structure first
    
    # Now check which files already exist
    for task in download_tasks:
        sub, act, trl, t_id = task
        path = os.path.join(parent_dir, sub, act, trl)
        f_name = sub + act + trl + 'Camera2.zip'
        file_path = os.path.join(path, f_name)
        
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            print(f"  Skipping: {f_name} (already downloaded)")
            skipped_count += 1
        else:
            filtered_tasks.append(task)
    
    print(f"Skipping {skipped_count} already downloaded files. {len(filtered_tasks)} files to download.")
    download_tasks = filtered_tasks
    
    # If all files are already downloaded, we're done
    if not download_tasks:
        print("All files have already been downloaded!")
        return
        
    # Process in smaller batches to avoid overwhelming the API
    for i in range(0, len(download_tasks), batch_size):
        batch = download_tasks[i:i+batch_size]
        print(f"\nProcessing batch {i//batch_size + 1}/{(len(download_tasks) + batch_size - 1)//batch_size} ({len(batch)} tasks)")
        
        # Use a smaller number of workers for better stability
        actual_workers = min(max_workers, len(batch), 4) 
        print(f"Using {actual_workers} worker threads")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=actual_workers) as executor:
            # Submit batch tasks
            future_to_task = {}
            for task in batch:
                # Triple-check if file exists before submitting task
                sub, act, trl, t_id = task
                path = os.path.join(parent_dir, sub, act, trl)
                f_name = sub + act + trl + 'Camera2.zip'
                file_path = os.path.join(path, f_name)
                
                if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                    print(f"  Skipping: {f_name} (verified before submission)")
                    successful_downloads += 1
                    continue
                    
                future = executor.submit(download_task, task[0], task[1], task[2], task[3], parent_dir, gauth, drive, max_attempts=5)
                future_to_task[future] = task
            
            # If all files in this batch were skipped, continue to next batch
            if not future_to_task:
                print("All files in this batch already exist, moving to next batch")
                continue
                
            # Process results with timeout to avoid hanging
            completed_futures = []
            with tqdm(total=len(future_to_task), desc="Downloading") as pbar:
                try:
                    for future in concurrent.futures.as_completed(future_to_task, timeout=120):
                        completed_futures.append(future)
                        task = future_to_task[future]
                        try:
                            result = future.result(timeout=30)
                            if result['success']:
                                successful_downloads += 1
                        except concurrent.futures.TimeoutError:
                            print(f"Timeout while downloading {task[0]}{task[1]}{task[2]}Camera2.zip")
                        except Exception as e:
                            print(f"Error downloading {task[0]}{task[1]}{task[2]}Camera2.zip: {e}")
                        pbar.update(1)
                except concurrent.futures.TimeoutError:
                    print("Batch timeout reached, moving to next batch")
            
            # Cancel any remaining futures
            remaining_futures = set(future_to_task.keys()) - set(completed_futures)
            if remaining_futures:
                print(f"Cancelling {len(remaining_futures)} hanging tasks")
                for future in remaining_futures:
                    future.cancel()
        
        # Short pause between batches
        if i + batch_size < len(download_tasks):
            print("Pausing briefly between batches...")
            time.sleep(1)
    
    print(f'Download complete! {successful_downloads}/{total_files} Camera 2 video files were downloaded.')

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
    
        # Process subjects individually for better control and reliability
    for subject in incomplete_subjects:
        print(f"\nProcessing subject {subject} ({subject_status[subject][0]}/{subject_status[subject][1]} files already downloaded)")
        
        try:
            # Download Camera 2 videos for a single subject
            download_camera2_videos(
                parent_dir=parent_dir,
                n_sub=[subject, subject],  # Just this one subject
                n_act=[1, 11],  # All activities (1-11)
                n_trl=[1, 3],   # All trials (1-3)
                max_workers=4,   # Further reduced workers for stability
                use_cache=True,  # Use caching to speed up subsequent runs
                batch_size=10    # Smaller batches for reliability
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
    
    # Example to download only for Subject 1, Activity 1, Trial 1:
    # download_camera2_videos(parent_dir=parent_dir, n_sub=[1, 1], n_act=[1, 1], n_trl=[1, 1], max_workers=1, use_cache=True)

if __name__ == "__main__":
    main()
