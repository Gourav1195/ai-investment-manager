from __future__ import annotations

from src.investing.cli import build_parser


def test_build_parser_includes_portfolio_command() -> None:
    parser = build_parser()
    args = parser.parse_args(["portfolio", "load-examples", "--database", "work/portfolio.db"])
    assert args.command == "portfolio"
    assert args.portfolio_command == "load-examples"
