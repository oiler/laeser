#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "requests>=2.31.0",
# ]
# ///

"""
MP3 Batch Downloader with Rate Limiting

Downloads a series of numbered MP3 files with polite rate limiting
to respect the server.

Usage:
    uv run download_mp3s.py
"""

import time
import logging
from pathlib import Path
from datetime import datetime
import requests

# ============================================================================
# CONFIGURATION
# ============================================================================

# Base URL pattern - use {num} as placeholder for episode number
BASE_URL = "https://media.grc.com/sn/sn-{num:03d}.mp3"
BASE_URL = "https://media.grc.com/sn/sn-{num:03d}.txt"

# Range of episodes to download (inclusive)
START_EPISODE = 1
END_EPISODE = 1047

# Download settings
DELAY_SECONDS = 60  # Wait time between downloads (60 = 1 minute)
DOWNLOAD_FOLDER = "downloads"
LOG_FILE = "download_log.txt"

# Request settings
TIMEOUT_SECONDS = 300  # 5 minutes timeout per file
USER_AGENT = "Mozilla/5.0 (compatible; PoliteDownloader/1.0)"

# ============================================================================


def setup_logging():
    """Configure logging to file and console."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )


def download_file(url: str, output_path: Path, session: requests.Session) -> bool:
    """
    Download a single file from URL to output path.
    Returns True if successful, False otherwise.
    """
    try:
        logging.info(f"Downloading: {url}")
        
        response = session.get(
            url,
            timeout=TIMEOUT_SECONDS,
            stream=True,
            headers={'User-Agent': USER_AGENT}
        )
        
        # Check if file exists (200 OK)
        if response.status_code == 404:
            logging.warning(f"File not found (404): {url}")
            return False
        
        response.raise_for_status()
        
        # Get file size if available
        total_size = int(response.headers.get('content-length', 0))
        size_mb = total_size / (1024 * 1024) if total_size else 0
        
        # Write file to disk
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        # Verify file was written
        actual_size = output_path.stat().st_size
        actual_mb = actual_size / (1024 * 1024)
        
        logging.info(f"✓ Downloaded: {output_path.name} ({actual_mb:.2f} MB)")
        return True
        
    except requests.exceptions.Timeout:
        logging.error(f"Timeout downloading: {url}")
        return False
    except requests.exceptions.RequestException as e:
        logging.error(f"Error downloading {url}: {e}")
        return False
    except Exception as e:
        logging.error(f"Unexpected error with {url}: {e}")
        return False


def main():
    """Main execution function."""
    
    setup_logging()
    
    # Create download folder
    download_dir = Path(DOWNLOAD_FOLDER)
    download_dir.mkdir(exist_ok=True)
    
    # Summary tracking
    start_time = datetime.now()
    total_files = END_EPISODE - START_EPISODE + 1
    successful = 0
    failed = 0
    skipped = 0
    
    logging.info("=" * 60)
    logging.info("Starting MP3 download batch")
    logging.info(f"Episodes: {START_EPISODE} to {END_EPISODE} ({total_files} files)")
    logging.info(f"Download folder: {download_dir.absolute()}")
    logging.info(f"Rate limit: {DELAY_SECONDS} seconds between downloads")
    logging.info("=" * 60)
    
    # Create persistent session for connection reuse
    session = requests.Session()
    
    try:
        for episode_num in range(START_EPISODE, END_EPISODE + 1):
            # Generate URL and filename
            url = BASE_URL.format(num=episode_num)
            filename = f"sn-{episode_num:03d}.mp3"
            output_path = download_dir / filename
            
            # Skip if already downloaded
            if output_path.exists():
                logging.info(f"Skipping (already exists): {filename}")
                skipped += 1
                continue
            
            # Download file
            success = download_file(url, output_path, session)
            
            if success:
                successful += 1
            else:
                failed += 1
                # Clean up partial download if it exists
                if output_path.exists():
                    output_path.unlink()
            
            # Progress update
            completed = successful + failed + skipped
            logging.info(f"Progress: {completed}/{total_files} " +
                        f"(Success: {successful}, Failed: {failed}, Skipped: {skipped})")
            
            # Rate limiting - wait before next download (except for last file)
            if episode_num < END_EPISODE:
                logging.info(f"Waiting {DELAY_SECONDS} seconds before next download...")
                time.sleep(DELAY_SECONDS)
        
    except KeyboardInterrupt:
        logging.warning("\n⚠ Download interrupted by user")
    finally:
        session.close()
    
    # Final summary
    end_time = datetime.now()
    duration = end_time - start_time
    
    logging.info("=" * 60)
    logging.info("Download batch complete")
    logging.info(f"Total files: {total_files}")
    logging.info(f"Successful: {successful}")
    logging.info(f"Failed: {failed}")
    logging.info(f"Skipped: {skipped}")
    logging.info(f"Duration: {duration}")
    logging.info("=" * 60)
    
    if failed > 0:
        logging.warning(f"⚠ {failed} files failed to download. Check log for details.")


if __name__ == "__main__":
    main()