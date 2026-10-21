"""Estimate magnet-disc or stir-bar speed from a brightness marker in video.

A white sector passes a fixed region of interest (ROI) once per turn.
A linear fit of rising-edge times returns rpm; video FPS must be calibrated.
This does NOT measure the vortex surface and does not detect every alias.
"""
from __future__ import annotations

import argparse
import sys

import numpy as np


def crossing_times(signal, fps, level=None):
    samples = np.asarray(signal, dtype=float)
    if len(samples) < 5 or fps <= 0:
        raise ValueError("not enough video frames, or invalid FPS")
    if level is None:
        lo, hi = np.percentile(samples, [5, 95])
        if hi - lo < 1e-8:
            raise ValueError("insufficient contrast; adjust lighting or ROI")
        level = (lo + hi) / 2
    indices = np.flatnonzero((samples[:-1] < level) & (samples[1:] >= level))
    fractions = ((level - samples[indices]) /
                 (samples[indices + 1] - samples[indices]))
    return (indices + fractions) / fps


def rate_from_crossings(crossings):
    t = np.asarray(crossings, dtype=float)
    if len(t) < 3 or np.any(np.diff(t) <= 0):
        raise ValueError("need >=3 consistently ordered crossings")
    count = np.arange(len(t))
    # Fit count = a*time + b: a equals revolutions per second.
    (slope, offset), covariance = np.polyfit(t, count, 1, cov=True)
    if slope <= 0:
        raise ValueError("invalid video period")
    residual_s = (count - (slope * t + offset)) / slope
    rpm = 60 * slope
    error_rpm = 60 * np.sqrt(covariance[0, 0])
    return rpm, error_rpm, float(np.max(np.abs(residual_s)))


def video_brightness(video, roi, start=0, stop=None):
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("pip install -e '.[video]' for OpenCV") from exc
    x, y, width, height = roi
    if min(x, y) < 0 or min(width, height) <= 0:
        raise ValueError("ROI must be inside the frame with positive dimensions")
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise OSError("could not open video: " + video)
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            raise ValueError("video has no valid FPS metadata; choose another file")
        frame_width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        frame_height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        if x + width > frame_width or y + height > frame_height:
            raise ValueError("ROI extends outside video frame")
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(start * fps))
        readings = []
        while True:
            if stop is not None and len(readings) >= (stop - start) * fps:
                break
            available, frame = cap.read()
            if not available:
                break
            readings.append(float(frame[y:y + height, x:x + width].mean()))
        return np.asarray(readings), fps
    finally:
        cap.release()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Estimate disc rpm from a black/white sector")
    parser.add_argument("video")
    parser.add_argument("--roi", type=int, nargs=4, required=True,
                        metavar=("X", "Y", "W", "H"))
    parser.add_argument("--fps", type=float, help="measured video FPS (override file metadata)")
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--stop", type=float)
    args = parser.parse_args(argv)
    try:
        if args.start < 0 or (args.stop is not None and args.stop <= args.start):
            raise ValueError("invalid video time interval")
        signal, fps_file = video_brightness(args.video, args.roi, args.start, args.stop)
        fps = args.fps if args.fps is not None else fps_file
        crossings = crossing_times(signal, fps)
        rpm, error, max_resid = rate_from_crossings(crossings)
        print("FPS used: %.4f; frames: %d; counted turns: %d" %
              (fps, len(signal), len(crossings) - 1))
        print("observed rotation: %.3f +/- %.3f rpm; max timing residual %.3f ms" %
              (rpm, error, max_resid * 1000))
        if fps * 60 / rpm < 2.5:
            print("WARNING: fewer than 2.5 frames/revolution; alias risk.", file=sys.stderr)
        return 0
    except (ValueError, OSError, RuntimeError) as ex:
        print("ERROR:", ex, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
