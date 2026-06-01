"""Hash one NFC reader value for settings/nfc_auth.json."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from albatross_pi.security.nfc import tag_sha256


def main() -> None:
    parser = argparse.ArgumentParser(description="Hash an NFC tag value without storing its raw identifier")
    parser.add_argument("tag", help="raw line emitted by the USB NFC reader")
    args = parser.parse_args()
    print(tag_sha256(args.tag))


if __name__ == "__main__":
    main()
