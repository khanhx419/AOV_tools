# AOV Tools — LDPlayer Multi-Instance Automation

Python-based RPA script that automates **Arena of Valor (Liên Quân Mobile)** across multiple LDPlayer emulator instances.

## Features

- **Multi-instance orchestration** — Master/Slave architecture with grouped instance binding
- **Image recognition** — OpenCV template matching for UI navigation
- **OCR** — Tesseract with preprocessing pipeline (grayscale → upscale → binarize) for Room ID extraction
- **Synchronized timing** — Master-driven `threading.Event` for coordinated feature toggles at T=180s
- **Error recovery** — Timeout + retry + popup-dismiss logic on all operations
- **ADB throttling** — Enforced 1.0s minimum poll interval to prevent emulator lag

## Requirements

- Python 3.10+
- [LDPlayer 9](https://www.ldplayer.net/)
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) (installed and on PATH)

## Setup

```bash
# Install Python dependencies
pip install -r requirements.txt

# Configure your instances in config.json
# - Set ldplayer_path and adb_path
# - Define instance_groups (master → slave bindings)
# - Calibrate OCR room_id_region coordinates

# Place template screenshots in templates/
# (cropped PNGs of all UI buttons, icons, and indicators)
```

## Usage

```bash
# Ensure all LDPlayer instances are running and game is open
python main.py
```

## Project Structure

```
AOV_tools/
├── config.json              # Instance groups, paths, timings, timeouts
├── main.py                  # Entry point — orchestrator
├── core/
│   ├── adb_controller.py    # ADB wrapper (screencap, tap, swipe, text)
│   ├── ldplayer_manager.py  # ldconsole wrapper (list2, launch, quit)
│   ├── image_matcher.py     # OpenCV template matching + polling
│   ├── ocr_reader.py        # Tesseract OCR with preprocessing
│   ├── error_handler.py     # Timeout recovery, popup dismissal
│   └── instance_worker.py   # Per-instance thread worker
├── phases/
│   ├── phase1_init.py       # Claim rewards, shop, use items
│   ├── phase2_room.py       # Room create (Master) / join (Slave)
│   └── phase3_match.py      # Hero select, synced timer, match loop ×4
├── templates/               # UI template images (.png)
├── logs/                    # Runtime logs
└── requirements.txt         # Python dependencies
```

## Workflow

1. **Phase 1** — All instances claim rewards, purchase shop items, use items
2. **Phase 2** — Masters create custom rooms, extract Room IDs via OCR, Slaves join
3. **Phase 3** — 4-match loop: hero select → ready → 3-min timer → feature toggle → match end → play again

## Configuration

Edit `config.json` to match your setup:

| Key | Description |
|-----|-------------|
| `ldplayer_path` | LDPlayer installation directory |
| `instance_groups` | Master→Slave bindings (e.g. `[{"master": 0, "slaves": [2, 3]}]`) |
| `match_count` | Number of matches per run (default: 4) |
| `match_timer_seconds` | Seconds before feature toggle (default: 180) |
| `ocr.room_id_region` | Pixel coordinates for Room ID crop region |
| `template_confidence` | OpenCV match threshold (default: 0.8) |

## License

Private project — not for redistribution.
