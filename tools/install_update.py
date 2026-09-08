"""Install the newest Albatross USB update bundle from a terminal."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from albatross_pi.state.snapshot import StateSnapshot
from albatross_pi.updater import install_update_from_usb, diagnose_repository_install


def main() -> None:
    parser = argparse.ArgumentParser(description="Install an Albatross USB update bundle")
    parser.add_argument("--bundle", type=Path, help="explicit update bundle zip or unpacked bundle directory")
    parser.add_argument("--diagnose", action="store_true", help="read-only online-update install check; no download, install, flash or reboot")
    args = parser.parse_args()
    if args.diagnose:
        if args.bundle:
            parser.error("--diagnose cannot be combined with --bundle")
        result = diagnose_repository_install()
        print(f"HUD install: {ROOT}")
        print(result.display())
        if result.status == "ZIP/COPY INSTALL":
            print("See docs/update_bundles.md: Migrating a ZIP installation. Keep your existing folder.")
        return
    if args.bundle:
        os.environ["ALBATROSS_UPDATE_BUNDLE"] = str(args.bundle)
    result = install_update_from_usb(StateSnapshot())
    print(result.display())


if __name__ == "__main__":
    main()
