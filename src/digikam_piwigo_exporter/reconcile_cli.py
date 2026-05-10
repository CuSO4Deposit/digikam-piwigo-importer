from __future__ import annotations

import argparse
import logging
from pathlib import Path

from digikam_piwigo_exporter.config import load_config
from digikam_piwigo_exporter.piwigo import PiwigoClient
from digikam_piwigo_exporter.reconcile import ShareReconciler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="digikam-piwigo-reconcile-shares",
        description="Associate existing Piwigo images with share albums based on tags.",
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--dry-run", action="store_true")
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
    args = build_parser().parse_args(argv)
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
        reconciler = ShareReconciler(piwigo=client, config=config)
        events = reconciler.reconcile(dry_run=args.dry_run)
        for event in events:
            logging.info(
                "%s image %s: %s",
                event.kind,
                event.image_id,
                event.message,
            )
    finally:
        client.close()

    return 0
