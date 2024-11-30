# iCloud Media Manager

## Overview

This script helps manage your iCloud media by providing three key functionalities:
1. **Download all images from iCloud.**
2. **Delete all images from iCloud.**
3. **Download all images from iCloud and delete them after downloading.**

The script also updates metadata for already downloaded files and ensures downloaded media retains accurate creation and modification timestamps.

## Download more then 100GB from iCloud

Please note that Apple iCloud has a maximum download speed of 4 MB/s. Therefore, I recommend requesting a copy of your data directly from Apple, especially for media files like photos and videos stored in iCloud. 

The process is straightforward:
1. Log in to your account at [https://privacy.apple.com/account](https://privacy.apple.com/account).
2. Once logged in, click the **"Request a copy of your data >"** button.
3. Select **iCloud Photos** or any other data you want to include.

After making your selection, you can proceed with the request and specify the maximum size for the ZIP files to be downloaded. This will make managing your downloads much easier.

## Features

- **Batch Processing**: Handle large volumes of media with adjustable batch sizes.
- **Retry Logic**: Automatically retries operations in case of errors (e.g., server overload).
- **Metadata Preservation**: Ensures accurate creation and modification dates for downloaded files.
- **Logging**: Tracks failed deletions for future retries.
- **Secure Input**: Hides your iCloud password during input.

## Requirements

- Python 3.8 or higher
- The following Python libraries:
  - `pyicloud`
  - `tqdm`
  - `getpass`

Install the required dependencies using:
```bash
pip install -r requirements.txt
```

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/your-repo/icloud-media-manager.git
   cd icloud-media-manager
   ```

2. Create a virtual environment (optional but recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the script:
   ```bash
   python icloud_media_manager.py
   ```

## Usage

When you run the script, it will prompt you to:
1. **Enter your iCloud credentials**:
   - Your email and password (password input is hidden for security).
2. **Select an action**:
   - `1` - Download all images from iCloud.
   - `2` - Delete all images from iCloud.
   - `3` - Download all images from iCloud and delete them after downloading.

### Parameters
- **Base Directory**: Specify where to save the downloaded media (default: current working directory).
- **ZIP File Name**: Name of the ZIP archive for storing downloaded files (default: `iCloudMedia.zip`).
- **Batch Size**: Number of media files processed in one batch (default: 100).
- **Max Workers**: Number of threads for parallel processing (default: 10, used only for downloads).

### Example Walkthrough

1. **Choose Action**: Select `1` to download all images.
2. **Batch Size**: Set batch size to 50 for smoother processing.
3. **ZIP File Name**: Use `MyPhotos.zip`.
4. The script downloads your photos in batches and adjusts their metadata to preserve the original creation date.

---

## Logging and Metadata Management

- **Failed Deletions Log**: If deletions fail, filenames are logged in `failed_deletions.log` for future reference.
- **Metadata Update**: Automatically updates metadata for existing files in the ZIP archive.

## Common Errors and Solutions

- **Sync Zone CAS Op-Lock Error**:
  - This occurs when multiple operations conflict on the iCloud server. The script automatically retries these operations up to three times.
- **Server Overload**:
  - If iCloud servers are overloaded, the script retries with exponential backoff. For persistent issues, retry later.

## Security

Your iCloud credentials are used securely:
- **Password Input**: Hidden during input using `getpass`.
- **Session Management**: Only session information is retained during script execution.

## Contributions

Feel free to submit issues or pull requests to improve this script!

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.