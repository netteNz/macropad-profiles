"""Copy changed firmware files to the CIRCUITPY drive.

Every write to CIRCUITPY makes the board auto-reload, so this copies only
files whose contents differ, writes code.py last, and leaves lib/ to circup.
Use --prune to delete board files under ui/, profiles/ and panel/ that no longer
exist in firmware/ (nothing outside those folders is ever deleted).

    python tools/deploy.py [--drive F:\\] [--prune] [--dry-run]
"""
import argparse
import filecmp
import os
import shutil
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "firmware")
SKIP_DIRS = {"tests", "__pycache__", "lib"}
SKIP_FILES = {"requirements.txt"}
PRUNE_DIRS = ("ui", "profiles", "panel")


def firmware_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name in SKIP_FILES or not name.endswith((".py", ".mpy", ".bdf", ".pcf")):
                continue
            yield os.path.relpath(os.path.join(dirpath, name), ROOT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drive", default="F:\\")
    ap.add_argument("--prune", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(os.path.join(args.drive, "boot_out.txt")):
        sys.exit("No CIRCUITPY drive at %s (boot_out.txt missing)" % args.drive)

    files = sorted(firmware_files(), key=lambda p: p == "code.py")  # code.py last
    changed = []
    for rel in files:
        dst = os.path.join(args.drive, rel)
        if os.path.exists(dst) and filecmp.cmp(os.path.join(ROOT, rel), dst, shallow=False):
            continue
        changed.append(rel)

    removed = []
    if args.prune:
        keep = set(files)
        for d in PRUNE_DIRS:
            for dirpath, _, filenames in os.walk(os.path.join(args.drive, d)):
                for name in filenames:
                    rel = os.path.relpath(os.path.join(dirpath, name), args.drive)
                    if rel not in keep:
                        removed.append(rel)

    for rel in changed:
        print("copy  ", rel)
        if not args.dry_run:
            dst = os.path.join(args.drive, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(os.path.join(ROOT, rel), dst)
    for rel in removed:
        print("remove", rel)
        if not args.dry_run:
            os.remove(os.path.join(args.drive, rel))
    if not (changed or removed):
        print("up to date")
    elif not args.dry_run:
        # Flush so the board doesn't reload from a half-written FAT.
        if hasattr(os, "sync"):
            os.sync()


if __name__ == "__main__":
    main()
