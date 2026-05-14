"""
OCR Reader — Tesseract OCR with preprocessing pipeline for game fonts.

Fix #2: Grayscale → Upscale → Binary threshold pipeline + digit-only whitelist
for accurate Room ID extraction from game screenshots with shadows/strokes.
"""

import logging

import cv2
import numpy as np
import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)


class OcrReader:
    """Extracts dynamic text (Room IDs) from game screenshots using Tesseract."""

    def __init__(self, config: dict):
        self.tesseract_config = config["ocr"]["tesseract_config"]
        self.preprocess_cfg = config["ocr"]["preprocessing"]
        self.room_id_region = config["ocr"]["room_id_region"]

    def preprocess_image(self, image: Image.Image) -> Image.Image:
        """
        Multi-step preprocessing for game fonts with shadows/strokes.

        Pipeline:
          1. Convert to grayscale
          2. Upscale (3x) for better glyph recognition
          3. Binary threshold to remove shadows and anti-aliasing
        """
        img = np.array(image)

        # Step 1: Grayscale
        if self.preprocess_cfg.get("grayscale", True):
            if len(img.shape) == 3:
                img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

        # Step 2: Upscale
        scale = self.preprocess_cfg.get("resize_scale", 3)
        if scale > 1:
            img = cv2.resize(img, None, fx=scale, fy=scale,
                             interpolation=cv2.INTER_CUBIC)

        # Step 3: Binary threshold
        thresh_val = self.preprocess_cfg.get("threshold_value", 150)
        thresh_max = self.preprocess_cfg.get("threshold_max", 255)
        _, img = cv2.threshold(img, thresh_val, thresh_max, cv2.THRESH_BINARY)

        return Image.fromarray(img)

    def extract_room_id(self, adb) -> str:
        """
        Capture screen → crop Room ID region → preprocess → OCR.

        Returns:
            Room ID as a numeric string (e.g. '483291').

        Raises:
            ValueError: If OCR fails or result is not purely numeric.
        """
        screen = adb.screencap()
        r = self.room_id_region
        cropped = screen.crop((r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"]))

        processed = self.preprocess_image(cropped)
        raw_text = pytesseract.image_to_string(
            processed, config=self.tesseract_config
        ).strip()

        logger.info(f"OCR raw output: '{raw_text}'")

        # Validate: must be non-empty and digits only
        if not raw_text or not raw_text.isdigit():
            raise ValueError(f"OCR failed or invalid Room ID: '{raw_text}'")

        logger.info(f"Extracted Room ID: {raw_text}")
        return raw_text

    def extract_text(self, adb, region: dict, custom_config: str = None) -> str:
        """
        Generic text extraction from a screen region.

        Args:
            adb: AdbController instance.
            region: Dict with x, y, w, h keys.
            custom_config: Optional custom Tesseract config string.

        Returns:
            Extracted text string.
        """
        screen = adb.screencap()
        cropped = screen.crop((
            region["x"], region["y"],
            region["x"] + region["w"], region["y"] + region["h"]
        ))
        processed = self.preprocess_image(cropped)
        config = custom_config or self.tesseract_config
        text = pytesseract.image_to_string(processed, config=config).strip()
        logger.debug(f"OCR text: '{text}'")
        return text
