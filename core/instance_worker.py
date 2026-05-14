"""
Instance Worker — Per-instance thread worker for Master/Slave coordination.

Fix #3: Master workers own a threading.Event (toggle_signal) that they .set()
at T=180s. Slave workers .wait() on the same event for synchronized execution.
"""

import logging
import queue
import threading

logger = logging.getLogger(__name__)


class InstanceWorker:
    """Thread worker managing one emulator instance through all phases."""

    def __init__(self, index: int, role: str, adb, handler, matcher, ocr, sync: dict, config: dict):
        """
        Args:
            index: LDPlayer instance index.
            role: 'master' or 'slave'.
            adb: AdbController for this instance.
            handler: ErrorHandler for this instance.
            matcher: ImageMatcher (shared config, per-instance screencap via adb).
            ocr: OcrReader for Room ID extraction.
            sync: Shared sync dict for the group containing:
                  - 'room_id': str or None
                  - 'room_id_ready': threading.Event
                  - 'toggle_signal': threading.Event
            config: Global config dict.
        """
        self.index = index
        self.role = role
        self.adb = adb
        self.handler = handler
        self.matcher = matcher
        self.ocr = ocr
        self.sync = sync
        self.config = config
        self.match_count = config["match_count"]
        self.command_queue = queue.Queue()
        self.status = "idle"
        self._thread = None
        self._stop_event = threading.Event()

        logger.info(
            f"Worker created: Instance {index} ({role})"
        )

    @property
    def is_master(self) -> bool:
        return self.role == "master"

    @property
    def is_slave(self) -> bool:
        return self.role == "slave"

    def start(self):
        """Start the worker thread."""
        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"worker-{self.index}-{self.role}",
            daemon=True,
        )
        self._thread.start()
        logger.info(f"Worker {self.index} ({self.role}) thread started")

    def stop(self):
        """Signal the worker to stop."""
        self._stop_event.set()
        self.command_queue.put("STOP")
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        self.status = "stopped"
        logger.info(f"Worker {self.index} ({self.role}) stopped")

    def send_command(self, command: str):
        """Enqueue a command for this worker."""
        logger.debug(f"Worker {self.index}: enqueuing command '{command}'")
        self.command_queue.put(command)

    def _run_loop(self):
        """Main thread loop — processes commands from the queue."""
        while not self._stop_event.is_set():
            try:
                command = self.command_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if command == "STOP":
                break

            self.status = f"executing:{command}"
            logger.info(f"Worker {self.index}: executing '{command}'")

            try:
                self._dispatch(command)
                self.status = "idle"
            except Exception as e:
                logger.error(
                    f"Worker {self.index}: command '{command}' failed: {e}"
                )
                self.status = f"error:{command}"

    def _dispatch(self, command: str):
        """Route a command string to the appropriate phase handler."""
        # Import phases here to avoid circular imports
        from phases.phase1_init import run_phase1
        from phases.phase2_room import run_phase2_create_room, run_phase2_join_room
        from phases.phase3_match import run_phase3_match

        if command == "RUN_PHASE1":
            run_phase1(self)

        elif command == "CREATE_ROOM":
            run_phase2_create_room(self)

        elif command.startswith("JOIN_ROOM"):
            run_phase2_join_room(self)

        elif command.startswith("RUN_MATCH:"):
            match_num = int(command.split(":")[1])
            run_phase3_match(self, match_num)

        else:
            logger.warning(f"Worker {self.index}: unknown command '{command}'")

    def wait_for_status(self, target: str, timeout: int = 300):
        """
        Block until worker reaches target status or timeout.

        Args:
            target: Status string to wait for (e.g. 'idle').
            timeout: Max seconds to wait.

        Raises:
            TimeoutError: If status not reached in time.
        """
        import time
        start = time.time()
        while time.time() - start < timeout:
            if self.status == target or self.status.startswith(target):
                return
            if self.status.startswith("error"):
                raise RuntimeError(
                    f"Worker {self.index} in error state: {self.status}"
                )
            time.sleep(0.5)
        raise TimeoutError(
            f"Worker {self.index} did not reach '{target}' within {timeout}s"
        )

    def __repr__(self):
        return (
            f"InstanceWorker(index={self.index}, role='{self.role}', "
            f"status='{self.status}')"
        )
