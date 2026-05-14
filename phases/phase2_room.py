"""
Phase 2 — Room Management: Create Room (Master) + Join Room (Slave).

Fix #1: Group-aware routing — each Master creates a room, extracts Room ID
via OCR, and shares it with its bound Slaves through the sync dict.
Fix #2: OCR preprocessing pipeline for accurate Room ID extraction.
Fix #5: All waits use timeouts + retry via ErrorHandler.
"""

import logging
import time

logger = logging.getLogger(__name__)

TEMPLATES = {
    "create_room": "templates/create_room.png",
    "join_room": "templates/join_room.png",
    "room_lobby": "templates/room_lobby.png",
    "room_id_input": "templates/room_id_input.png",
    "confirm_join": "templates/confirm_join.png",
    "start_match": "templates/start_match.png",
    "custom_mode": "templates/custom_mode.png",
}


def run_phase2_create_room(worker):
    """
    Master flow: Create a custom room and extract the Room ID via OCR.

    Steps:
        1. Navigate to custom mode
        2. Find and tap 'Create Room'
        3. Wait for room lobby to load
        4. OCR extract Room ID
        5. Store Room ID in sync dict and signal Slaves

    Args:
        worker: InstanceWorker with role='master'.
    """
    idx = worker.index
    adb = worker.adb
    handler = worker.handler
    matcher = worker.matcher
    ocr = worker.ocr
    sync = worker.sync
    timeouts = worker.config["timeouts"]

    logger.info(f"[Master {idx}] === PHASE 2: Create Room ===")

    # Step 1: Navigate to custom/practice mode
    try:
        def _find_custom():
            return matcher.wait_for_template(
                adb, TEMPLATES["custom_mode"],
                timeout=timeouts["room_create"]
            )
        pos = handler.with_retry(_find_custom, f"Master {idx} — Custom Mode")
        adb.tap(*pos)
        time.sleep(1.5)
    except TimeoutError:
        logger.warning(f"[Master {idx}] Custom mode not found, trying direct create")

    # Step 2: Find and tap 'Create Room'
    def _find_create():
        return matcher.wait_for_template(
            adb, TEMPLATES["create_room"],
            timeout=timeouts["room_create"]
        )

    pos = handler.with_retry(_find_create, f"Master {idx} — Create Room")
    adb.tap(*pos)
    time.sleep(2.0)

    # Step 3: Wait for room lobby to appear
    def _wait_lobby():
        return matcher.wait_for_template(
            adb, TEMPLATES["room_lobby"],
            timeout=timeouts["room_create"]
        )

    handler.with_retry(_wait_lobby, f"Master {idx} — Room Lobby")
    time.sleep(1.0)

    # Step 4: Extract Room ID via OCR
    room_id = None
    max_ocr_retries = 3
    for attempt in range(1, max_ocr_retries + 1):
        try:
            room_id = ocr.extract_room_id(adb)
            logger.info(f"[Master {idx}] Room ID extracted: {room_id}")
            break
        except ValueError as e:
            logger.warning(
                f"[Master {idx}] OCR attempt {attempt}/{max_ocr_retries}: {e}"
            )
            time.sleep(1.0)

    if room_id is None:
        raise RuntimeError(f"[Master {idx}] Failed to extract Room ID after {max_ocr_retries} attempts")

    # Step 5: Share Room ID with Slaves via sync dict
    sync["room_id"] = room_id
    sync["room_id_ready"].set()
    logger.info(f"[Master {idx}] Room ID '{room_id}' shared with slaves")


def run_phase2_join_room(worker):
    """
    Slave flow: Wait for Master's Room ID and join the room.

    Steps:
        1. Wait for room_id_ready event from Master
        2. Read Room ID from sync dict
        3. Navigate to 'Join Room'
        4. Input Room ID
        5. Confirm and wait for lobby

    Args:
        worker: InstanceWorker with role='slave'.
    """
    idx = worker.index
    adb = worker.adb
    handler = worker.handler
    matcher = worker.matcher
    sync = worker.sync
    timeouts = worker.config["timeouts"]

    logger.info(f"[Slave {idx}] === PHASE 2: Join Room ===")

    # Step 1: Wait for Master to share Room ID
    logger.info(f"[Slave {idx}] Waiting for Room ID from Master...")
    got_id = sync["room_id_ready"].wait(timeout=60)
    if not got_id:
        raise TimeoutError(f"[Slave {idx}] Master did not provide Room ID within 60s")

    room_id = sync["room_id"]
    logger.info(f"[Slave {idx}] Received Room ID: {room_id}")

    # Step 2: Find and tap 'Join Room'
    def _find_join():
        return matcher.wait_for_template(
            adb, TEMPLATES["join_room"],
            timeout=timeouts["room_join"]
        )

    pos = handler.with_retry(_find_join, f"Slave {idx} — Join Room")
    adb.tap(*pos)
    time.sleep(1.5)

    # Step 3: Find input field and enter Room ID
    try:
        def _find_input():
            return matcher.wait_for_template(
                adb, TEMPLATES["room_id_input"],
                timeout=timeouts["room_join"]
            )
        pos = handler.with_retry(_find_input, f"Slave {idx} — Room ID Input")
        adb.tap(*pos)
        time.sleep(0.5)
    except TimeoutError:
        # Input field might auto-focus; try typing directly
        logger.warning(f"[Slave {idx}] Input field not found, attempting direct input")

    # Clear any existing text and type Room ID
    adb.clear_text_field(max_chars=10)
    adb.input_text(room_id)
    time.sleep(0.5)

    # Step 4: Confirm join
    try:
        def _find_confirm():
            return matcher.wait_for_template(
                adb, TEMPLATES["confirm_join"],
                timeout=timeouts["room_join"]
            )
        pos = handler.with_retry(_find_confirm, f"Slave {idx} — Confirm Join")
        adb.tap(*pos)
        time.sleep(2.0)
    except TimeoutError:
        # Try pressing Enter as fallback
        logger.warning(f"[Slave {idx}] Confirm button not found, pressing Enter")
        adb.key_event(66)  # KEYCODE_ENTER
        time.sleep(2.0)

    # Step 5: Wait for room lobby
    def _wait_lobby():
        return matcher.wait_for_template(
            adb, TEMPLATES["room_lobby"],
            timeout=timeouts["room_join"]
        )

    try:
        handler.with_retry(_wait_lobby, f"Slave {idx} — Room Lobby")
        logger.info(f"[Slave {idx}] Successfully joined room {room_id}")
    except TimeoutError:
        logger.error(f"[Slave {idx}] Failed to join room {room_id}")
        raise
