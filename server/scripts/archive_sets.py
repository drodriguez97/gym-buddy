"""Take sets off the dashboard without destroying them.

    python scripts/archive_sets.py 20 21 28-33        (from server/; set numbers or ranges)
    python scripts/archive_sets.py --restore 30

Archiving moves a set's .bin and .json from data/sets to data/archive and
removes its database row. Restoring moves the files back and counts the set
again. Nothing is ever deleted: some sets exist only on the server.
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from app import db, main  # noqa: E402

ARCHIVE = main.SET_DIR.parent / "archive"


def numbers(args):
    wanted = set()
    for arg in args:
        first, _, last = arg.partition("-")
        wanted.update(range(int(first), int(last or first) + 1))
    return wanted


def move(set_id, source, target):
    target.mkdir(parents=True, exist_ok=True)
    for ext in (".json", ".bin"):
        shutil.move(str(source / (set_id + ext)), str(target / (set_id + ext)))


def archive(wanted):
    done = []
    for path in sorted(main.SET_DIR.glob("*.bin")):
        if int(path.stem[:5]) in wanted and path.with_suffix(".json").exists():
            db.delete_set(path.stem)        # row first: a set is never on the dashboard without its files
            move(path.stem, main.SET_DIR, ARCHIVE)
            done.append(path.stem)
    return done


def restore(wanted):
    done = []
    for path in sorted(ARCHIVE.glob("*.bin")):
        if int(path.stem[:5]) in wanted:
            move(path.stem, ARCHIVE, main.SET_DIR)
            main.record(path.stem)
            done.append(path.stem)
    return done


if __name__ == "__main__":
    args = sys.argv[1:]
    restoring = args[:1] == ["--restore"]
    done = restore(numbers(args[1:])) if restoring else archive(numbers(args))
    print(f"{'restored' if restoring else 'archived'} {len(done)}: {' '.join(s[:5] for s in done)}")
    print(f"{len(db.list_sets())} sets on the dashboard, {len(list(ARCHIVE.glob('*.bin')))} in {ARCHIVE}")
