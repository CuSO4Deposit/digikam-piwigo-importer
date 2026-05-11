from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from digikam_piwigo_exporter.config import load_config
from digikam_piwigo_exporter.importer import PiwigoImporter
from digikam_piwigo_exporter.piwigo import PiwigoClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="digikam-piwigo-import",
        description="Import a DigiKam-managed folder into Piwigo.",
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--album", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--no-dedupe-check",
        action="store_true",
        help="Skip per-file checksum lookups before upload. Faster for first imports, but not idempotent.",
    )
    parser.add_argument(
        "--update-existing-metadata",
        action="store_true",
        help=(
            "When checksum lookup finds an existing image, update its Piwigo "
            "title, description, tags, and privacy level from local metadata "
            "without uploading the image again."
        ),
    )
    parser.add_argument(
        "--check-auth",
        action="store_true",
        help="Check Piwigo authentication and exit.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Log debug details.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.no_dedupe_check and args.update_existing_metadata:
        parser.print_usage(sys.stderr)
        print(
            "digikam-piwigo-import: error: "
            "--update-existing-metadata cannot be used with --no-dedupe-check",
            file=sys.stderr,
        )
        return 2
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    config = load_config(args.config)
    client = PiwigoClient(
        args.base_url,
        username=config.username,
        password=config.password,
        api_key=config.api_key,
    )
    try:
        client.login()
        if args.check_auth:
            status = client.get_status()
            logging.info(
                "authenticated as %s (%s)",
                status.get("username", "unknown"),
                status.get("status", "unknown"),
            )
            return 0
        importer = PiwigoImporter(piwigo=client, config=config)
        events = importer.import_folder(
            args.input,
            args.album,
            dry_run=args.dry_run,
            dedupe_check=not args.no_dedupe_check,
            update_existing_metadata=args.update_existing_metadata,
        )
        for event in events:
            logging.info("%s %s: %s", event.kind, event.image_path, event.message)
    finally:
        client.close()

    return 0
