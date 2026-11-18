import unittest

from netbox_asset_labels.layout import QR_LEFT, QR_NONE, QR_RIGHT, LabelError, LabelSpec, render_label
from netbox_asset_labels.ptouch import TAPES, mm_to_dots

URL = 'https://netbox.example.com/dcim/devices/1234/'


def dark_columns(image):
    width, height = image.size
    pixels = image.load()
    return [x for x in range(width) if any(pixels[x, y] == 0 for y in range(height))]


class RenderLabelTest(unittest.TestCase):

    def test_height_matches_tape(self):
        for tape in TAPES.values():
            with self.subTest(tape=tape.label):
                image = render_label(LabelSpec(lines=['sw-core-01']), tape.pins)
                self.assertEqual(image.mode, '1')
                self.assertEqual(image.height, tape.pins)
                self.assertTrue(dark_columns(image))

    def test_qr_and_text(self):
        height = TAPES[12].pins
        text_only = render_label(LabelSpec(lines=['sw-core-01', 'AT-0042']), height)
        with_qr = render_label(LabelSpec(lines=['sw-core-01', 'AT-0042'], qr_data=URL), height)
        self.assertGreater(with_qr.width, text_only.width + height // 2)

    def test_qr_position(self):
        height = TAPES[24].pins
        left = render_label(LabelSpec(lines=['x'], qr_data=URL, qr_position=QR_LEFT), height)
        right = render_label(LabelSpec(lines=['x'], qr_data=URL, qr_position=QR_RIGHT), height)
        self.assertEqual(dark_columns(left)[0], 0)
        self.assertEqual(dark_columns(right)[-1], right.width - 1)

    def test_qr_only(self):
        image = render_label(LabelSpec(qr_data=URL), TAPES[18].pins)
        self.assertEqual(image.width, max(dark_columns(image)) + 1)

    def test_qr_too_large(self):
        with self.assertRaises(LabelError):
            render_label(LabelSpec(qr_data=URL * 3), TAPES[4].pins)

    def test_fixed_length(self):
        image = render_label(LabelSpec(lines=['a fairly long device name', 'x'], length_mm=40), TAPES[12].pins)
        self.assertEqual(image.width, mm_to_dots(40))

    def test_fixed_length_too_short(self):
        with self.assertRaises(LabelError):
            render_label(LabelSpec(lines=['x' * 200], length_mm=5), TAPES[12].pins)

    def test_more_lines_smaller_text(self):
        one = render_label(LabelSpec(lines=['ABCDEFGH']), TAPES[12].pins)
        three = render_label(LabelSpec(lines=['ABCDEFGH'] * 3, emphasize_first_line=False), TAPES[12].pins)
        self.assertLess(three.width, one.width)

    def test_empty_rejected(self):
        with self.assertRaises(LabelError):
            render_label(LabelSpec(lines=[], qr_data=URL, qr_position=QR_NONE), TAPES[12].pins)


if __name__ == '__main__':
    unittest.main()
