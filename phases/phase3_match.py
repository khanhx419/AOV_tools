"""
Phase 3 — Match Loop: Hero Select → Synced Timer → Feature Toggle → Match End.

Fix #3: Master owns toggle_signal Event, sleeps 180s then .set(). Slaves .wait().
Fix #4: Poll interval enforced at minimum 1.0s.
Fix #5: All waits use timeouts + retry via ErrorHandler.
"""

import logging
import time

logger = logging.getLogger(__name__)

TEMPLATES = {
    "hero_select": "templates/hero_select.png",
    "ready_btn": "templates/ready_btn.png",
    "battlefield": "templates/battlefield.png",
    "feature_icon": "templates/feature_icon.png",
    "feature_toggle_on": "templates/feature_toggle_on.png",
    "feature_toggle_off": "templates/feature_toggle_off.png",
    "victory": "templates/victory.png",
    "defeat": "templates/defeat.png",
    "continue_btn": "templates/continue_btn.png",
    "play_again": "templates/play_again.png",
    "exit_room": "templates/exit_room.png",
    "match_result": "templates/match_result.png",
}


def run_phase3_match(worker, match_num: int):
    """
    Execute one match iteration within the 4-match loop.

    Steps:
        1. Hero Selection + Ready
        2. Wait for battlefield (match load)
        3. Synchronized timer + feature toggle (Fix #3)
        4. Wait for match end
        5. Dismiss results + loop or exit

    Args:
        worker: InstanceWorker instance.
        match_num: Current match number (1-4).
    """
    idx = worker.index
    role = worker.role
    adb = worker.adb
    handler = worker.handler
    matcher = worker.matcher
    sync = worker.sync
    config = worker.config
    timeouts = config["timeouts"]

    logger.info(f"[{role.upper()} {idx}] === MATCH {match_num}/{config['match_count']} ===")

    # --- Step 1: Hero Selection ---
    _hero_select(worker, timeouts)

    # --- Step 2: Wait for Match Load ---
    _wait_for_battlefield(worker, timeouts)

    # --- Step 3: Synchronized Timer + Feature Toggle ---
    _synced_feature_toggle(worker)

    # --- Step 4: Wait for Match End ---
    _wait_for_match_end(worker, timeouts)

    # --- Step 5: Dismiss Results + Loop Control ---
    _dismiss_results(worker, timeouts)

    if match_num < config["match_count"]:
        _play_again(worker, timeouts)
    else:
        _exit_room(worker, timeouts)

    logger.info(f"[{role.upper()} {idx}] Match {match_num} complete")


def _hero_select(worker, timeouts):
    """Select hero and press ready."""
    idx = worker.index
    adb = worker.adb
    handler = worker.handler
    matcher = worker.matcher

    logger.info(f"[Instance {idx}] Step 1: Hero selection")

    # Tap hero selection
    def _find_hero():
        return matcher.wait_for_template(
            adb, TEMPLATES["hero_select"],
            timeout=timeouts["hero_select"]
        )

    try:
        pos = handler.with_retry(_find_hero, f"Instance {idx} — Hero Select")
        adb.tap(*pos)
        time.sleep(1.0)
    except TimeoutError:
        logger.warning(f"[Instance {idx}] Hero select not found, may be auto-selected")

    # Tap ready button
    def _find_ready():
        return matcher.wait_for_template(
            adb, TEMPLATES["ready_btn"],
            timeout=timeouts["ready_button"]
        )

    pos = handler.with_retry(_find_ready, f"Instance {idx} — Ready")
    adb.tap(*pos)
    time.sleep(1.0)
    logger.info(f"[Instance {idx}] Ready confirmed")


def _wait_for_battlefield(worker, timeouts):
    """Wait for the match to load (battlefield indicator appears)."""
    idx = worker.index
    adb = worker.adb
    handler = worker.handler
    matcher = worker.matcher

    logger.info(f"[Instance {idx}] Step 2: Waiting for battlefield")

    def _detect_battlefield():
        return matcher.wait_for_template(
            adb, TEMPLATES["battlefield"],
            timeout=timeouts["match_load"]
        )

    handler.with_retry(_detect_battlefield, f"Instance {idx} — Battlefield Load")
    logger.info(f"[Instance {idx}] Battlefield detected — match started")


def _synced_feature_toggle(worker):
    """
    Synchronized feature toggle at T=180s.

    Fix #3: Master sleeps 180s then sets toggle_signal.
    Slaves wait on toggle_signal.
    """
    idx = worker.index
    role = worker.role
    adb = worker.adb
    handler = worker.handler
    matcher = worker.matcher
    sync = worker.sync
    config = worker.config
    timer_seconds = config["match_timer_seconds"]
    toggle_wait = config["feature_toggle_wait"]

    if worker.is_master:
        # Master: sleep for match_timer_seconds, then signal
        logger.info(
            f"[Master {idx}] Step 3: Timer started — "
            f"waiting {timer_seconds}s before toggle"
        )
        time.sleep(timer_seconds)

        # Signal all slaves in this group
        sync["toggle_signal"].set()
        logger.info(f"[Master {idx}] Toggle signal sent to slaves")

        # Execute own feature toggle
        _execute_feature_toggle(worker, toggle_wait)

    else:
        # Slave: wait for master's signal
        logger.info(f"[Slave {idx}] Step 3: Waiting for toggle signal from Master")
        got_signal = sync["toggle_signal"].wait(timeout=timer_seconds + 60)
        if not got_signal:
            logger.error(f"[Slave {idx}] Toggle signal timeout!")
            return

        logger.info(f"[Slave {idx}] Toggle signal received")
        _execute_feature_toggle(worker, toggle_wait)


