import os
import sys
import shutil
import zipfile
import argparse
import logging

logger = logging.getLogger(__name__)


def extract_frames(
    video_path,
    output_dir,
    fps=None,
    interval_ms=None,
    output_format="png",
    jpeg_quality=85,
    progress_callback=None,
):
    """
    Extract frames from a video file.

    Args:
        video_path:        Path to the input video file.
        output_dir:        Directory to save extracted frames.
        fps:               Extract at this frame rate (None = all frames).
        interval_ms:       Extract every N milliseconds (overrides fps if set).
        output_format:     'png' or 'jpeg'.
        jpeg_quality:      JPEG quality 1-100 (only used when format is jpeg).
        progress_callback: Optional callable(current, total) for progress updates.

    Returns:
        dict with extraction results.
    """
    try:
        import cv2
    except ImportError:
        raise ImportError(
            "OpenCV is required. Install with: pip install opencv-python"
        )

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    os.makedirs(output_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    video_fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration_s = total_frames / video_fps if video_fps > 0 else 0

    logger.info(
        "Video: %dx%d, %.1f fps, %d frames, %.1fs",
        width, height, video_fps, total_frames, duration_s,
    )

    # Determine frame interval
    if interval_ms is not None:
        frame_interval = (interval_ms / 1000.0) * video_fps
    elif fps is not None and fps > 0:
        frame_interval = video_fps / fps
    else:
        frame_interval = 1

    # File extension + write params
    fmt = output_format.lower()
    if fmt in ("jpg", "jpeg"):
        ext = ".jpg"
        write_params = [cv2.IMWRITE_JPEG_QUALITY, int(jpeg_quality)]
    else:
        ext = ".png"
        write_params = [cv2.IMWRITE_PNG_COMPRESSION, 3]

    extracted = 0
    frame_idx = 0
    next_frame = 0.0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx >= next_frame:
            filename = f"frame_{extracted:06d}{ext}"
            filepath = os.path.join(output_dir, filename)
            cv2.imwrite(filepath, frame, write_params)
            extracted += 1
            next_frame += frame_interval

            # Fire progress callback
            if progress_callback is not None:
                try:
                    progress_callback(frame_idx + 1, total_frames)
                except Exception:
                    pass

            if extracted % 100 == 0:
                logger.info("Extracted %d frames...", extracted)

        frame_idx += 1

    cap.release()

    # Final progress callback
    if progress_callback is not None:
        try:
            progress_callback(total_frames, total_frames)
        except Exception:
            pass

    result = {
        "video_path": video_path,
        "output_dir": output_dir,
        "video_fps": video_fps,
        "video_resolution": f"{width}x{height}",
        "total_video_frames": total_frames,
        "duration_seconds": duration_s,
        "extracted_frames": extracted,
        "target_fps": fps,
        "interval_ms": interval_ms,
        "output_format": fmt,
    }

    logger.info(
        "Extraction complete: %d frames saved to %s", extracted, output_dir
    )
    return result


def extract_frames_to_zip(
    video_path,
    zip_path,
    fps=None,
    interval_ms=None,
    output_format="png",
    jpeg_quality=85,
    progress_callback=None,
):
    """
    Extract frames and package them directly into a ZIP file.

    Args:
        video_path:        Path to the input video file.
        zip_path:          Path for the output ZIP file.
        fps:               Extract at this frame rate (None = all frames).
        interval_ms:       Extract every N milliseconds (overrides fps).
        output_format:     'png' or 'jpeg'.
        jpeg_quality:      JPEG quality 1-100.
        progress_callback: Optional callable(current, total) for progress.

    Returns:
        dict with extraction results + zip_path.
    """
    import tempfile

    tmp_dir = tempfile.mkdtemp(prefix="nexus_frames_")
    try:
        result = extract_frames(
            video_path, tmp_dir,
            fps=fps, interval_ms=interval_ms,
            output_format=output_format, jpeg_quality=jpeg_quality,
            progress_callback=progress_callback,
        )

        os.makedirs(os.path.dirname(os.path.abspath(zip_path)), exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname in sorted(os.listdir(tmp_dir)):
                fpath = os.path.join(tmp_dir, fname)
                if os.path.isfile(fpath):
                    zf.write(fpath, fname)

        result["zip_path"] = zip_path
        logger.info("ZIP created: %s", zip_path)
        return result

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def estimate_frames(video_path, fps=None, interval_ms=None):
    """Estimate how many frames would be extracted without actually doing it."""
    info = get_video_info(video_path)
    if not info:
        return 0

    video_fps = info["fps"]
    total_frames = info["total_frames"]

    if interval_ms is not None and interval_ms > 0:
        duration_s = info["duration_s"]
        return max(1, int(duration_s / (interval_ms / 1000.0)))
    elif fps is not None and fps > 0:
        if fps >= video_fps:
            return total_frames
        return max(1, int(total_frames * fps / video_fps))
    else:
        return total_frames


def get_video_info(video_path):
    """Get video metadata without extracting frames."""
    try:
        import cv2
    except ImportError:
        return None

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None

    info = {
        "fps": cap.get(cv2.CAP_PROP_FPS),
        "total_frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
    }
    info["duration_s"] = (
        info["total_frames"] / info["fps"] if info["fps"] > 0 else 0
    )

    cap.release()
    return info


def get_video_thumbnail(video_path, size=(400, 225)):
    """Get a thumbnail from the first frame of the video as a PIL Image."""
    try:
        import cv2
        from PIL import Image
    except ImportError:
        return None

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None

    # Read the very first frame
    ret, frame = cap.read()
    cap.release()

    if not ret:
        return None

    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(frame_rgb)
    img.thumbnail(size, Image.LANCZOS)
    return img


# ── CLI entry point ──────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract frames from video")
    parser.add_argument("video", help="Path to video file")
    parser.add_argument("--output", "-o", required=True, help="Output directory")
    parser.add_argument("--fps", type=float, help="Target FPS for extraction")
    parser.add_argument(
        "--interval-ms", type=float, help="Extract every N milliseconds"
    )
    parser.add_argument(
        "--format", choices=["png", "jpeg"], default="png",
        help="Output format (default: png)",
    )
    parser.add_argument(
        "--quality", type=int, default=85,
        help="JPEG quality 1-100 (default: 85)",
    )
    parser.add_argument(
        "--zip", metavar="ZIP_PATH",
        help="Export frames to a ZIP instead of a folder",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.zip:
        result = extract_frames_to_zip(
            args.video, args.zip,
            fps=args.fps, interval_ms=args.interval_ms,
            output_format=args.format, jpeg_quality=args.quality,
        )
    else:
        result = extract_frames(
            args.video, args.output,
            fps=args.fps, interval_ms=args.interval_ms,
            output_format=args.format, jpeg_quality=args.quality,
        )

    print(f"\nExtracted {result['extracted_frames']} frames")
    print(f"Output: {result.get('zip_path', result['output_dir'])}")
