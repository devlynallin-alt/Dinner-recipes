"""
Image Validation and Processing Module

Validates uploaded/fetched images to prevent malicious file uploads.
Re-encodes images through PIL to strip potential exploits.
"""

import os
from io import BytesIO

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class ImageValidationError(Exception):
    """Raised when an image fails validation."""
    pass


# Allowed image formats (PIL format names)
ALLOWED_FORMATS = {'JPEG', 'PNG', 'GIF', 'WEBP'}

# Maximum image dimensions (prevent decompression bombs)
MAX_WIDTH = 4096
MAX_HEIGHT = 4096

# Maximum file size (10MB)
MAX_FILE_SIZE = 10 * 1024 * 1024


def validate_and_process_image(image_data, output_path, max_width=2048, max_height=2048):
    """
    Validate and re-encode an image to ensure safety.

    Args:
        image_data: Raw image bytes or file-like object
        output_path: Path where the processed image will be saved
        max_width: Maximum width to resize to (default 2048)
        max_height: Maximum height to resize to (default 2048)

    Returns:
        str: The final output path (may have different extension)

    Raises:
        ImageValidationError: If the image is invalid or potentially malicious
    """
    if not PIL_AVAILABLE:
        raise ImageValidationError("PIL/Pillow is not installed. Cannot validate images.")

    # Handle bytes or file-like object
    if isinstance(image_data, bytes):
        if len(image_data) > MAX_FILE_SIZE:
            raise ImageValidationError(f"Image too large: {len(image_data)} bytes (max {MAX_FILE_SIZE})")
        image_buffer = BytesIO(image_data)
    else:
        # File-like object - read into buffer
        image_data.seek(0)
        content = image_data.read()
        if len(content) > MAX_FILE_SIZE:
            raise ImageValidationError(f"Image too large: {len(content)} bytes (max {MAX_FILE_SIZE})")
        image_buffer = BytesIO(content)

    try:
        # Open image with PIL (validates format)
        img = Image.open(image_buffer)

        # Verify it's actually an image (detects corrupted/fake files)
        img.verify()

        # Re-open after verify (verify() leaves file in uncertain state)
        image_buffer.seek(0)
        img = Image.open(image_buffer)

        # Check format
        if img.format not in ALLOWED_FORMATS:
            raise ImageValidationError(
                f"Invalid image format: {img.format}. "
                f"Allowed formats: {', '.join(ALLOWED_FORMATS)}"
            )

        # Check dimensions (prevent decompression bombs)
        width, height = img.size
        if width > MAX_WIDTH or height > MAX_HEIGHT:
            raise ImageValidationError(
                f"Image dimensions too large: {width}x{height}. "
                f"Maximum: {MAX_WIDTH}x{MAX_HEIGHT}"
            )

        # Resize if needed
        if width > max_width or height > max_height:
            img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

        # Convert RGBA to RGB for JPEG (remove alpha channel)
        if img.mode in ('RGBA', 'LA', 'P'):
            # Create white background
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background

        # Force output to JPEG for consistency and to strip any hidden data
        # Update output path to .jpg extension
        base_path = os.path.splitext(output_path)[0]
        output_path = base_path + '.jpg'

        # Save as JPEG with reasonable quality
        img.save(output_path, 'JPEG', quality=85, optimize=True)

        return output_path

    except ImageValidationError:
        raise
    except Image.DecompressionBombError:
        raise ImageValidationError("Image appears to be a decompression bomb (too large when decoded)")
    except Exception as e:
        raise ImageValidationError(f"Invalid or corrupted image: {str(e)}")


def validate_uploaded_file(file_storage, output_path, max_width=2048, max_height=2048):
    """
    Validate and process an uploaded file from Flask's request.files.

    Args:
        file_storage: werkzeug.datastructures.FileStorage object
        output_path: Path where the processed image will be saved
        max_width: Maximum width to resize to
        max_height: Maximum height to resize to

    Returns:
        str: The final output path (always .jpg)

    Raises:
        ImageValidationError: If the image is invalid
    """
    return validate_and_process_image(file_storage, output_path, max_width, max_height)
