"""
Raster driver for Brother P-touch printers with a 128-pin, 180 dpi print head
(PT-E550W, PT-P750W), printing over the network (raw TCP, port 9100).

Based on Brother's "Raster Command Reference PT-E550W/P750W/P710BT". This module
has no Django dependencies.
"""
import socket
import time
from dataclasses import dataclass
from functools import partial

from PIL import Image

__all__ = (
    'CUT_FULL',
    'CUT_NONE',
    'CUT_TAB',
    'DPI',
    'TAPES',
    'PrinterConnection',
    'PrinterError',
    'Status',
    'Tape',
    'encode_job',
    'mm_to_dots',
    'packbits',
    'parse_status',
)

DPI = 180
HEAD_PINS = 128
BYTES_PER_LINE = HEAD_PINS // 8

CUT_TAB = 'tab'     # cut after every label, with a half-cut peel tab in each label's margin
CUT_FULL = 'full'   # cut after every label
CUT_NONE = 'none'   # no cutting
# A strip (half cuts between labels, full cut at the end) is not supported yet: the
# PT-E550W turns half cuts into peel tabs whenever it also cuts every label. See
# tools/cut_test.py for finding the settings that produce a strip.

# Page position in the print information command (ESC i z n9)
PAGE_FIRST = 0
PAGE_MIDDLE = 1
PAGE_LAST = 2  # also used for single-page jobs


@dataclass(frozen=True)
class CutSettings:
    auto_cut: bool          # ESC i M bit 6
    cut_every: int = None   # ESC i A n; None to not send it
    half_cut: bool = False  # ESC i K bit 2


def _cut_settings(cut, index, count):
    """Cut settings for page `index` of `count` pages in a job."""
    if cut == CUT_NONE:
        return CutSettings(auto_cut=False)
    # With half cut on, the printer adds a peel tab to each label it cuts
    return CutSettings(auto_cut=True, cut_every=1, half_cut=cut == CUT_TAB)


@dataclass(frozen=True)
class Tape:
    code: int        # width as reported in status / sent in ESC i z (3.5 mm is reported as 4)
    width_mm: float  # physical tape width
    offset: int      # unused pins before the printable area
    pins: int        # printable pins (= label image height in pixels)

    @property
    def label(self):
        return f'{self.width_mm:g} mm'


TAPES = {
    tape.code: tape for tape in (
        Tape(4, 3.5, 52, 24),
        Tape(6, 6, 48, 32),
        Tape(9, 9, 39, 50),
        Tape(12, 12, 29, 70),
        Tape(18, 18, 8, 112),
        Tape(24, 24, 0, 128),
    )
}


def mm_to_dots(mm):
    return round(float(mm) * DPI / 25.4)


class PrinterError(Exception):
    pass


#
# Job encoding
#

def packbits(data):
    """TIFF PackBits compression, as required by the raster 'G' command."""
    out = bytearray()
    i, n = 0, len(data)
    while i < n:
        run = 1
        while i + run < n and run < 128 and data[i + run] == data[i]:
            run += 1
        if run > 1:
            out += bytes(((257 - run) & 0xFF, data[i]))
            i += run
            continue
        start = i
        i += 1
        while i < n and i - start < 128 and not (i + 1 < n and data[i] == data[i + 1]):
            i += 1
        out.append(i - start - 1)
        out += data[start:i]
    return bytes(out)


def _raster_lines(image, tape):
    """Yield one 16-byte raster line per image column; dark pixels print."""
    if image.height != tape.pins:
        raise ValueError(f'Image height {image.height} does not match {tape.label} tape ({tape.pins} pixels)')
    canvas = Image.new('L', (image.width, HEAD_PINS), 255)
    canvas.paste(image.convert('L'), (0, tape.offset))
    # Threshold so printed (dark) dots are 1 bits, then transpose so each column becomes a row of pins
    dots = canvas.point(lambda v: 255 if v < 128 else 0, mode='1')
    data = dots.transpose(Image.Transpose.TRANSPOSE).tobytes()
    for x in range(image.width):
        yield data[x * BYTES_PER_LINE:(x + 1) * BYTES_PER_LINE]


def _page(image, tape, margin_dots, position, cut):
    lines = image.width
    out = bytearray()
    # Print information: recovery on, media width valid; width, line count, page position
    out += b'\x1biz' + bytes((0x84, 0x00, tape.code, 0x00)) + lines.to_bytes(4, 'little') + bytes((position, 0x00))
    # Various mode: auto cut; cut every n labels
    out += b'\x1biM' + bytes((0x40 if cut.auto_cut else 0x00,))
    if cut.cut_every is not None:
        out += b'\x1biA' + bytes((cut.cut_every,))
    # Advanced mode: half cut, no chain printing (feed and cut after the last label)
    out += b'\x1biK' + bytes(((0x04 if cut.half_cut else 0x00) | 0x08,))
    out += b'\x1bid' + margin_dots.to_bytes(2, 'little')
    out += b'M\x02'  # TIFF compression; the E550W does not cut without it
    for line in _raster_lines(image, tape):
        if not any(line):
            out += b'Z'
        else:
            packed = packbits(line)
            out += b'G' + len(packed).to_bytes(2, 'little') + packed
    out += b'\x1a' if position == PAGE_LAST else b'\x0c'
    return bytes(out)


