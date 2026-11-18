import unittest

from PIL import Image, ImageDraw

from netbox_asset_labels.ptouch import (
    CUT_FULL, CUT_NONE, CUT_TAB, HEAD_PINS, TAPES, encode_job, packbits, parse_status,
)


def unpackbits(data):
    out = bytearray()
    i = 0
    while i < len(data):
        n = data[i]
        i += 1
        if n < 128:
            out += data[i:i + n + 1]
            i += n + 1
        elif n > 128:
            out += bytes([data[i]]) * (257 - n)
            i += 1
    return bytes(out)


def decode_job(data):
    """Parse an encoded job back into pages: [(page settings, raster lines)]."""
    pages, lines, settings = [], [], {}
    i = 0
    while i < len(data):
        b = data[i]
        if b == 0x00:
            i += 1
        elif data[i:i + 2] == b'\x1b@':
            i += 2
        elif data[i:i + 3] == b'\x1bia':
            i += 4
        elif data[i:i + 3] == b'\x1biz':
            settings['width'] = data[i + 5]
            settings['lines'] = int.from_bytes(data[i + 7:i + 11], 'little')
            settings['page'] = data[i + 11]
            i += 13
        elif data[i:i + 3] == b'\x1biM':
            settings['mode'] = data[i + 3]
            i += 4
        elif data[i:i + 3] == b'\x1biA':
            settings['cut_every'] = data[i + 3]
            i += 4
        elif data[i:i + 3] == b'\x1biK':
            settings['advanced'] = data[i + 3]
            i += 4
        elif data[i:i + 3] == b'\x1bid':
            settings['margin'] = int.from_bytes(data[i + 3:i + 5], 'little')
            i += 5
        elif data[i:i + 2] == b'M\x02':
            i += 2
        elif b == ord('Z'):
            lines.append(bytes(16))
            i += 1
        elif b == ord('G'):
            n = int.from_bytes(data[i + 1:i + 3], 'little')
            lines.append(unpackbits(data[i + 3:i + 3 + n]))
            i += 3 + n
        elif b in (0x0C, 0x1A):
            pages.append((dict(settings, end=b), lines))
            lines, settings = [], {}
            i += 1
        else:
            raise AssertionError(f'Unexpected byte {b:#04x} at offset {i}')
    return pages


def lines_to_image(lines, tape):
    """Rebuild the label image (dark = 0) from raster lines."""
    image = Image.new('1', (len(lines), tape.pins), 1)
    for x, line in enumerate(lines):
        assert len(line) == HEAD_PINS // 8
        for pin in range(HEAD_PINS):
            if line[pin // 8] & (0x80 >> (pin % 8)):
                assert tape.offset <= pin < tape.offset + tape.pins, f'dot outside printable area at pin {pin}'
                image.putpixel((x, pin - tape.offset), 0)
    return image


def sample_image(tape, width=40):
    image = Image.new('1', (width, tape.pins), 1)
    draw = ImageDraw.Draw(image)
    draw.rectangle((2, 0, 10, tape.pins - 1), fill=0)
    draw.line((15, 0, width - 1, tape.pins - 1), fill=0)
    image.putpixel((width - 1, 0), 0)
    return image


class PackBitsTest(unittest.TestCase):

    def test_roundtrip(self):
        cases = [
            b'', b'\x00', b'\x00' * 16, b'\x01\x02\x03', b'\xff' * 200,
            bytes(range(256)), b'\x00\x00\x01\x02\x02\x02\x03', b'\xaa\xaa\xbb' * 50,
        ]
        for data in cases:
            with self.subTest(data=data[:10]):
                self.assertEqual(unpackbits(packbits(data)), data)

    def test_run_compresses(self):
        self.assertEqual(packbits(b'\x00' * 16), b'\xf1\x00')


class EncodeJobTest(unittest.TestCase):

    def test_image_roundtrip_all_tapes(self):
        for tape in TAPES.values():
            with self.subTest(tape=tape.label):
                image = sample_image(tape)
                (settings, lines), = decode_job(encode_job([image], tape))
                self.assertEqual(settings['width'], tape.code)
                self.assertEqual(settings['lines'], image.width)
                self.assertEqual(len(lines), image.width)
                self.assertEqual(lines_to_image(lines, tape).tobytes(), image.tobytes())

    def test_peel_tab_single_job(self):
        # One job: page positions first/middle/last, auto cut every label with half cut on
        tape = TAPES[12]
        pages = decode_job(encode_job([sample_image(tape)] * 3, tape, cut=CUT_TAB, margin_mm=2))
        self.assertEqual([p[0]['page'] for p in pages], [0, 1, 2])
        self.assertEqual([p[0]['end'] for p in pages], [0x0C, 0x0C, 0x1A])
        self.assertTrue(all(p[0]['mode'] == 0x40 and p[0]['advanced'] == 0x0C for p in pages))
        self.assertTrue(all(p[0]['cut_every'] == 1 for p in pages))
        self.assertEqual(pages[0][0]['margin'], 14)

    def test_single_page_is_last(self):
        tape = TAPES[12]
        (settings, _), = decode_job(encode_job([sample_image(tape)], tape))
        self.assertEqual(settings['page'], 2)

    def test_full_cut_separate_jobs(self):
        tape = TAPES[12]
        data = encode_job([sample_image(tape)] * 2, tape, cut=CUT_FULL)
        self.assertEqual(data.count(b'\x1b@'), 2)
        pages = decode_job(data)
        self.assertEqual([p[0]['end'] for p in pages], [0x1A, 0x1A])
        self.assertTrue(all(p[0]['advanced'] == 0x08 for p in pages))

    def test_no_cut(self):
        tape = TAPES[9]
        (settings, _), = decode_job(encode_job([sample_image(tape)], tape, cut=CUT_NONE))
        self.assertEqual(settings['mode'], 0x00)

    def test_wrong_height_rejected(self):
        with self.assertRaises(ValueError):
            encode_job([sample_image(TAPES[12])], TAPES[24])


class StatusTest(unittest.TestCase):

    def status_bytes(self, error1=0, error2=0, width=12, media=0x01, status_type=0):
        data = bytearray(32)
        data[0:4] = b'\x80\x20B0'
        data[8], data[9], data[10], data[11], data[18] = error1, error2, width, media, status_type
        return bytes(data)

    def test_parse(self):
        status = parse_status(self.status_bytes(width=4))
        self.assertEqual(status.tape, TAPES[4])
        self.assertEqual(status.errors, [])
        self.assertEqual(status.media_description, 'Laminated tape')

    def test_errors(self):
        status = parse_status(self.status_bytes(error1=0x01, error2=0x10, width=0, media=0))
        self.assertEqual(status.errors, ['No tape installed', 'Cover open'])
        self.assertIsNone(status.tape)


if __name__ == '__main__':
    unittest.main()
