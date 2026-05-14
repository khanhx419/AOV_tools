"""
Image Matcher — OpenCV template matching engine with polling support.

Uses cv2.matchTemplate with TM_CCOEFF_NORMED for UI element detection.
Enforces a minimum 1.0s poll interval to prevent ADB overload (Fix #4).
"""

import logging
import os
import time

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


class ImageMatcher:
    """OpenCV-based template matching for game UI navigation."""

    def __init__(self, config: dict):
        self.confidence = config.get("template_confidence", 0.8)
        self.poll_interval = config.get("poll_interval_seconds", 1.0)
        self._template_cache = {}

    def _load_template(self, template_path: str) -> np.ndarray:
        """Load and cache a template image from disk."""
        if template_path in self._template_cache:
            return self._template_cache[template_path]
        if not os.path.isfile(template_path):
            raise FileNotFoundError(f"Template not found: {template_path}")
        template = cv2.imread(template_path, cv2.IMREAD_COLOR)
        if template is None:
            raise ValueError(f"Failed to read template: {template_path}")
        self._template_cache[template_path] = template
        return template

    @staticmethod
    def _pil_to_cv2(pil_image: Image.Image) -> np.ndarray:
        """Convert PIL Image (RGB) to OpenCV array (BGR)."""
        return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

    def find_template(self, screen_img, template_path, confidence=None):
        """Find a template in screen. Returns (cx, cy) or None."""
        confidence = confidence or self.confidence
        screen_cv = self._pil_to_cv2(screen_img)
        template = self._load_template(template_path)
        if (screen_cv.shape[0] < template.shape[0] or
                screen_cv.shape[1] < template.shape[1]):
            return None
        result = cv2.matchTemplate(screen_cv, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val >= confidence:
            h, w = template.shape[:2]
            return (max_loc[0] + w // 2, max_loc[1] + h // 2)
        return None

    def find_all_templates(self, screen_img, template_path, confidence=None, min_distance=20):
        """Find all occurrences of a template. Returns list of (cx, cy)."""
        confidence = confidence or self.confidence
        screen_cv = self._pil_to_cv2(screen_img)
        template = self._load_template(template_path)
        if (screen_cv.shape[0] < template.shape[0] or
                screen_cv.shape[1] < template.shape[1]):
            return []
        result = cv2.matchTemplate(screen_cv, template, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= confidence)
        h, w = template.shape[:2]
        matches = []
        for pt in zip(*locations[::-1]):
            cx, cy = pt[0] + w // 2, pt[1] + h // 2
            if not any(abs(cx - ex) + abs(cy - ey) < min_distance for ex, ey in matches):
                matches.append((cx, cy))
        return matches

    def wait_for_template(self, adb, template_path, timeout=30, interval=None, confidence=None):
        """Poll screen until template found or timeout. Raises TimeoutError."""
        interval = max(interval or self.poll_interval, 1.0)
        start = time.time()
        logger.info(f"Waiting for: {os.path.basename(template_path)} (timeout={timeout}s)")
        while time.time() - start < timeout:
            try:
                screen = adb.screencap()
                result = self.find_template(screen, template_path, confidence)
                if result is not None:
                    logger.info(f"Found: {os.path.basename(template_path)} at {result}")
                    return result
            except Exception as e:
                logger.warning(f"Screencap error during wait: {e}")
            time.sleep(interval)
        raise TimeoutError(f"'{os.path.basename(template_path)}' not found within {timeout}s")

    def wait_for_any_template(self, adb, template_paths, timeout=30, interval=None, confidence=None):
        """Poll until any template matches. Returns (path, (cx, cy))."""
        interval = max(interval or self.poll_interval, 1.0)
        start = time.time()
        while time.time() - start < timeout:
            try:
                screen = adb.screencap()
                for p in template_paths:
                    result = self.find_template(screen, p, confidence)
                    if result is not None:
                        return (p, result)
            except Exception as e:
                logger.warning(f"Screencap error: {e}")
            time.sleep(interval)
        raise TimeoutError(f"None of templates found within {timeout}s")

    def is_template_visible(self, adb, template_path, confidence=None):
        """Quick check if template is currently on screen."""
        try:
            screen = adb.screencap()
            return self.find_template(screen, template_path, confidence) is not None
        except Exception:
            return False

    def clear_cache(self):
        """Clear the template image cache."""
        self._template_cache.clear()
