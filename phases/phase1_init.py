"""
Phase 1 — Initialization: Claim Rewards → Shop Purchase → Use Items.

Runs once per instance at startup. Non-fatal: if this phase fails,
the worker continues to Phase 2.

Fix #5: All waits use timeouts + retry via ErrorHandler.
"""

import logging
import time

logger = logging.getLogger(__name__)

# Template paths (relative to project root)
TEMPLATES = {
    "reward_claim": "templates/reward_claim.png",
    "shop_icon": "templates/shop_icon.png",
    "item_buy": "templates/item_buy.png",
    "item_use": "templates/item_use.png",
    "close_popup": "templates/close_popup.png",
    "main_screen": "templates/main_screen.png",
    "backpack_icon": "templates/backpack_icon.png",
}


def run_phase1(worker):
    """
    Execute Phase 1: Claim rewards, purchase shop items, use items.

    Args:
        worker: InstanceWorker with adb, handler, matcher, and config.
    """
    idx = worker.index
    adb = worker.adb
    handler = worker.handler
    matcher = worker.matcher
    config = worker.config
    timeouts = config["timeouts"]

    logger.info(f"[Instance {idx}] === PHASE 1: Initialization ===")

    # --- Step 1: Claim Rewards ---
    try:
        _claim_rewards(worker, timeouts)
    except Exception as e:
        logger.warning(f"[Instance {idx}] Reward claim failed (non-fatal): {e}")

    # --- Step 2: Shop Purchase ---
    try:
        _shop_purchase(worker, timeouts)
    except Exception as e:
        logger.warning(f"[Instance {idx}] Shop purchase failed (non-fatal): {e}")

    # --- Step 3: Use Items ---
    try:
        _use_items(worker, timeouts)
    except Exception as e:
        logger.warning(f"[Instance {idx}] Item use failed (non-fatal): {e}")

    # --- Step 4: Return to Main Screen ---
    try:
        _return_to_main(worker, timeouts)
    except Exception as e:
        logger.warning(f"[Instance {idx}] Return to main failed: {e}")

    logger.info(f"[Instance {idx}] Phase 1 complete")


def _claim_rewards(worker, timeouts):
    """Scan for and tap all reward claim buttons."""
    idx = worker.index
    adb = worker.adb
    handler = worker.handler
    matcher = worker.matcher

    logger.info(f"[Instance {idx}] Step 1: Claiming rewards")

    def _scan_and_claim():
        screen = adb.screencap()
        rewards = matcher.find_all_templates(
            screen, TEMPLATES["reward_claim"]
        )
        if not rewards:
            logger.info(f"[Instance {idx}] No rewards found to claim")
            return

        logger.info(f"[Instance {idx}] Found {len(rewards)} reward(s)")
        for i, (x, y) in enumerate(rewards):
            logger.debug(f"[Instance {idx}] Claiming reward {i + 1} at ({x}, {y})")
            adb.tap(x, y)
            time.sleep(1.0)

            # Dismiss any result popup
            try:
                handler.try_dismiss_popups()
            except Exception:
                pass

    handler.with_retry(
        _scan_and_claim,
        f"Instance {idx} — Claim Rewards",
    )


def _shop_purchase(worker, timeouts):
    """Navigate to shop and purchase configured items."""
    idx = worker.index
    adb = worker.adb
    handler = worker.handler
    matcher = worker.matcher

    logger.info(f"[Instance {idx}] Step 2: Shop purchase")

    # Find and tap shop icon
    def _open_shop():
        return matcher.wait_for_template(
            adb, TEMPLATES["shop_icon"],
            timeout=timeouts["shop_navigation"]
        )

    pos = handler.with_retry(_open_shop, f"Instance {idx} — Open Shop")
    adb.tap(*pos)
    time.sleep(1.5)

    # Find and tap buy button
    def _find_buy():
        return matcher.wait_for_template(
            adb, TEMPLATES["item_buy"],
            timeout=timeouts["shop_navigation"]
        )

    pos = handler.with_retry(_find_buy, f"Instance {idx} — Buy Item")
    adb.tap(*pos)
    time.sleep(1.0)

    # Dismiss purchase confirmation if any
    handler.try_dismiss_popups()
    time.sleep(0.5)

    # Go back from shop
    adb.press_back()
    time.sleep(1.0)


def _use_items(worker, timeouts):
    """Navigate to backpack and use the purchased item."""
    idx = worker.index
    adb = worker.adb
    handler = worker.handler
    matcher = worker.matcher

    logger.info(f"[Instance {idx}] Step 3: Use items")

    # Open backpack / inventory
    def _open_backpack():
        return matcher.wait_for_template(
            adb, TEMPLATES["backpack_icon"],
            timeout=timeouts["shop_navigation"]
        )

    try:
        pos = handler.with_retry(
            _open_backpack, f"Instance {idx} — Open Backpack"
        )
        adb.tap(*pos)
        time.sleep(1.5)
    except TimeoutError:
        logger.warning(f"[Instance {idx}] Backpack not found, skipping item use")
        return

    # Find and tap use button
    def _find_use():
        return matcher.wait_for_template(
            adb, TEMPLATES["item_use"],
            timeout=timeouts["shop_navigation"]
        )

    try:
        pos = handler.with_retry(
            _find_use, f"Instance {idx} — Use Item"
        )
        adb.tap(*pos)
        time.sleep(1.0)
    except TimeoutError:
        logger.warning(f"[Instance {idx}] Use button not found")

    # Dismiss any popup and go back
    handler.try_dismiss_popups()
    adb.press_back()
    time.sleep(1.0)


def _return_to_main(worker, timeouts):
    """Ensure we're back on the main game screen."""
    idx = worker.index
    adb = worker.adb
    matcher = worker.matcher

    logger.info(f"[Instance {idx}] Step 4: Return to main screen")

    # Press back a few times to ensure we're at root
    for _ in range(3):
        if matcher.is_template_visible(adb, TEMPLATES.get("main_screen", "")):
            logger.info(f"[Instance {idx}] Main screen confirmed")
            return
        adb.press_back()
        time.sleep(1.0)

    logger.warning(f"[Instance {idx}] Could not confirm main screen")
