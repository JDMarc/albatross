"""Install the newest Albatross USB update bundle from a terminal."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from albatross_pi.state.snapshot import StateSnapshot
from albatross_pi.updater import install_update_from_usb


def main() -> None:
    parser = argparse.ArgumentParser(description="Install an Albatross USB update bundle")
    parser.add_argument("--bundle", type=Path, help="explicit update bundle zip or unpacked bundle directory")
    args = parser.parse_args()
    if args.bundle:
        os.environ["ALBATROSS_UPDATE_BUNDLE"] = str(args.bundle)
    result = install_update_from_usb(StateSnapshot())
    print(result.display())


if __name__ == "__main__":
    main()
