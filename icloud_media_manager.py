from pyicloud import PyiCloudService
import os
import zipfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import threading
import getpass

# Create a lock for ZIP file access
zip_lock = threading.Lock()

# Function to load already downloaded files
def load_downloaded_files(downloaded_files_path):
    if os.path.exists(downloaded_files_path):
        with open(downloaded_files_path, "r") as f:
            return set(f.read().splitlines())
    return set()

# Function to append a downloaded file to the tracking list
def append_to_downloaded_files(downloaded_files_path, filename):
    with open(downloaded_files_path, "a") as f:
        f.write(filename + "\n")

# Function to adjust file system attributes (e.g., creation date, modification date)
def adjust_file_metadata(file_path, photo):
    try:
        creation_time = time.mktime(photo.created.timetuple())
        os.utime(file_path, (creation_time, creation_time))  # Set access and modification times
        print(f"Adjusted metadata for: {file_path}")
    except Exception as e:
        print(f"Failed to adjust metadata for {file_path}: {e}")

# Function to delete a photo from iCloud with retry mechanism
def delete_photo(photo, max_retries=3):
    for attempt in range(1, max_retries + 1):
        try:
            photo.delete()
            print(f"Deleted photo: {photo.filename}")
            return True
        except Exception as e:
            print(f"Failed to delete {photo.filename} (Attempt {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                backoff = 2 ** attempt  # Exponential backoff
                print(f"Retrying in {backoff} seconds...")
                time.sleep(backoff)
            else:
                print(f"Giving up on deleting {photo.filename} after {max_retries} attempts.")
                return False


# Function to delete all photos from iCloud sequentially with retries and logging
def delete_photos_in_batches(api, batch_size, failed_deletions_log):
    photos = api.photos.all
    photo_iter = iter(photos)  # Get an iterator for the photos object

    failed_files = []  # Track files that couldn't be deleted

    # Count total photos for the progress bar
    total_photos = len(photos)
    with tqdm(total=total_photos, desc="Deleting media", unit="file") as progress_bar:
        while True:
            # Fetch a batch of photos
            batch = []
            try:
                for _ in range(batch_size):
                    batch.append(next(photo_iter))
            except StopIteration:
                pass  # End of the generator

            if not batch:
                break  # Exit loop if no more photos

            # Process each photo sequentially
            for photo in batch:
                success = delete_photo(photo)  # Call the delete function
                if not success:
                    failed_files.append(photo.filename)  # Log failed deletions
                progress_bar.update(1)

    # Log failed deletions to a file
    if failed_files:
        with open(failed_deletions_log, "w") as log_file:
            log_file.write("\n".join(failed_files))
        print(f"Failed deletions logged to {failed_deletions_log}")
    else:
        print("All photos deleted successfully.")


# Function to update metadata for already downloaded files
def update_metadata_in_zip(api, zip_path, downloaded_files_path, temp_dir):
    if not os.path.exists(downloaded_files_path) or not os.path.exists(zip_path):
        print("No downloaded files or ZIP archive found.")
        return

    # Load already downloaded files
    downloaded_files = load_downloaded_files(downloaded_files_path)
    photos = api.photos.all

    # Temporary extraction directory
    extracted_dir = os.path.join(temp_dir, "extracted")
    if not os.path.exists(extracted_dir):
        os.makedirs(extracted_dir)

    # Open the ZIP archive
    with zipfile.ZipFile(zip_path, "r") as zipf:
        for photo in photos:
            if photo.filename in downloaded_files:
                try:
                    # Extract the file from the ZIP
                    extracted_path = os.path.join(extracted_dir, photo.filename)
                    zipf.extract(photo.filename, path=extracted_dir)

                    # Update the metadata
                    print(f"Updating metadata for: {extracted_path}")
                    adjust_file_metadata(extracted_path, photo)
                except Exception as e:
                    print(f"Failed to update metadata for {photo.filename}: {e}")

    # Recreate the ZIP file with updated metadata
    updated_zip_path = os.path.join(temp_dir, "updated_" + os.path.basename(zip_path))
    with zipfile.ZipFile(updated_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(extracted_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, extracted_dir)
                zipf.write(file_path, arcname=arcname)

    # Replace the original ZIP with the updated ZIP
    os.replace(updated_zip_path, zip_path)
    print(f"Metadata updated for files in ZIP archive: {zip_path}")

# Function to download a single media file and optionally delete it
def download_and_compress(photo, zip_path, progress_bar, downloaded_files, downloaded_files_path, temp_dir=None):
    try:
        filename = photo.filename
        if filename in downloaded_files:
            print(f"Skipping already downloaded file: {filename}")
            progress_bar.update(1)  # Update the progress bar for skipped files
            return filename, True

        download_url = photo.download()
        file_data = download_url.raw.read()

        if temp_dir:
            # Save to a temporary directory for metadata adjustment
            temp_file_path = os.path.join(temp_dir, filename)
            with open(temp_file_path, "wb") as temp_file:
                temp_file.write(file_data)
            adjust_file_metadata(temp_file_path, photo)

            # Add to ZIP archive from the temporary file
            with zip_lock:
                with zipfile.ZipFile(zip_path, "a", compression=zipfile.ZIP_DEFLATED) as zipf:
                    zipf.write(temp_file_path, arcname=filename)
            os.remove(temp_file_path)
        else:
            # Save directly to the ZIP archive
            with zip_lock:
                with zipfile.ZipFile(zip_path, "a", compression=zipfile.ZIP_DEFLATED) as zipf:
                    zipf.writestr(filename, file_data)

        # Mark as downloaded
        append_to_downloaded_files(downloaded_files_path, filename)

        progress_bar.update(1)  # Update the progress bar
        return filename, True
    except Exception as e:
        print(f"Failed to download {photo.filename}: {e}")
        progress_bar.update(1)  # Update the progress bar even for failed downloads
        return photo.filename, False

# Function to process photos in batches
def process_photos_in_batches(api, zip_path, batch_size, max_workers, downloaded_files_path, temp_dir=None):
    photos = api.photos.all
    photo_iter = iter(photos)  # Get an iterator for the photos object

    # Load already downloaded files
    downloaded_files = load_downloaded_files(downloaded_files_path)

    # Count total photos for the progress bar
    total_photos = len(photos)
    with tqdm(total=total_photos, desc="Processing media", unit="file") as progress_bar:
        while True:
            # Fetch a batch of photos
            batch = []
            try:
                for _ in range(batch_size):
                    batch.append(next(photo_iter))
            except StopIteration:
                pass  # End of the generator

            if not batch:
                break  # Exit loop if no more photos

            # Process the batch with multithreading
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_photo = {
                    executor.submit(download_and_compress, photo, zip_path, progress_bar, downloaded_files, downloaded_files_path, temp_dir): photo
                    for photo in batch
                }
                for future in as_completed(future_to_photo):
                    filename, success = future.result()
                    if success:
                        print(f"Successfully downloaded: {filename}")
                    else:
                        print(f"Failed to download: {filename}")

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
    
    # Prompt for the ZIP file name
    zip_filename = input("Enter the name for the ZIP file (e.g., 'iCloudMedia.zip'): ").strip()
    if not zip_filename:
        print("Invalid file name. Using default name: 'iCloudMedia.zip'")
        zip_filename = "iCloudMedia.zip"
        
    zip_path = os.path.join(base_dir, zip_filename)
    downloaded_files_path = os.path.join(base_dir, "downloaded_files.txt")
    temp_dir = os.path.join(base_dir, "temp")

    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    
    failed_deletions_log = os.path.join(base_dir, "failed_deletions.log")

    try:
        batch_size = int(input("Enter the batch size (default: 100): ").strip() or 100)
        max_workers = int(input("Enter the number of workers (default: 10): ").strip() or 10)
    except ValueError:
        print("Invalid input. Using default values: batch_size=100, max_workers=10")
        batch_size = 100
        max_workers = 10

    # Automatically update metadata for files in the ZIP archive
    print("Checking and updating metadata for files in the ZIP archive...")
    update_metadata_in_zip(api, zip_path, downloaded_files_path, temp_dir)

    # Choose an action
    print("\nChoose an action:")
    print("1) Download all images from iCloud")
    print("2) Delete all images from iCloud")
    print("3) Download all images from iCloud and delete them after downloading")
    action = input("Enter the number corresponding to your choice: ").strip()

    # Perform the selected action
    if action == "1":
        process_photos_in_batches(api, zip_path, batch_size, max_workers, downloaded_files_path, temp_dir)
    elif action == "2":
        delete_photos_in_batches(api, batch_size, failed_deletions_log)
    elif action == "3":
        process_photos_in_batches(api, zip_path, batch_size, max_workers, downloaded_files_path, temp_dir)
        delete_photos_in_batches(api, batch_size, failed_deletions_log)
    else:
        print("Invalid action selected. Exiting.")
