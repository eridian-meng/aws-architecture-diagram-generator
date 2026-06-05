from __future__ import annotations

import argparse
from pathlib import Path

from aws_diagram.drawio_renderer import render_to_file as render_drawio_to_file
from aws_diagram.discovery import discover_account
from aws_diagram.sample_data import build_sample_model
from aws_diagram.svg_renderer import render_to_file as render_svg_to_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AWS diagram generator")
    parser.add_argument(
        "--output",
        default="diagrams/generated-sample.svg",
        help="Output path; writes SVG by default, or draw.io when the path ends in .drawio",
    )
    parser.add_argument(
        "--drawio",
        action="store_true",
        help="Also write a matching .drawio file when the output path is SVG",
    )
    parser.add_argument("--profile", help="AWS profile to use for live discovery; defaults to AWS CLI resolution")
    parser.add_argument("--account", help="AWS account ID to validate and render")
    parser.add_argument("--account-id", dest="account", help=argparse.SUPPRESS)
    parser.add_argument("--region", help="AWS region to discover")
    parser.add_argument("--vpc", help="VPC ID or Name tag to scope live discovery")
    parser.add_argument("--show-routes", action="store_true", help="Include VPC and Transit Gateway route tables")
    parser.add_argument(
        "--show-security-groups",
        action="store_true",
        help="Append security groups and rules for resources shown in the diagram",
    )
    parser.add_argument("--state", action="store_true", help="Show EC2 instance state labels")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Include routes and security groups",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    show_routes = args.show_routes or args.full
    show_security_groups = args.show_security_groups or args.full
    show_state = args.state
    output_path = Path(args.output)
    output_is_drawio = output_path.suffix.lower() == ".drawio"
    svg_path = output_path if not output_is_drawio else None
    drawio_path = output_path if output_is_drawio else output_path.with_suffix(".drawio")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if args.profile or args.account or args.region or args.vpc:
        missing = [name for name, value in (("account", args.account), ("region", args.region), ("vpc", args.vpc)) if not value]
        if missing:
            parser.error(f"missing required arguments for live discovery: {', '.join(missing)}")
        model = discover_account(
            account=args.account,
            region=args.region,
            vpc=args.vpc,
            profile=args.profile,
            show_routes=show_routes,
            show_security_groups=show_security_groups,
            show_state=show_state,
        )
    else:
        model = build_sample_model(
            show_routes=show_routes,
            show_security_groups=show_security_groups,
            show_state=show_state,
        )
    if svg_path:
        render_svg_to_file(model, svg_path)
        print(svg_path)
    if output_is_drawio or args.drawio:
        drawio_path.parent.mkdir(parents=True, exist_ok=True)
        render_drawio_to_file(model, drawio_path)
        print(drawio_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
