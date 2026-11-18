"""
Print strips of three labels with different cut settings, to find out how a printer
handles half cuts. Each label shows its variant and position, e.g. "V3 2/3".

Network printer (sent directly):
    python tools/cut_test.py --host 192.0.2.10

USB printer or other transport (writes one .bin file per variant to send raw):
    python tools/cut_test.py --out /tmp/cut-test --tape 12

Run it from the repository root in the NetBox image, e.g.:
    docker run --rm --entrypoint "" -v "$PWD":/src -w /src -e PYTHONPATH=/src:/opt/netbox/netbox \\
      netboxcommunity/netbox:v4.7.4 sh -c '
        uv pip install -q -p /opt/netbox/venv/bin/python segno &&
        /opt/netbox/venv/bin/python tools/cut_test.py --host 192.0.2.10'
"""
import argparse
import os

from netbox_asset_labels.layout import LabelSpec, QR_NONE, render_label
from netbox_asset_labels.ptouch import TAPES, CutSettings, PrinterConnection, _job, mm_to_dots

LABELS = 3

# (name, description, cut settings for page index i of n)
VARIANTS = (
    ('V1', 'auto cut off, half cut on', lambda i, n: CutSettings(auto_cut=False, half_cut=True)),
    ('V2', 'cut every 0, half cut on', lambda i, n: CutSettings(auto_cut=True, cut_every=0, half_cut=True)),
    ('V3', f'cut every {LABELS}, half cut on', lambda i, n: CutSettings(auto_cut=True, cut_every=n, half_cut=True)),
    ('V4', 'no cut-every, half cut on', lambda i, n: CutSettings(auto_cut=True, half_cut=True)),
    ('V5', 'cut every 1, half cut on, last off',
     lambda i, n: CutSettings(auto_cut=True, cut_every=1, half_cut=i < n - 1)),
    ('V6', f'cut every {LABELS}, half cut on, last off',
     lambda i, n: CutSettings(auto_cut=True, cut_every=n, half_cut=i < n - 1)),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--host', help='printer address (network printing)')
    parser.add_argument('--port', type=int, default=9100)
    parser.add_argument('--tape', type=float, help='tape width in mm (default: ask the printer)')
    parser.add_argument('--out', help='write .bin files to this directory instead of printing')
    parser.add_argument('--variants', help='comma-separated variants to run, e.g. V1,V3 (default: all)')
    args = parser.parse_args()
    if not args.host and not args.out:
        parser.error('give --host or --out')

    tape = None
    if args.tape:
        tape = next(t for t in TAPES.values() if t.width_mm == args.tape)
    elif args.host:
        with PrinterConnection(args.host, args.port) as printer:
            status = printer.request_status()
        if status is None or status.tape is None:
            parser.error('the printer did not report its tape; give --tape')
        tape = status.tape
    else:
        parser.error('give --tape with --out')

    selected = set(args.variants.upper().split(',')) if args.variants else None
    for name, description, settings in VARIANTS:
        if selected and name not in selected:
            continue
        images = [
            render_label(LabelSpec(lines=[f'{name} {i}/{LABELS}', description], qr_position=QR_NONE), tape.pins)
            for i in range(1, LABELS + 1)
        ]
        job = _job([(image, mm_to_dots(2)) for image in images], tape, settings)
        if args.out:
            os.makedirs(args.out, exist_ok=True)
            path = os.path.join(args.out, f'{name}.bin')
            with open(path, 'wb') as f:
                f.write(job)
            print(f'{name}: {description} -> {path}')
        else:
            with PrinterConnection(args.host, args.port) as printer:
                printer.send(job)
                printer.wait_for_completion(LABELS, timeout=20)
            print(f'{name}: {description} -> printed')


if __name__ == '__main__':
    main()
