import unittest

from aws_diagram.layout_engine import build_layout
from aws_diagram.sample_data import build_sample_model


class LayoutTests(unittest.TestCase):
    def test_public_subnet_cards_match_private_instance_card_width(self):
        layout = build_layout(build_sample_model())

        public_card = layout.node_layouts["nat-a"].box
        private_card = layout.node_layouts["app-a1"].box

        self.assertEqual(public_card.width, private_card.width)


if __name__ == "__main__":
    unittest.main()
