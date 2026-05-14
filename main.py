"""
AOV Tools — Main Orchestrator

Entry point that coordinates all LDPlayer instances through the 3-phase
automation workflow:
  Phase 1: Claim rewards, shop purchase, use items (all instances, parallel)
  Phase 2: Room creation (Masters) + Room join (Slaves) — group-aware
  Phase 3: Match loop ×4 with synchronized timer

Fix #1: Group-aware orchestration via instance_groups config.
Fix #3: Per-group sync primitives (room_id, toggle_signal).
Fix #5: Error boundaries around each phase.
"""

import json
import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from core.adb_controller import AdbController
from core.ldplayer_manager import LDPlayerManager
from core.image_matcher import ImageMatcher
from core.ocr_reader import OcrReader
from core.error_handler import ErrorHandler
from core.instance_worker import InstanceWorker


# ---------------------------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------------------------

def setup_logging():
    """Configure logging to both console and per-run log file."""
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"aov_run_{timestamp}.log")

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)-7s] [%(threadName)-20s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)

    # File handler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(console)
    root.addHandler(file_handler)

    return logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_config(path: str = None) -> dict:
    """Load and validate the configuration file."""
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "config.json")

    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # Validate required keys
    required = [
        "ldplayer_path", "adb_path", "instance_groups",
        "match_count", "match_timer_seconds",
    ]
    for key in required:
        if key not in config:
            raise ValueError(f"Missing required config key: '{key}'")

    if not config["instance_groups"]:
        raise ValueError("instance_groups must contain at least one group")

    return config


# ---------------------------------------------------------------------------
# Worker Factory
# ---------------------------------------------------------------------------

def build_workers(config: dict, ldm: LDPlayerManager) -> tuple:
    """
    Create InstanceWorker objects for all configured instances.

    Returns:
        Tuple of (workers_dict, group_sync_dict).
        workers_dict: {instance_index: InstanceWorker}
        group_sync_dict: {master_index: sync_dict}
    """
    workers = {}
    group_sync = {}

    for group in config["instance_groups"]:
        master_idx = group["master"]
        slave_idxs = group["slaves"]

        # Create per-group sync primitives
        sync = {
            "room_id": None,
            "room_id_ready": threading.Event(),
            "toggle_signal": threading.Event(),
        }
        group_sync[master_idx] = sync

        # Create shared components per instance
        matcher = ImageMatcher(config)
        ocr = OcrReader(config)

        # Master worker
        master_serial = ldm.get_adb_serial(master_idx)
        master_adb = AdbController(master_serial, config)
        master_handler = ErrorHandler(master_adb, matcher, config)
        workers[master_idx] = InstanceWorker(
            index=master_idx,
            role="master",
            adb=master_adb,
            handler=master_handler,
            matcher=matcher,
            ocr=ocr,
            sync=sync,
            config=config,
        )

        # Slave workers — reference the SAME sync object
        for s_idx in slave_idxs:
            s_matcher = ImageMatcher(config)
            s_ocr = OcrReader(config)
            s_serial = ldm.get_adb_serial(s_idx)
            s_adb = AdbController(s_serial, config)
            s_handler = ErrorHandler(s_adb, s_matcher, config)
            workers[s_idx] = InstanceWorker(
                index=s_idx,
                role="slave",
                adb=s_adb,
                handler=s_handler,
                matcher=s_matcher,
                ocr=s_ocr,
                sync=sync,
                config=config,
            )

    return workers, group_sync


# ---------------------------------------------------------------------------
# Phase Execution Helpers
# ---------------------------------------------------------------------------

def run_parallel(workers: dict, command: str, subset: list = None, timeout: int = 300):
    """
    Send a command to multiple workers and wait for all to complete.

    Args:
        workers: Dict of {index: InstanceWorker}.
        command: Command string to send.
        subset: Optional list of instance indexes. If None, all workers.
        timeout: Max seconds to wait for all workers.
    """
    logger = logging.getLogger(__name__)
    targets = subset or list(workers.keys())

    logger.info(f"Sending '{command}' to instances: {targets}")

    # Send commands
    for idx in targets:
        workers[idx].send_command(command)

    # Wait for all to return to idle
    for idx in targets:
        try:
            workers[idx].wait_for_status("idle", timeout=timeout)
            logger.info(f"Instance {idx}: '{command}' completed")
        except (TimeoutError, RuntimeError) as e:
            logger.error(f"Instance {idx}: '{command}' failed: {e}")


