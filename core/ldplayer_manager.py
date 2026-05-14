"""
LDPlayer Manager — Wraps ldconsole.exe for instance lifecycle management.

Provides discovery, launch, quit, and ADB serial resolution for LDPlayer instances.
"""

import logging
import os
import subprocess
import time

logger = logging.getLogger(__name__)


class LDPlayerManager:
    """Manages LDPlayer emulator instances via ldconsole.exe."""

    def __init__(self, config: dict):
        """
        Args:
            config: Global configuration dict containing 'ldplayer_path'.
        """
        self.ldplayer_path = config["ldplayer_path"]
        self.ldconsole_path = os.path.join(self.ldplayer_path, "ldconsole.exe")
        self.adb_path = config["adb_path"]

        if not os.path.isfile(self.ldconsole_path):
            raise FileNotFoundError(
                f"ldconsole.exe not found at: {self.ldconsole_path}"
            )
        logger.info(f"LDPlayerManager initialized: {self.ldconsole_path}")

    def _run_ldconsole(self, args: list, timeout: int = 30) -> str:
        """
        Execute an ldconsole command and return stdout.

        Args:
            args: Command arguments (without ldconsole.exe prefix).
            timeout: Maximum seconds to wait.

        Returns:
            Command stdout as decoded string.
        """
        cmd = [self.ldconsole_path] + args
        logger.debug(f"Running ldconsole: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
        )
        return result.stdout.decode("utf-8", errors="replace").strip()

    def list_instances(self) -> list:
        """
        List all LDPlayer instances using `list2`.

        Returns:
            List of dicts with keys: index, name, running, pid, adb_port.
            Each dict represents one emulator instance.

        Format of list2 output (tab-separated):
            index, name, top_window_handle, bind_handle, running,
            pid, vbox_pid, ...
        """
        output = self._run_ldconsole(["list2"])
        instances = []

        if not output:
            logger.warning("ldconsole list2 returned empty output")
            return instances

        for line in output.splitlines():
            parts = line.split(",")
            if len(parts) < 6:
                continue

            try:
                index = int(parts[0])
                name = parts[1]
                running = parts[4].strip() == "1"
                pid = int(parts[5]) if parts[5].strip() else 0

                instances.append({
                    "index": index,
                    "name": name,
                    "running": running,
                    "pid": pid,
                })
            except (ValueError, IndexError) as e:
                logger.warning(f"Failed to parse instance line: {line} — {e}")
                continue

        logger.info(f"Discovered {len(instances)} LDPlayer instances")
        return instances

    def launch(self, index: int, wait_boot: bool = True, boot_timeout: int = 60):
        """
        Launch an LDPlayer instance by index.

        Args:
            index: Instance index (0-based).
            wait_boot: If True, wait until instance is fully booted.
            boot_timeout: Max seconds to wait for boot.
        """
        logger.info(f"Launching LDPlayer instance {index}")
        self._run_ldconsole(["launch", "--index", str(index)])

        if wait_boot:
            self._wait_for_boot(index, boot_timeout)

    def _wait_for_boot(self, index: int, timeout: int = 60):
        """
        Wait until an instance is running and ADB-accessible.

        Args:
            index: Instance index.
            timeout: Max seconds to wait.

        Raises:
            TimeoutError: If instance doesn't become available.
        """
        start = time.time()
        while time.time() - start < timeout:
            if self.is_running(index):
                serial = self.get_adb_serial(index)
                if serial:
                    logger.info(
                        f"Instance {index} booted — ADB serial: {serial}"
                    )
                    return
            time.sleep(2)
        raise TimeoutError(
            f"Instance {index} did not boot within {timeout}s"
        )

    def quit(self, index: int):
        """
        Quit/close an LDPlayer instance by index.

        Args:
            index: Instance index.
        """
        logger.info(f"Quitting LDPlayer instance {index}")
        self._run_ldconsole(["quit", "--index", str(index)])

    def quit_all(self):
        """Quit all running LDPlayer instances."""
        logger.info("Quitting all LDPlayer instances")
        self._run_ldconsole(["quitall"])

    def is_running(self, index: int) -> bool:
        """
        Check if an instance is currently running.

        Args:
            index: Instance index.

        Returns:
            True if running, False otherwise.
        """
        output = self._run_ldconsole(["isrunning", "--index", str(index)])
        return "running" in output.lower()

    def run_app(self, index: int, package: str):
        """
        Launch an app within an LDPlayer instance.

        Args:
            index: Instance index.
            package: Android package name.
        """
        logger.info(f"Instance {index}: launching app {package}")
        self._run_ldconsole(
            ["runapp", "--index", str(index), "--packagename", package]
        )
        time.sleep(3)

    def kill_app(self, index: int, package: str):
        """
        Kill an app within an LDPlayer instance.

        Args:
            index: Instance index.
            package: Android package name.
        """
        logger.info(f"Instance {index}: killing app {package}")
        self._run_ldconsole(
            ["killapp", "--index", str(index), "--packagename", package]
        )

    def get_adb_serial(self, index: int) -> str:
        """
        Get the ADB serial address for a specific LDPlayer instance.

        LDPlayer assigns ADB ports starting at 5555 for index 0,
        incrementing by 2 for each subsequent instance:
            Index 0 → 127.0.0.1:5555
            Index 1 → 127.0.0.1:5557
            Index 2 → 127.0.0.1:5559
            ...

        Args:
            index: Instance index.

        Returns:
            ADB serial string (e.g. '127.0.0.1:5555').
        """
        port = 5555 + (index * 2)
        serial = f"127.0.0.1:{port}"
        logger.debug(f"Instance {index} → ADB serial: {serial}")
        return serial

    def get_all_running(self) -> list:
        """
        Get a list of all currently running instance indexes.

        Returns:
            List of integer indexes of running instances.
        """
        instances = self.list_instances()
        running = [inst["index"] for inst in instances if inst["running"]]
        logger.info(f"Running instances: {running}")
        return running

    def __repr__(self):
        return f"LDPlayerManager(path='{self.ldplayer_path}')"
