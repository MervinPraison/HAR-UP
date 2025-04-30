#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
organize_subject17.py - A script to organize Subject17 files into the correct folder structure
"""

import os
import shutil
import re

def organize_subject17_files():
    """
    Organize Subject17 files into the correct folder structure:
    Subject17/
        Activity1/
            Trial1/
            Trial1Subject17Activity1Trial1Camera2.zip
            Trial2/
            Trial2Subject17Activity1Trial2Camera2.zip
            Trial3/
            Trial3Subject17Activity1Trial3Camera2.zip
        Activity2/
            ...
    """
    # Source directory where all the files are currently located
    source_dir = '/Users/praison/phd-vlmlimitation/HAR-UP/DataBaseDownload/Subject17_Downloads/Subject17'
    
    # Get all zip files in the source directory
    files = [f for f in os.listdir(source_dir) if f.endswith('.zip') and os.path.isfile(os.path.join(source_dir, f))]
    
    # Regular expression to extract Activity and Trial numbers
    pattern = r'Subject17Activity(\d+)Trial(\d+)Camera2\.zip'
    
    # Process each file
    for file in files:
        # Extract Activity and Trial numbers
        match = re.match(pattern, file)
        if match:
            activity_num = match.group(1)
            trial_num = match.group(2)
            
            # Create paths
            activity_dir = os.path.join(source_dir, f'Activity{activity_num}')
            trial_dir = os.path.join(activity_dir, f'Trial{trial_num}')
            
            # Create directories if they don't exist
            os.makedirs(trial_dir, exist_ok=True)
            
            # Source and destination paths for the file
            source_file = os.path.join(source_dir, file)
            
            # Copy file to Activity directory with Trial prefix
            dest_file_activity = os.path.join(activity_dir, f'Trial{trial_num}{file}')
            
            # Copy the file (don't move to preserve the original)
            print(f"Copying {file} to {dest_file_activity}")
            shutil.copy2(source_file, dest_file_activity)
            
            print(f"Organized {file} into Activity{activity_num}/Trial{trial_num}")
        else:
            print(f"Warning: {file} does not match the expected pattern")
    
    print("Organization complete!")

if __name__ == "__main__":
    organize_subject17_files()