def get_masters(config: dict) -> list:
    """Get list of master instance indexes."""
    return [g["master"] for g in config["instance_groups"]]


def get_slaves(config: dict) -> list:
    """Get list of all slave instance indexes."""
    slaves = []
    for g in config["instance_groups"]:
        slaves.extend(g["slaves"])
    return slaves


def get_all_indexes(config: dict) -> list:
    """Get list of all instance indexes (masters + slaves)."""
    return get_masters(config) + get_slaves(config)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_instances(config: dict, ldm: LDPlayerManager):
    """Verify all configured instances are running."""
    logger = logging.getLogger(__name__)

    for group in config["instance_groups"]:
        master = group["master"]
        if not ldm.is_running(master):
            raise RuntimeError(
                f"Master instance {master} is not running! "
                f"Please start it in LDPlayer before running this script."
            )
        logger.info(f"✓ Master instance {master} is running")

        for s in group["slaves"]:
            if not ldm.is_running(s):
                raise RuntimeError(
                    f"Slave instance {s} is not running! "
                    f"Please start it in LDPlayer before running this script."
                )
            logger.info(f"✓ Slave instance {s} is running")


# ---------------------------------------------------------------------------
# Main Orchestration
# ---------------------------------------------------------------------------

def main():
    """Main entry point — orchestrates the full automation workflow."""
    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("AOV Tools — Multi-Instance Automation Script")
    logger.info("=" * 60)

    # Load configuration
    try:
        config = load_config()
        logger.info(f"Config loaded: {len(config['instance_groups'])} group(s), "
                     f"{config['match_count']} matches")
    except Exception as e:
        logger.critical(f"Failed to load config: {e}")
        sys.exit(1)

    # Initialize LDPlayer manager
    try:
        ldm = LDPlayerManager(config)
    except FileNotFoundError as e:
        logger.critical(f"LDPlayer not found: {e}")
        sys.exit(1)

    # Validate all instances are running
    try:
        validate_instances(config, ldm)
    except RuntimeError as e:
        logger.critical(str(e))
        sys.exit(1)

    # Build workers + sync primitives
    workers, group_sync = build_workers(config, ldm)
    logger.info(f"Created {len(workers)} workers")

    # Start all worker threads
    for w in workers.values():
        w.start()

    try:
        # ============================================================
        # PHASE 1: Initialization (all instances, parallel)
        # ============================================================
        logger.info("=" * 40)
        logger.info("PHASE 1: Initialization")
        logger.info("=" * 40)

        try:
            run_parallel(workers, "RUN_PHASE1", timeout=120)
        except Exception as e:
            logger.error(f"Phase 1 had errors (non-fatal): {e}")

        # ============================================================
        # PHASE 2: Room Setup (group-aware)
        # ============================================================
        logger.info("=" * 40)
        logger.info("PHASE 2: Room Setup")
        logger.info("=" * 40)

        # Masters create rooms first
        masters = get_masters(config)
        logger.info(f"Masters creating rooms: {masters}")
        run_parallel(workers, "CREATE_ROOM", subset=masters, timeout=120)

        # Slaves join rooms
        slaves = get_slaves(config)
        logger.info(f"Slaves joining rooms: {slaves}")
        run_parallel(workers, "JOIN_ROOM", subset=slaves, timeout=120)

        # ============================================================
        # PHASE 3: Match Loop (×match_count)
        # ============================================================
        logger.info("=" * 40)
        logger.info(f"PHASE 3: Match Loop (×{config['match_count']})")
        logger.info("=" * 40)

        all_indexes = get_all_indexes(config)

        for match_num in range(1, config["match_count"] + 1):
            logger.info(f"--- Match {match_num}/{config['match_count']} ---")

            # Reset toggle signal for this match
            for sync in group_sync.values():
                sync["toggle_signal"].clear()

            # Run match on all instances
            run_parallel(
                workers,
                f"RUN_MATCH:{match_num}",
                subset=all_indexes,
                timeout=900,  # 15 min max per match
            )

            logger.info(f"Match {match_num} completed on all instances")

    except KeyboardInterrupt:
        logger.warning("Interrupted by user (Ctrl+C)")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
    finally:
        # ============================================================
        # SHUTDOWN
        # ============================================================
        logger.info("=" * 40)
        logger.info("SHUTTING DOWN")
        logger.info("=" * 40)

        for w in workers.values():
            try:
                w.stop()
            except Exception as e:
                logger.warning(f"Error stopping worker {w.index}: {e}")

        logger.info("All workers stopped. Script terminated.")


if __name__ == "__main__":
    main()
