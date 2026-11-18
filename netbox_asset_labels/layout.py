"""
Composition of label images: an optional QR code next to one or more lines of
text, sized to the printable height of the tape. This module has no Django
dependencies.
"""
from dataclasses import dataclass, field

import segno
from PIL import Image, ImageDraw, ImageFont

from .ptouch import mm_to_dots

__all__ = (
    'ALIGN_CENTER',
    'ALIGN_LEFT',
    'QR_LEFT',
    'QR_NONE',
    'QR_RIGHT',
    'LabelError',
    'LabelSpec',
    'render_label',
)

QR_NONE = 'none'
QR_LEFT = 'left'
QR_RIGHT = 'right'
ALIGN_LEFT = 'left'
ALIGN_CENTER = 'center'

EMPHASIS_RATIO = 1.3     # first line size relative to the other lines
MIN_FONT_SIZE = 6        # pixels; smaller text is unreadable at 180 dpi
QR_GAP_MM = 1.5          # space between QR code and text


class LabelError(Exception):
    pass


@dataclass
class LabelSpec:
    lines: list = field(default_factory=list)
    qr_data: str = ''
    qr_position: str = QR_LEFT
    emphasize_first_line: bool = True
    align: str = ALIGN_LEFT
    length_mm: float = None   # fixed label length; None to fit the content
    font_path: str = None     # TrueType font; None for Pillow's built-in font
    bold_font_path: str = None


def _font(path, size):
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def _qr_image(data, height):
    qr = segno.make(data, error='l', boost_error=True)
    modules = qr.symbol_size(border=0)[0]
    scale = height // modules
    if scale < 1:
        raise LabelError(
            f'QR code ({modules}x{modules} modules) does not fit on the tape ({height} pixels). '
            f'Use a wider tape or shorter QR data.'
        )
    image = Image.new('1', (modules * scale, modules * scale), 1)
    draw = ImageDraw.Draw(image)
    for y, row in enumerate(qr.matrix):
        for x, dark in enumerate(row):
            if dark:
                draw.rectangle((x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1), fill=0)
    return image


class _TextBlock:

    def __init__(self, spec, base_size):
        self.lines = spec.lines
        self.fonts = []
        self.emboldens = []
        for i, _ in enumerate(self.lines):
            emphasized = i == 0 and spec.emphasize_first_line and len(self.lines) > 1
            size = round(base_size * EMPHASIS_RATIO) if emphasized else base_size
            if emphasized and spec.bold_font_path:
                self.fonts.append(_font(spec.bold_font_path, size))
                self.emboldens.append(0)
            else:
                self.fonts.append(_font(spec.font_path, size))
                # Fake bold for the built-in font, which has no bold variant: the text is
                # drawn again shifted right by this many pixels, thickening vertical stems
                self.emboldens.append(max(1, size // 25) if emphasized else 0)
        self.line_heights = [sum(font.getmetrics()) for font in self.fonts]
        self.line_widths = [
            round(font.getlength(line)) + embolden
            for font, line, embolden in zip(self.fonts, self.lines, self.emboldens)
        ]

    @property
    def height(self):
        return sum(self.line_heights)

    @property
    def width(self):
        return max(self.line_widths, default=0)

    def draw(self, draw, x, y, width, align):
        for line, font, embolden, line_width, line_height in zip(
            self.lines, self.fonts, self.emboldens, self.line_widths, self.line_heights
        ):
            dx = (width - line_width) // 2 if align == ALIGN_CENTER else 0
            for offset in range(embolden + 1):
                draw.text((x + dx + offset, y), line, font=font, fill=0)
            y += line_height


def _fit_text(spec, height, max_width=None):
    """Return the largest _TextBlock that fits within height (and max_width)."""
    best = None
    lo, hi = MIN_FONT_SIZE, height
    while lo <= hi:
        size = (lo + hi) // 2
        block = _TextBlock(spec, size)
        if block.height <= height and (max_width is None or block.width <= max_width):
            best = block
            lo = size + 1
        else:
            hi = size - 1
    if best is None:
        raise LabelError('Text does not fit on the label. Use fewer lines, a wider tape or a longer label.')
    return best


def render_label(spec, height):
    """
    Render a label for a tape with `height` printable pixels. Returns a mode '1'
    image whose width is the label length in dots (180 dpi).
    """
    if not spec.lines and not (spec.qr_data and spec.qr_position != QR_NONE):
        raise LabelError('The label has no content')

    qr = _qr_image(spec.qr_data, height) if spec.qr_data and spec.qr_position != QR_NONE else None
    gap = mm_to_dots(QR_GAP_MM) if qr and spec.lines else 0
    qr_width = qr.width + gap if qr else 0
    fixed_length = mm_to_dots(spec.length_mm) if spec.length_mm else None

    text = None
    if spec.lines:
        max_width = fixed_length - qr_width if fixed_length else None
        if max_width is not None and max_width <= 0:
            raise LabelError('The label is too short for its QR code')
        text = _fit_text(spec, height, max_width)

    content_width = qr_width + (text.width if text else 0)
    length = fixed_length or content_width
    if content_width > length:
        raise LabelError('The QR code does not fit within the label length')

    image = Image.new('1', (length, height), 1)
    draw = ImageDraw.Draw(image)
    draw.fontmode = '1'  # no anti-aliasing on a 1-bit print head

    # Text gets all space not taken by the QR code
    text_x = qr_width if qr and spec.qr_position == QR_LEFT else 0
    text_width = length - qr_width
    if qr:
        qr_x = 0 if spec.qr_position == QR_LEFT else length - qr.width
        image.paste(qr, (qr_x, (height - qr.height) // 2))
    if text:
        text.draw(draw, text_x, (height - text.height) // 2, text_width, spec.align)
    return image
