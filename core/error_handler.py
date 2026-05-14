"""
Error Handler — Timeout recovery, popup dismissal, and retry logic.

Fix #5: All wait_for_* calls enforce timeouts. TimeoutError triggers
popup-dismiss recovery or phase restart after max retries.
"""

import logging

logger = logging.getLogger(__name__)


class ErrorHandler:
    """Handles TimeoutError and unexpected UI states with retry + popup dismiss."""

    def __init__(self, adb, image_matcher, config: dict):
        self.adb = adb
        self.matcher = image_matcher
        self.max_retries = config["recovery"]["max_retries"]
        self.popup_templates = config["recovery"]["popup_dismiss_templates"]
        self.fallback_tap = config["recovery"]["dismiss_tap_fallback"]

    def try_dismiss_popups(self) -> bool:
        """
        Scan for known popup/close-button templates and tap them.
        Falls back to tapping a generic safe coordinate.

        Returns:
            True if a popup template was matched and tapped.
        """
        try:
            screen = self.adb.screencap()
            for tmpl in self.popup_templates:
                tmpl_path = f"templates/{tmpl}"
                pos = self.matcher.find_template(screen, tmpl_path)
                if pos:
                    logger.info(f"Dismissing popup via: {tmpl}")
                    self.adb.tap(*pos)
                    return True
        except Exception as e:
            logger.warning(f"Error during popup scan: {e}")

        # Fallback: tap neutral area
        logger.warning("No popup template matched — fallback tap")
        self.adb.tap(self.fallback_tap["x"], self.fallback_tap["y"])
        return False

    def with_retry(self, action_fn, action_name: str, max_retries: int = None):
        """
        Wrap an action with retry + popup-dismiss logic.

        On TimeoutError:
          1. Try to dismiss any popup
          2. Retry the action
          3. After max_retries, raise to caller

        Args:
            action_fn: Callable to execute.
            action_name: Human-readable name for logging.
            max_retries: Override default max retries.

        Returns:
            Whatever action_fn returns on success.

        Raises:
            TimeoutError: After all retries exhausted.
        """
        retries = max_retries or self.max_retries
        for attempt in range(1, retries + 1):
            try:
                return action_fn()
            except TimeoutError as e:
                logger.warning(
                    f"[{action_name}] Timeout attempt {attempt}/{retries}: {e}"
                )
                self.try_dismiss_popups()
                if attempt == retries:
                    logger.error(f"[{action_name}] All {retries} retries exhausted")
                    raise
            except Exception as e:
                logger.error(f"[{action_name}] Unexpected error: {e}")
                if attempt == retries:
                    raise
