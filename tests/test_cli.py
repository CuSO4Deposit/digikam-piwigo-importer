from digikam_piwigo_exporter.cli import build_parser


def test_parser_accepts_no_dedupe_check() -> None:
    args = build_parser().parse_args(
        [
            "--input",
            "album",
            "--album",
            "Trips",
            "--base-url",
            "https://photos.example",
            "--no-dedupe-check",
        ]
    )

    assert args.no_dedupe_check is True
