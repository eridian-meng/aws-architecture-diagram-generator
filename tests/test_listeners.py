import unittest

from aws_diagram.discovery import _listener_labels, _listener_target_group_arns
from aws_diagram.models import Resource
from aws_diagram.svg_renderer import render_svg
from aws_diagram.sample_data import build_sample_model


class ListenerTests(unittest.TestCase):
    def test_listener_labels_are_compact_and_sorted(self):
        listeners = [
            {"Protocol": "HTTPS", "Port": 443, "DefaultActions": [{"Type": "forward", "TargetGroupArn": "tg-https"}]},
            {"Protocol": "HTTP", "Port": 80, "DefaultActions": [{"Type": "redirect"}]},
            {"Protocol": "TCP", "Port": 22, "DefaultActions": [{"Type": "forward", "TargetGroupArn": "tg-tcp"}]},
            {"Protocol": "HTTPS", "Port": 8443, "DefaultActions": [{"Type": "forward", "TargetGroupArn": "tg-unused"}]},
            {"Protocol": "HTTPS", "Port": 443, "DefaultActions": [{"Type": "forward", "TargetGroupArn": "tg-https"}]},
        ]

        self.assertEqual(_listener_labels(listeners, backend_target_group_arns={"tg-https", "tg-tcp"}), ["TCP:22", "HTTPS:443"])

    def test_listener_target_groups_include_weighted_forward_actions(self):
        listeners = [
            {
                "DefaultActions": [
                    {"Type": "forward", "TargetGroupArn": "tg-direct"},
                    {
                        "Type": "forward",
                        "ForwardConfig": {
                            "TargetGroups": [
                                {"TargetGroupArn": "tg-weighted-a"},
                                {"TargetGroupArn": "tg-weighted-b"},
                            ]
                        },
                    },
                    {"Type": "redirect"},
                ]
            }
        ]

        self.assertEqual(
            _listener_target_group_arns(listeners),
            {"tg-direct", "tg-weighted-a", "tg-weighted-b"},
        )

    def test_svg_renders_listener_details_on_load_balancer(self):
        model = build_sample_model()
        for resource in model.resources:
            if resource.id == "public-elb":
                resource.listeners = ["HTTPS:443", "HTTP:80"]
                break

        svg = render_svg(model)

        self.assertIn("HTTPS:443, HTTP:80", svg)


if __name__ == "__main__":
    unittest.main()