def _execute_feature_toggle(worker, toggle_wait: int):
    """
    Execute the feature toggle sequence:
        a. Find feature icon → tap
        b. Toggle ON
        c. Wait toggle_wait seconds
        d. Toggle OFF, close menu
    """
    idx = worker.index
    adb = worker.adb
    matcher = worker.matcher

    logger.info(f"[Instance {idx}] Executing feature toggle sequence")

    # Find and tap feature icon
    try:
        screen = adb.screencap()
        pos = matcher.find_template(screen, TEMPLATES["feature_icon"])
        if pos:
            adb.tap(*pos)
            time.sleep(0.5)
        else:
            logger.warning(f"[Instance {idx}] Feature icon not found")
            return
    except Exception as e:
        logger.error(f"[Instance {idx}] Feature icon error: {e}")
        return

    # Toggle ON — check current state
    try:
        screen = adb.screencap()
        is_off = matcher.find_template(screen, TEMPLATES["feature_toggle_off"])
        if is_off:
            adb.tap(*is_off)
            logger.info(f"[Instance {idx}] Feature toggled ON")
        else:
            # Already on or different state
            on_pos = matcher.find_template(screen, TEMPLATES["feature_toggle_on"])
            if on_pos:
                logger.info(f"[Instance {idx}] Feature already ON")
            else:
                logger.warning(f"[Instance {idx}] Toggle state unclear")
    except Exception as e:
        logger.error(f"[Instance {idx}] Toggle ON error: {e}")

    # Wait
    logger.info(f"[Instance {idx}] Waiting {toggle_wait}s with feature ON")
    time.sleep(toggle_wait)

    # Toggle OFF
    try:
        screen = adb.screencap()
        on_pos = matcher.find_template(screen, TEMPLATES["feature_toggle_on"])
        if on_pos:
            adb.tap(*on_pos)
            logger.info(f"[Instance {idx}] Feature toggled OFF")
    except Exception as e:
        logger.error(f"[Instance {idx}] Toggle OFF error: {e}")

    # Close menu
    adb.press_back()
    time.sleep(0.5)
    logger.info(f"[Instance {idx}] Feature toggle sequence complete")


def _wait_for_match_end(worker, timeouts):
    """Wait for victory/defeat screen."""
    idx = worker.index
    adb = worker.adb
    handler = worker.handler
    matcher = worker.matcher

    logger.info(f"[Instance {idx}] Step 4: Waiting for match end")

    def _detect_end():
        return matcher.wait_for_any_template(
            adb,
            [TEMPLATES["victory"], TEMPLATES["defeat"], TEMPLATES["match_result"]],
            timeout=timeouts["match_end"]
        )

    result = handler.with_retry(_detect_end, f"Instance {idx} — Match End")
    template_matched = result[0]
    logger.info(f"[Instance {idx}] Match ended — detected: {template_matched}")


def _dismiss_results(worker, timeouts):
    """Tap through post-match result screens."""
    idx = worker.index
    adb = worker.adb
    matcher = worker.matcher

    logger.info(f"[Instance {idx}] Step 5: Dismissing results")

    # Tap continue/skip buttons multiple times to clear all result screens
    for attempt in range(5):
        time.sleep(1.5)
        screen = adb.screencap()

        pos = matcher.find_template(screen, TEMPLATES["continue_btn"])
        if pos:
            adb.tap(*pos)
            logger.debug(f"[Instance {idx}] Tapped continue ({attempt + 1})")
            continue

        # Check if we're back to lobby/room
        pos = matcher.find_template(screen, TEMPLATES["play_again"])
        if pos:
            logger.info(f"[Instance {idx}] Results dismissed — at play again")
            return

        # Fallback: tap center-bottom area to skip
        adb.tap(640, 600)

    logger.info(f"[Instance {idx}] Results dismissal complete")


def _play_again(worker, timeouts):
    """Tap 'Play Again' to start the next match in the loop."""
    idx = worker.index
    adb = worker.adb
    handler = worker.handler
    matcher = worker.matcher

    logger.info(f"[Instance {idx}] Tapping Play Again")

    def _find_play_again():
        return matcher.wait_for_template(
            adb, TEMPLATES["play_again"],
            timeout=timeouts["default"]
        )

    try:
        pos = handler.with_retry(
            _find_play_again, f"Instance {idx} — Play Again"
        )
        adb.tap(*pos)
        time.sleep(2.0)
    except TimeoutError:
        logger.warning(f"[Instance {idx}] Play Again not found")


def _exit_room(worker, timeouts):
    """Exit the room after the final match."""
    idx = worker.index
    adb = worker.adb
    matcher = worker.matcher

    logger.info(f"[Instance {idx}] Exiting room (final match)")

    try:
        screen = adb.screencap()
        pos = matcher.find_template(screen, TEMPLATES["exit_room"])
        if pos:
            adb.tap(*pos)
            time.sleep(1.5)
            return
    except Exception:
        pass

    # Fallback: press back multiple times
    for _ in range(3):
        adb.press_back()
        time.sleep(1.0)

    logger.info(f"[Instance {idx}] Room exit complete")
