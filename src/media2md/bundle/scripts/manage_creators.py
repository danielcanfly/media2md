#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import os
import re
import shutil
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "creators.yaml"
BACKUPS = ROOT / "config" / "backups"
LOCK = ROOT / "config" / ".creators.lock"
INIT_SCRIPT = ROOT / "scripts" / "init_system.py"

USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")


def clean_username(value: str) -> str:
    value = value.strip().lstrip("@")

    if not USERNAME_RE.fullmatch(value):
        raise ValueError(
            "Username must contain 1-30 letters, numbers, "
            "periods, or underscores."
        )

    return value


def parse_bool(value: str) -> bool:
    value = value.strip().lower()

    if value in {"true", "1", "yes", "on"}:
        return True

    if value in {"false", "0", "no", "off"}:
        return False

    raise argparse.ArgumentTypeError("Use true or false.")


def normalize(item: dict) -> dict:
    limit = int(item.get("max_new_per_run", 20))

    if not 1 <= limit <= 500:
        raise ValueError(
            "max_new_per_run must be between 1 and 500."
        )

    return {
        "username": clean_username(
            str(item.get("username", ""))
        ),
        "enabled": bool(item.get("enabled", True)),
        "language": str(
            item.get("language", "auto")
        ).strip() or "auto",
        "max_new_per_run": limit,
        "scan_reels": bool(
            item.get("scan_reels", True)
        ),
        "note": str(
            item.get("note", "") or ""
        ),
    }


@contextmanager
def config_lock():
    LOCK.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with LOCK.open(
        "a+",
        encoding="utf-8",
    ) as handle:
        fcntl.flock(
            handle.fileno(),
            fcntl.LOCK_EX,
        )

        try:
            yield
        finally:
            fcntl.flock(
                handle.fileno(),
                fcntl.LOCK_UN,
            )


def load_creators() -> list[dict]:
    if not CONFIG.exists():
        raise RuntimeError(
            f"Missing config: {CONFIG}"
        )

    try:
        document = yaml.safe_load(
            CONFIG.read_text(
                encoding="utf-8"
            )
        ) or {}
    except yaml.YAMLError as exc:
        raise RuntimeError(
            f"Invalid YAML: {exc}"
        ) from exc

    items = document.get("creators")

    if not isinstance(items, list):
        raise RuntimeError(
            "creators.yaml must contain "
            "a top-level creators list."
        )

    creators: list[dict] = []
    seen: set[str] = set()

    for item in items:
        if not isinstance(item, dict):
            raise RuntimeError(
                "Every creator entry must be an object."
            )

        creator = normalize(item)
        key = creator["username"].lower()

        if key in seen:
            raise RuntimeError(
                f"Duplicate creator: "
                f"{creator['username']}"
            )

        seen.add(key)
        creators.append(creator)

    return creators


