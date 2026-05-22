# AWS Architecture Diagram Automation

This project will automate AWS architecture diagrams from an AWS account and region input.

The immediate goal is not full discovery yet. The first step is to lock a baseline blueprint that future discovery and rendering code will target.

## Baseline Direction

- Input: `account_id`, `region`
- Discovery layer: enumerate AWS resources and relationships from APIs/CLI
- Normalization layer: convert raw resources into a graph model
- Rendering layer: translate the graph into diagram code for AWS icons
- Output: a clean architecture diagram with explicit network flow

## Important Constraint

The AWS Diagram MCP server is a rendering tool. It generates diagrams from diagram code, but it does not discover AWS resources on its own. This project therefore needs two separate responsibilities:

1. Resource discovery
2. Diagram rendering

## First Blueprint

The baseline blueprint lives in [docs/baseline-blueprint.md](/Users/gagandeep.toor/Projects/aws/aws-diagram/docs/baseline-blueprint.md).

The first machine-friendly version of that blueprint lives in [specs/baseline-network-blueprint.yaml](/Users/gagandeep.toor/Projects/aws/aws-diagram/specs/baseline-network-blueprint.yaml).

## Proposed Flow

1. User provides AWS account ID and region.
2. Discovery gathers VPCs, subnets, route tables, internet gateways, NAT gateways, load balancers, security groups, EC2, Auto Scaling groups, RDS, EFS, VPC endpoints, and major managed dependencies.
3. The discovery output is normalized into zones, tiers, resources, and edges.
4. The renderer selects a blueprint and fills it with real resources.
5. The diagram generator emits a clean architecture artifact.

## Baseline Rendering Rules

- Prefer a two-AZ mirrored layout when the VPC spans at least two AZs.
- Show boundaries in this order: AWS cloud, region, VPC, availability zone, subnet.
- Keep ingress at the top or left edge, then application tier, then data tier.
- Show arrows only for meaningful network or service flow.
- Avoid crossing lines when grouping can remove ambiguity.
- Use current AWS official icons in the final rendered output.
- Use AWS reference-architecture layout conventions for spacing, labels, and flow narration.

## Next Step

The next implementation step should be a small discovery schema and a renderer adapter that can turn the YAML blueprint into AWS Diagram MCP server code.

## Current Working Slice

The repo now includes a first local renderer implementation under `src/aws_diagram/`.

Install/check Python requirements with:

```bash
python3 -m pip install -r requirements.txt
```

There are currently no third-party Python package dependencies. The only external prerequisite for live discovery is the AWS CLI with a valid authenticated profile.

Generate the current sample diagram with:

```bash
python3 -m aws_diagram.cli --output diagrams/generated-sample.svg
```

This generates a generic sample SVG using the official AWS icon assets already downloaded into the workspace.
The built-in sample model is sanitized for publishing and does not use live account data.

Generate a live diagram from a real account, region, and VPC with:

```bash
aws sso login --profile <your-profile>
python3 -m aws_diagram.cli --profile <your-profile> --account <acct> --region <region> --vpc <vpc-id-or-name> --output diagrams/<name>.svg
```

The live discovery path currently uses the local AWS CLI to inspect the target account, region, and VPC, then renders the discovered topology into SVG.
Live and customer-specific diagram artifacts should be treated as internal outputs and are ignored by `.gitignore` by default.

The discovery path is read-only. The implementation is limited to AWS CLI `describe`, `list`, `get`, and `search` operations that fetch inventory and routing data, and it will refuse any non-read-only AWS CLI call.

If your AWS config contains account-scoped profiles such as `account-123456789012`, `--profile` is optional. The CLI will try to resolve the profile automatically from the requested account:

```bash
python3 -m aws_diagram.cli --account <acct> --region <region> --vpc <vpc-id-or-name> --output diagrams/<name>.svg
```

Route tables are hidden by default. Include them only when needed:

```bash
python3 -m aws_diagram.cli --account <acct> --region <region> --vpc <vpc-id-or-name> --show-routes --output diagrams/<name>.svg
```

Security groups are hidden by default. Include an appendix with security groups attached to drawn resources, plus inbound and outbound rules:

```bash
draw --account <acct> --region <region> --vpc <vpc-id-or-name> --show-security-groups --output diagrams/<name>.svg
```

The security group appendix includes only security groups attached to resources shown in the diagram, such as load balancers, EC2 instances, and RDS instances. Rules are summarized by direction, protocol, port range, and source CIDRs/security group references.

Use `--full` to include all optional sections:

```bash
draw --account <acct> --region <region> --vpc <vpc-id-or-name> --full --output diagrams/<name>.svg
```

## Global `draw` Command

Install a global wrapper for this checkout with:

```bash
scripts/install-draw-wrapper.sh
```

The wrapper installs this project into the repo virtualenv in editable mode and writes `~/.local/bin/draw`. After `~/.local/bin` is on your `PATH`, the command can be run from any directory:

```bash
draw --account <acct> --region <region> --vpc <vpc-id-or-name> --output diagrams/<name>.svg
```

Relative `--output` paths are resolved from the directory where you run `draw`, not from this repository.

By default, `draw` writes only the requested SVG file. Add `--drawio` when you also want the matching draw.io file:

```bash
draw --account <acct> --region <region> --vpc <vpc-id-or-name> --output diagrams/<name>.svg --drawio
```

To create only a draw.io file, use a `.drawio` output path:

```bash
draw --account <acct> --region <region> --vpc <vpc-id-or-name> --output diagrams/<name>.drawio
```
