from __future__ import annotations

import base64
import os
from pathlib import Path


PROJECT_ROOT = Path(os.environ.get("AWS_DIAGRAM_HOME", Path(__file__).resolve().parents[2]))
ICON_ROOT = PROJECT_ROOT / "aws-icons"


ICON_PATHS = {
    "aws_cloud": ICON_ROOT / "Architecture-Group-Icons_01302026/AWS-Cloud-logo_32.png",
    "vpc": ICON_ROOT / "Architecture-Group-Icons_01302026/Virtual-private-cloud-VPC_32.png",
    "public_subnet": ICON_ROOT / "Architecture-Group-Icons_01302026/Public-subnet_32.png",
    "private_subnet": ICON_ROOT / "Architecture-Group-Icons_01302026/Private-subnet_32.png",
    "route53": ICON_ROOT
    / "Architecture-Service-Icons_01302026/Arch_Networking-Content-Delivery/48/Arch_Amazon-Route-53_48.png",
    "internet_gateway": ICON_ROOT
    / "Resource-Icons_01302026/Res_Networking-Content-Delivery/Res_Amazon-VPC_Internet-Gateway_48.png",
    "nat_gateway": ICON_ROOT
    / "Resource-Icons_01302026/Res_Networking-Content-Delivery/Res_Amazon-VPC_NAT-Gateway_48.png",
    "alb": ICON_ROOT
    / "Resource-Icons_01302026/Res_Networking-Content-Delivery/Res_Elastic-Load-Balancing_Application-Load-Balancer_48.png",
    "nlb": ICON_ROOT
    / "Resource-Icons_01302026/Res_Networking-Content-Delivery/Res_Elastic-Load-Balancing_Network-Load-Balancer_48.png",
    "ec2_instance": ICON_ROOT / "Resource-Icons_01302026/Res_Compute/Res_Amazon-EC2_Instance_48.png",
    "rds": ICON_ROOT / "Architecture-Service-Icons_01302026/Arch_Databases/48/Arch_Amazon-RDS_48.png",
    "rds_multi_az": ICON_ROOT / "Resource-Icons_01302026/Res_Databases/Res_Amazon-RDS_Multi-AZ_48.png",
    "waf": ICON_ROOT / "Architecture-Service-Icons_01302026/Arch_Security-Identity/48/Arch_AWS-WAF_48.png",
    "transit_gateway": ICON_ROOT
    / "Architecture-Service-Icons_01302026/Arch_Networking-Content-Delivery/48/Arch_AWS-Transit-Gateway_48.png",
    "tgw_peering": ICON_ROOT
    / "Resource-Icons_01302026/Res_Networking-Content-Delivery/Res_AWS-Transit-Gateway_Attachment_48.png",
    "site_to_site_vpn": ICON_ROOT
    / "Architecture-Service-Icons_01302026/Arch_Networking-Content-Delivery/48/Arch_AWS-Site-to-Site-VPN_48.png",
    "vpn_connection": ICON_ROOT
    / "Resource-Icons_01302026/Res_Networking-Content-Delivery/Res_Amazon-VPC_VPN-Connection_48.png",
    "vpc_peering": ICON_ROOT
    / "Resource-Icons_01302026/Res_Networking-Content-Delivery/Res_Amazon-VPC_Peering-Connection_48.png",
    "privatelink": ICON_ROOT
    / "Architecture-Service-Icons_01302026/Arch_Networking-Content-Delivery/48/Arch_AWS-PrivateLink_48.png",
    "route_table": ICON_ROOT
    / "Resource-Icons_01302026/Res_Networking-Content-Delivery/Res_Amazon-Route-53_Route-Table_48.png",
}


def icon_data_uri(name: str) -> str:
    path = ICON_PATHS[name]
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
