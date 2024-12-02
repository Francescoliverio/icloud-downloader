import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import threading
import getpass
from pyicloud import PyiCloudService
import shutil

# Create a lock for thread-safe operations
download_lock = threading.Lock()

# Function to load already downloaded files
def load_downloaded_files(downloaded_files_path):
    if os.path.exists(downloaded_files_path):
        with open(downloaded_files_path, "r") as f:
            # Convert filenames to lowercase for case-insensitive comparison
            return set(line.strip() for line in f)
    return set()

# Function to append a downloaded file to the tracking list
def append_to_downloaded_files(downloaded_files_path, filename):
    with download_lock:
        with open(downloaded_files_path, "a") as f:
            f.write(filename + "\n")

# Function to adjust file system attributes (e.g., creation date, modification date)
def adjust_file_metadata(file_path, photo):
    try:
        creation_time = time.mktime(photo.created.timetuple())
        os.utime(file_path, (creation_time, creation_time))  # Set access and modification times
        tqdm.write(f"Adjusted metadata for: {file_path}")
    except Exception as e:
        tqdm.write(f"Failed to adjust metadata for {file_path}: {e}")

# Function to download a single media file
def download_media_file(photo, base_dir, downloaded_files, downloaded_files_path, max_retries=3):
    filename = photo.filename
    for attempt in range(1, max_retries + 1):
        try:
            with download_lock:
                if filename in downloaded_files:
                    # File already downloaded, skip
                    return filename, True  # Indicate success

            # Start downloading the file
            download_url = photo.download()
            file_path = os.path.join(base_dir, filename)

            # Use streaming logic for efficient file writing
            with open(file_path, "wb") as file:
                with download_url.raw as response_stream:
                    shutil.copyfileobj(response_stream, file)  # Write data in chunks

            # Adjust metadata
            adjust_file_metadata(file_path, photo)

            # Mark as downloaded
            append_to_downloaded_files(downloaded_files_path, filename)
            with download_lock:
                downloaded_files.add(filename)

            tqdm.write(f"Successfully downloaded: {filename}")
            return filename, True  # Indicate success
        except Exception as e:
            tqdm.write(f"Failed to download {filename} (Attempt {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                backoff = 2 ** attempt  # Exponential backoff
                tqdm.write(f"Retrying in {backoff} seconds...")
                time.sleep(backoff)
            else:
                tqdm.write(f"Giving up on downloading {filename} after {max_retries} attempts.")
                return filename, False  # Indicate failure

# Function to process photos in batches
def process_photos_in_batches(api, base_dir, batch_size, max_workers, downloaded_files_path):
    # Fetch all photos from the iCloud API
    photos = list(api.photos.all)  # Convert to list to allow len()
    total_photos = len(photos)

    # Load the set of already downloaded files
    downloaded_files = load_downloaded_files(downloaded_files_path)

    with open(downloaded_files_path, "r") as f:
        already_downloaded = sum(1 for _ in f)

    tqdm.write(f"Total media: {total_photos}")
    tqdm.write(f"Already downloaded: {already_downloaded}")

    # Debugging loop to print all filenames and check their presence in downloaded_files
    # for photo in photos:
    #     print(f"Evaluating photo: {photo.filename}")
    #     print(f"Is in downloaded_files: {photo.filename in downloaded_files}")

    # Filter out already downloaded media
    photos_to_download = [photo for photo in photos if photo.filename not in downloaded_files]
    remaining_photos = len(photos_to_download)

    if remaining_photos == 0:
        print("All files have already been downloaded.")
        return

    tqdm.write(f"Total media to download: {remaining_photos}")

    # Initialize progress bar with total_photos and initial=already_downloaded
    with tqdm(total=total_photos, desc="Processing media", unit="file", initial=already_downloaded) as progress_bar:
        # Process photos_to_download in batches
        for i in range(0, remaining_photos, batch_size):
            batch = photos_to_download[i:i + batch_size]
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_photo = {
                    executor.submit(
                        download_media_file,
                        photo,
                        base_dir,
                        downloaded_files,
                        downloaded_files_path
                    ): photo
                    for photo in batch
                }

                for future in as_completed(future_to_photo):
                    try:
                        filename, success = future.result()
                        if not success:
                            tqdm.write(f"Failed to download: {filename}")
                        progress_bar.update(1)  # Update progress bar regardless of success
                    except Exception as e:
                        photo = future_to_photo[future]
                        tqdm.write(f"Error processing photo {photo.filename}: {e}")
                        progress_bar.update(1)  # Update progress bar even on failure

# Function to delete a photo
def delete_photo(photo, max_retries=3):
    filename = photo.filename  # Normalize filename
    for attempt in range(1, max_retries + 1):
        try:
            photo.delete()
            tqdm.write(f"Deleted photo: {filename}")
            return True
        except Exception as e:
            tqdm.write(f"Failed to delete {filename} (Attempt {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                backoff = 2 ** attempt  # Exponential backoff
                tqdm.write(f"Retrying in {backoff} seconds...")
                time.sleep(backoff)
            else:
                tqdm.write(f"Giving up on deleting {filename} after {max_retries} attempts.")
                return False

# Function to delete all photos in batches
def delete_photos_in_batches(api, batch_size, max_workers=10):
    photos = list(api.photos.all)  # Convert to list to allow len()
    total_photos = len(photos)

    if total_photos == 0:
        print("No photos to delete.")
        return

    tqdm.write(f"Total photos to delete: {total_photos}")

    with tqdm(total=total_photos, desc="Deleting media", unit="file") as progress_bar:
        # Process photos in batches
        for i in range(0, total_photos, batch_size):
            batch = photos[i:i + batch_size]
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_photo = {
                    executor.submit(delete_photo, photo): photo
                    for photo in batch
                }

                for future in as_completed(future_to_photo):
                    try:
                        success = future.result()
                        if not success:
                            photo = future_to_photo[future]
                            tqdm.write(f"Failed to delete: {photo.filename}")
                        progress_bar.update(1)  # Update progress bar regardless of success
                    except Exception as e:
                        photo = future_to_photo[future]
                        tqdm.write(f"Error deleting photo {photo.filename}: {e}")
                        progress_bar.update(1)  # Update progress bar even on failure

# Authenticate with iCloud
def authenticate_icloud(username, password):
    print("Authenticating with iCloud...")
    api = PyiCloudService(username, password)

    # Check if 2FA is required
    if api.requires_2fa:
        print("Two-factor authentication required.")
        code = input("Enter the 2FA code sent to your trusted device: ")
        result = api.validate_2fa_code(code)
        if not result:
            print("Failed to verify 2FA code.")
            return None

    print("Authentication successful.")
    return api  # Return the authenticated iCloud instance

# Main script
if __name__ == "__main__":
    # Set iCloud credentials
    username = input("Enter your iCloud username (email): ")
    password = getpass.getpass("Enter your iCloud password: ")

    # Authenticate with iCloud
    api = authenticate_icloud(username, password)
    if not api:
        exit()

    # Define paths and parameters
    base_dir = input("Enter the base directory where files should be downloaded (default: current working directory): ").strip() or os.getcwd()

    # Ensure the base directory exists
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
        print(f"Created base directory: {base_dir}")

    downloaded_files_path = os.path.join(base_dir, "downloaded_files.txt")

    try:
        batch_size = int(input("Enter the batch size (default: 1): ").strip() or 100)
        max_workers = int(input("Enter the number of workers (default: 1): ").strip() or 10)
    except ValueError:
        print("Invalid input. Using default values: batch_size=1, max_workers=1")
        batch_size = 1
        max_workers = 1

    # Choose an action
    print("\nChoose an action:")
    print("1) Download all media from iCloud")
    print("2) Delete all media from iCloud")
    print("3) Download all media from iCloud and delete them after downloading")
    action = input("Enter the number corresponding to your choice: ").strip()

    # Perform the selected action
    if action == "1":
        process_photos_in_batches(api, base_dir, batch_size, max_workers, downloaded_files_path)
    elif action == "2":
        delete_photos_in_batches(api, batch_size, max_workers)
    elif action == "3":
        process_photos_in_batches(api, base_dir, batch_size, max_workers, downloaded_files_path)
        delete_photos_in_batches(api, batch_size, max_workers)
    else:
        print("Invalid action selected. Exiting.")
