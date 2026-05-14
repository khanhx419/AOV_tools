"""
ADB Controller — Wraps ADB commands for a specific LDPlayer instance.

Each instance is addressed by its ADB serial (e.g. '127.0.0.1:5555').
Provides screen capture, tap, swipe, text input, and key event operations.

Fix #3 (QoL): Added AdbController.start_server(adb_path) class method that
runs 'adb start-server' once at startup so the ADB bridge is guaranteed to
be active before any worker attempts a connection.
"""

import io
import logging
import subprocess
import time

from PIL import Image

logger = logging.getLogger(__name__)


class AdbController:
    """Manages ADB interactions with a single emulator instance."""

    # -----------------------------------------------------------------------
    # Class-level helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def start_server(adb_path: str):
        """
        Start the ADB server daemon.

        Should be called ONCE at application start, before any AdbController
        instances are constructed, to ensure the ADB bridge is active.

        Args:
            adb_path: Absolute path to the adb executable (from config).
        """
        _log = logging.getLogger(__name__)
        try:
            result = subprocess.run(
                [adb_path, "start-server"],
                capture_output=True,
                timeout=15,
            )
            stdout = result.stdout.decode("utf-8", errors="replace").strip()
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            if result.returncode == 0:
                _log.info(f"ADB server started successfully. {stdout or '(no output)'}")
            else:
                _log.warning(
                    f"adb start-server returned non-zero exit code "
                    f"{result.returncode}: {stderr}"
                )
        except FileNotFoundError:
            _log.critical(
                f"adb executable not found at '{adb_path}'. "
                "Please verify 'adb_path' in config.json."
            )
            raise
        except subprocess.TimeoutExpired:
            _log.error("adb start-server timed out after 15 seconds.")
            raise

    # -----------------------------------------------------------------------
    # Instance lifecycle
    # -----------------------------------------------------------------------

    def __init__(self, serial: str, config: dict):
        """
        Args:
            serial: ADB device serial (e.g. '127.0.0.1:5555').
            config: Global configuration dict containing 'adb_path'.
        """
        self.serial = serial
        self.adb_path = config["adb_path"]
        self._connect()

    def _connect(self):
        """Ensure the ADB connection to this device is established."""
        try:
            result = self._run_adb_command(["connect", self.serial])
            logger.info(f"[{self.serial}] ADB connect: {result.strip()}")
        except subprocess.SubprocessError as e:
            logger.error(f"[{self.serial}] ADB connect failed: {e}")
            raise

    def _run_adb_command(self, args: list, timeout: int = 30) -> str:
        """
        Execute an ADB command and return stdout as a string.

        Args:
            args: ADB command arguments (without 'adb' prefix or serial).
            timeout: Maximum seconds to wait for command completion.

        Returns:
            Command stdout as a decoded string.

        Raises:
            subprocess.SubprocessError: If the command fails.
        """
        cmd = [self.adb_path, "-s", self.serial] + args
        logger.debug(f"[{self.serial}] Running: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            logger.warning(f"[{self.serial}] ADB stderr: {stderr}")
        return result.stdout.decode("utf-8", errors="replace")

    def _run_adb_command_raw(self, args: list, timeout: int = 30) -> bytes:
        """
        Execute an ADB command and return raw stdout bytes (for screencap).

        Args:
            args: ADB command arguments.
            timeout: Maximum seconds to wait.

        Returns:
            Raw bytes from stdout.
        """
        cmd = [self.adb_path, "-s", self.serial] + args
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            raise subprocess.SubprocessError(
                f"ADB command failed on {self.serial}: {stderr}"
            )
        return result.stdout

    def screencap(self) -> Image.Image:
        """
        Capture the current screen of the emulator instance.

        Returns:
            PIL.Image.Image in RGB mode.

        Raises:
            subprocess.SubprocessError: If screencap fails.
            ValueError: If the image data is invalid.
        """
        raw_data = self._run_adb_command_raw(
            ["exec-out", "screencap", "-p"], timeout=10
        )
        if not raw_data:
            raise ValueError(f"[{self.serial}] Empty screencap data")

        try:
            image = Image.open(io.BytesIO(raw_data))
            return image.convert("RGB")
        except Exception as e:
            raise ValueError(
                f"[{self.serial}] Failed to decode screencap: {e}"
            )

    def tap(self, x: int, y: int):
        """
        Send a tap event at the given screen coordinates.

        Args:
            x: Horizontal pixel coordinate.
            y: Vertical pixel coordinate.
        """
        logger.debug(f"[{self.serial}] Tap ({x}, {y})")
        self._run_adb_command(
            ["shell", "input", "tap", str(x), str(y)]
        )
        # Brief delay to let the UI respond
        time.sleep(0.3)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300):
        """
        Send a swipe gesture from (x1, y1) to (x2, y2).

        Args:
            x1, y1: Start coordinates.
            x2, y2: End coordinates.
            duration_ms: Swipe duration in milliseconds.
        """
        logger.debug(
            f"[{self.serial}] Swipe ({x1},{y1}) -> ({x2},{y2}) in {duration_ms}ms"
        )
        self._run_adb_command(
            [
                "shell", "input", "swipe",
                str(x1), str(y1), str(x2), str(y2), str(duration_ms),
            ]
        )
        time.sleep(0.3)

    def input_text(self, text: str):
        """
        Type text into the currently focused input field.

        Args:
            text: The text string to input (ASCII characters only for ADB).
        """
        logger.debug(f"[{self.serial}] Input text: '{text}'")
        self._run_adb_command(["shell", "input", "text", text])
        time.sleep(0.2)

    def key_event(self, keycode: int):
        """
        Send a key event (e.g. KEYCODE_BACK = 4, KEYCODE_HOME = 3).

        Args:
            keycode: Android keycode integer.
        """
        logger.debug(f"[{self.serial}] Key event: {keycode}")
        self._run_adb_command(
            ["shell", "input", "keyevent", str(keycode)]
        )
        time.sleep(0.2)

    def press_back(self):
        """Send the BACK key event."""
        self.key_event(4)

    def press_home(self):
        """Send the HOME key event."""
        self.key_event(3)

    def clear_text_field(self, max_chars: int = 20):
        """
        Clear an input field by sending DEL key events.

        Args:
            max_chars: Number of DEL events to send (to ensure field is empty).
        """
        logger.debug(f"[{self.serial}] Clearing text field ({max_chars} DELs)")
        for _ in range(max_chars):
            self._run_adb_command(
                ["shell", "input", "keyevent", "67"]  # KEYCODE_DEL
            )
        time.sleep(0.2)

    def launch_app(self, package: str):
        """
        Launch an app by package name using monkey.

        Args:
            package: Android package name (e.g. 'com.garena.game.kgvn').
        """
        logger.info(f"[{self.serial}] Launching app: {package}")
        self._run_adb_command(
            [
                "shell", "monkey", "-p", package,
                "-c", "android.intent.category.LAUNCHER", "1",
            ]
        )
        time.sleep(3)

    def force_stop_app(self, package: str):
        """
        Force stop an app by package name.

        Args:
            package: Android package name.
        """
        logger.info(f"[{self.serial}] Force stopping: {package}")
        self._run_adb_command(["shell", "am", "force-stop", package])
        time.sleep(1)

    def is_screen_on(self) -> bool:
        """Check if the emulator screen is currently on."""
        result = self._run_adb_command(
            ["shell", "dumpsys", "power"]
        )
        return "mHoldingDisplaySuspendBlocker=true" in result

    def __repr__(self):
        return f"AdbController(serial='{self.serial}')"