def _job(pages, tape, cut_settings):
    """One print job; cut_settings(index, count) returns the CutSettings for each page."""
    out = bytearray(b'\x00' * 100 + b'\x1b@' + b'\x1bia\x01')  # invalidate, initialize, raster mode
    for i, (image, margin_dots) in enumerate(pages):
        if i == len(pages) - 1:
            position = PAGE_LAST
        else:
            position = PAGE_FIRST if i == 0 else PAGE_MIDDLE
        out += _page(image, tape, margin_dots, position, cut_settings(i, len(pages)))
    return bytes(out)


def encode_job(images, tape, cut=CUT_TAB, margin_mm=2):
    """
    Encode label images (mode '1' or 'L', height == tape.pins, width == label length
    in dots) into printer data. margin_mm is the blank tape before and after each
    label, either one value or one per image. For full cuts without a peel tab, each
    label is sent as its own job.
    """
    if not images:
        raise ValueError('No labels to print')
    margins = margin_mm if isinstance(margin_mm, (list, tuple)) else [margin_mm] * len(images)
    pages = [(image, mm_to_dots(margin)) for image, margin in zip(images, margins, strict=True)]
    settings = partial(_cut_settings, cut)
    if cut == CUT_FULL:
        return b''.join(_job([page], tape, settings) for page in pages)
    return _job(pages, tape, settings)


#
# Status
#

STATUS_LENGTH = 32
STATUS_REPLY = 0x00
STATUS_COMPLETED = 0x01
STATUS_ERROR = 0x02

ERRORS_1 = {
    0x01: 'No tape installed',
    0x02: 'End of tape',
    0x04: 'Cutter jam',
    0x10: 'Printer in use',
    0x40: 'High-voltage adapter',
}
ERRORS_2 = {
    0x01: 'Wrong tape installed',
    0x02: 'Expansion buffer full',
    0x04: 'Communication error',
    0x08: 'Communication buffer full',
    0x10: 'Cover open',
    0x20: 'Overheating',
    0x40: 'Black marking not detected',
    0x80: 'System error',
}
MEDIA_TYPES = {
    0x00: 'No tape',
    0x01: 'Laminated tape',
    0x03: 'Non-laminated tape',
    0x11: 'Heat-shrink tube (2:1)',
    0x17: 'Heat-shrink tube (3:1)',
    0xFF: 'Incompatible tape',
}


@dataclass(frozen=True)
class Status:
    error1: int
    error2: int
    media_width: int
    media_type: int
    status_type: int

    @property
    def errors(self):
        return [msg for bit, msg in ERRORS_1.items() if self.error1 & bit] + \
               [msg for bit, msg in ERRORS_2.items() if self.error2 & bit]

    @property
    def tape(self):
        return TAPES.get(self.media_width)

    @property
    def media_description(self):
        return MEDIA_TYPES.get(self.media_type, f'Unknown tape type ({self.media_type:#04x})')


def parse_status(data):
    if len(data) != STATUS_LENGTH or data[0] != 0x80 or data[1] != 0x20:
        raise PrinterError('Invalid status reply from printer')
    return Status(
        error1=data[8],
        error2=data[9],
        media_width=data[10],
        media_type=data[11],
        status_type=data[18],
    )


#
# Network connection
#

class PrinterConnection:
    """
    A raw TCP connection to a printer. Status replies are optional: not every
    printer/firmware answers status requests over the network, so methods that
    read return None on timeout instead of failing.

        with PrinterConnection('192.0.2.10') as printer:
            status = printer.request_status()
            printer.send(encode_job(images, tape))
            printer.wait_for_completion(len(images))
    """

    def __init__(self, host, port=9100, timeout=5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = None
        self._buffer = b''

    def __enter__(self):
        try:
            self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        except OSError as e:
            raise PrinterError(f'Cannot connect to printer at {self.host}:{self.port}: {e}') from e
        return self

    def __exit__(self, *exc):
        self.sock.close()

    def send(self, data):
        try:
            self.sock.sendall(data)
        except OSError as e:
            raise PrinterError(f'Sending to printer failed: {e}') from e

    def _read_status(self, timeout):
        deadline = time.monotonic() + timeout
        while len(self._buffer) < STATUS_LENGTH:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            self.sock.settimeout(remaining)
            try:
                chunk = self.sock.recv(1024)
            except TimeoutError:
                return None
            except OSError as e:
                raise PrinterError(f'Reading from printer failed: {e}') from e
            if not chunk:
                return None
            self._buffer += chunk
        data, self._buffer = self._buffer[:STATUS_LENGTH], self._buffer[STATUS_LENGTH:]
        return parse_status(data)

    def request_status(self, timeout=2.0):
        """Return the printer's Status, or None if it does not answer."""
        self.send(b'\x00' * 100 + b'\x1b@' + b'\x1biS')
        return self._read_status(timeout)

    def wait_for_completion(self, pages, timeout=10.0):
        """
        Wait for the printer to report `pages` printed labels. Return the last Status,
        or None if the printer stops answering. Raise PrinterError on a printer error.
        """
        completed = 0
        status = None
        deadline = time.monotonic() + timeout + 3 * pages
        while completed < pages:
            status = self._read_status(max(deadline - time.monotonic(), 0))
            if status is None:
                return None
            if status.status_type == STATUS_ERROR or status.errors:
                raise PrinterError(', '.join(status.errors) or 'Printer reported an error')
            if status.status_type == STATUS_COMPLETED:
                completed += 1
        return status