def save_creators(
    creators: list[dict],
) -> None:
    BACKUPS.mkdir(
        parents=True,
        exist_ok=True,
    )

    if CONFIG.exists():
        stamp = datetime.now().strftime(
            "%Y%m%d-%H%M%S-%f"
        )

        shutil.copy2(
            CONFIG,
            BACKUPS / f"creators-{stamp}.yaml",
        )

    temp = CONFIG.with_suffix(
        ".yaml.tmp"
    )

    temp.write_text(
        yaml.safe_dump(
            {"creators": creators},
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    os.replace(
        temp,
        CONFIG,
    )


def find_creator(
    creators: list[dict],
    name: str,
):
    key = clean_username(name).lower()

    for index, creator in enumerate(creators):
        if creator["username"].lower() == key:
            return index, creator

    return None, None


def sync_database() -> None:
    subprocess.run(
        [
            sys.executable,
            str(INIT_SCRIPT),
        ],
        cwd=ROOT,
        check=True,
    )


def cmd_list(_args) -> int:
    creators = load_creators()

    print(
        "USERNAME | ENABLED | LANGUAGE | "
        "MAX_NEW | REELS | NOTE"
    )
    print("-" * 90)

    if not creators:
        print("(no creators configured)")
        return 0

    for creator in creators:
        print(
            f"{creator['username']} | "
            f"{str(creator['enabled']).lower()} | "
            f"{creator['language']} | "
            f"{creator['max_new_per_run']} | "
            f"{str(creator['scan_reels']).lower()} | "
            f"{creator['note'] or '-'}"
        )

    return 0


def cmd_add(args) -> int:
    with config_lock():
        creators = load_creators()
        name = clean_username(
            args.username
        )

        index, _ = find_creator(
            creators,
            name,
        )

        if index is not None:
            raise RuntimeError(
                f"Creator already exists: {name}"
            )

        creator = normalize(
            {
                "username": name,
                "enabled": not args.disabled,
                "language": args.language,
                "max_new_per_run":
                    args.max_new_per_run,
                "scan_reels":
                    not args.no_reels,
                "note": args.note,
            }
        )

        creators.append(creator)

        creators.sort(
            key=lambda item:
                item["username"].lower()
        )

        save_creators(creators)

    sync_database()

    print(
        f"CREATOR_ADDED "
        f"username={name} "
        f"enabled="
        f"{str(creator['enabled']).lower()}"
    )

    return 0


def update_creator(
    name: str,
    updater,
) -> dict:
    with config_lock():
        creators = load_creators()

        index, creator = find_creator(
            creators,
            name,
        )

        if index is None or creator is None:
            raise RuntimeError(
                f"Creator not found: "
                f"{clean_username(name)}"
            )

        updated = normalize(
            updater(dict(creator))
        )

        creators[index] = updated
        save_creators(creators)

    sync_database()
    return updated


def cmd_enable(args) -> int:
    creator = update_creator(
        args.username,
        lambda item: {
            **item,
            "enabled": True,
        },
    )

    print(
        f"CREATOR_ENABLED "
        f"username={creator['username']}"
    )

    return 0


def cmd_disable(args) -> int:
    creator = update_creator(
        args.username,
        lambda item: {
            **item,
            "enabled": False,
        },
    )

    print(
        f"CREATOR_DISABLED "
        f"username={creator['username']}"
    )

    return 0


def cmd_set(args) -> int:
    values = (
        args.language,
        args.max_new_per_run,
        args.scan_reels,
        args.note,
    )

    if all(
        value is None
        for value in values
    ):
        raise RuntimeError(
            "No changes supplied."
        )

    def apply(item: dict) -> dict:
        if args.language is not None:
            item["language"] = args.language

        if args.max_new_per_run is not None:
            item["max_new_per_run"] = (
                args.max_new_per_run
            )

        if args.scan_reels is not None:
            item["scan_reels"] = (
                args.scan_reels
            )

        if args.note is not None:
            item["note"] = args.note

        return item

    creator = update_creator(
        args.username,
        apply,
    )

    print(
        f"CREATOR_UPDATED "
        f"username={creator['username']} "
        f"language={creator['language']} "
        f"max_new_per_run="
        f"{creator['max_new_per_run']} "
        f"scan_reels="
        f"{str(creator['scan_reels']).lower()}"
    )

    return 0


def cmd_validate(_args) -> int:
    creators = load_creators()

    print(
        f"CREATOR_CONFIG_VALID "
        f"creators={len(creators)}"
    )

    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Safely manage Instagram "
            "creator configuration."
        )
    )

    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    command = commands.add_parser(
        "list",
        help="List creators.",
    )
    command.set_defaults(
        func=cmd_list,
    )

    command = commands.add_parser(
        "add",
        help="Add a creator.",
    )

    command.add_argument(
        "username",
    )

    command.add_argument(
        "--language",
        default="auto",
    )

    command.add_argument(
        "--max-new-per-run",
        type=int,
        default=20,
    )

    command.add_argument(
        "--note",
        default="",
    )

    command.add_argument(
        "--disabled",
        action="store_true",
    )

    command.add_argument(
        "--no-reels",
        action="store_true",
    )

    command.set_defaults(
        func=cmd_add,
    )

    command = commands.add_parser(
        "enable",
        help="Enable a creator.",
    )

    command.add_argument(
        "username",
    )

    command.set_defaults(
        func=cmd_enable,
    )

    command = commands.add_parser(
        "disable",
        help="Disable a creator.",
    )

    command.add_argument(
        "username",
    )

    command.set_defaults(
        func=cmd_disable,
    )

    command = commands.add_parser(
        "set",
        help="Update creator settings.",
    )

    command.add_argument(
        "username",
    )

    command.add_argument(
        "--language",
    )

    command.add_argument(
        "--max-new-per-run",
        type=int,
    )

    command.add_argument(
        "--scan-reels",
        type=parse_bool,
    )

    command.add_argument(
        "--note",
    )

    command.set_defaults(
        func=cmd_set,
    )

    command = commands.add_parser(
        "validate",
        help="Validate creator config.",
    )

    command.set_defaults(
        func=cmd_validate,
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        return args.func(args)

    except (
        RuntimeError,
        ValueError,
        yaml.YAMLError,
        subprocess.CalledProcessError,
        OSError,
    ) as exc:
        print(
            f"ERROR: {exc}",
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
