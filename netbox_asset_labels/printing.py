"""
Rendering of labels for NetBox objects, and their output: sent to a LabelPrinter,
encoded as printer data for a USB printer (sent by the browser), or as files.
"""
import io
import zipfile
from dataclasses import dataclass

from django.utils.text import slugify
from django.utils.translation import gettext as _
from jinja2 import TemplateError
from PIL import Image

from dcim.models import Device, Module
from netbox.plugins.utils import get_plugin_config
from utilities.jinja2 import render_jinja2

from .choices import QRPositionChoices
from .layout import LabelError, LabelSpec, render_label
from .models import LabelTemplate
from .ptouch import TAPES, PrinterConnection, PrinterError, encode_job, mm_to_dots

__all__ = (
    'LabelError',
    'PrintResult',
    'PrinterError',
    'build_labels',
    'encode_labels',
    'get_netbox_url',
    'labels_pdf',
    'labels_png',
    'preview_png',
    'print_labels',
    'printer_status',
    'template_for',
)


def _setting(name):
    return get_plugin_config('netbox_asset_labels', name)


def get_netbox_url(request=None):
    """Base URL for links in labels: the netbox_url setting, else the request's host."""
    url = _setting('netbox_url')
    if not url and request is not None:
        url = request.build_absolute_uri('/')
    return (url or '').rstrip('/')


def template_for(obj):
    """The best matching LabelTemplate for obj, or an unsaved default template."""
    return LabelTemplate.objects.for_object(obj).first() or LabelTemplate(name=_('Default'))


def template_context(obj, netbox_url):
    device = obj if isinstance(obj, Device) else obj.device
    return {
        'object': obj,
        'device': device,
        'module': obj if isinstance(obj, Module) else None,
        'site': device.site,
        'location': device.location,
        'rack': device.rack,
        'tenant': device.tenant,
        'role': device.role,
        'url': f'{netbox_url}{obj.get_absolute_url()}',
    }


def label_spec(template, obj, netbox_url):
    context = template_context(obj, netbox_url)
    try:
        text = render_jinja2(template.text_template, context) if template.text_template else ''
        qr_data = ''
        if template.qr_position != QRPositionChoices.NONE and template.qr_template:
            qr_data = render_jinja2(template.qr_template, context).strip()
    except TemplateError as e:
        raise LabelError(_('Error in template "{template}": {error}').format(template=template, error=e))
    return LabelSpec(
        lines=[line.strip() for line in text.splitlines() if line.strip()],
        qr_data=qr_data,
        qr_position=template.qr_position,
        emphasize_first_line=template.emphasize_first_line,
        align=template.text_align,
        length_mm=float(template.length_mm) if template.length_mm else None,
        font_path=_setting('font_path'),
        bold_font_path=_setting('bold_font_path'),
    )


@dataclass
class Label:
    obj: object
    template: LabelTemplate
    image: Image.Image


def build_labels(objects, tape, netbox_url, template=None):
    """
    Render a Label for each object, using `template` or each object's best matching
    template. Raises LabelError listing every object that could not be rendered.
    """
    labels, errors = [], []
    for obj in objects:
        obj_template = template or template_for(obj)
        try:
            image = render_label(label_spec(obj_template, obj, netbox_url), tape.pins)
        except LabelError as e:
            errors.append(f'{obj}: {e}')
            continue
        labels.append(Label(obj, obj_template, image))
    if errors:
        raise LabelError('; '.join(errors))
    return labels


def preview_png(label, scale=2):
    """A PNG of the label, enlarged for display on screen."""
    image = label.image.convert('L')
    image = image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


def _tape_image(label, tape):
    """The label on a canvas of the full tape width plus its margins, at 180 dpi."""
    margin = mm_to_dots(label.template.margin_mm)
    canvas = Image.new('1', (label.image.width + 2 * margin, mm_to_dots(tape.width_mm)), 1)
    canvas.paste(label.image, (margin, (canvas.height - label.image.height) // 2))
    return canvas


def labels_pdf(labels, tape):
    """A PDF with one page per label, each page the size of the label on the tape."""
    pages = [_tape_image(label, tape) for label in labels]
    buffer = io.BytesIO()
    pages[0].save(buffer, format='PDF', resolution=180, save_all=True, append_images=pages[1:])
    return buffer.getvalue()


def labels_png(labels, tape):
    """
    Return (filename, content type, data): one PNG at 180 dpi, or a ZIP of PNGs named
    after the objects when there are several labels.
    """
    def png(label):
        buffer = io.BytesIO()
        _tape_image(label, tape).save(buffer, format='PNG', dpi=(180, 180))
        return buffer.getvalue()

    def name(label):
        return slugify(str(label.obj)) or f'label-{label.obj.pk}'

    if len(labels) == 1:
        return f'{name(labels[0])}.png', 'image/png', png(labels[0])
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        used = set()
        for label in labels:
            filename = name(label)
            if filename in used:
                filename = f'{filename}-{label.obj.pk}'
            used.add(filename)
            archive.writestr(f'{filename}.png', png(label))
    return 'labels.zip', 'application/zip', buffer.getvalue()


def encode_labels(labels, tape, cut_mode):
    """Printer data for labels, e.g. for sending to a USB printer from the browser."""
    return encode_job(
        [label.image for label in labels],
        tape,
        cut=cut_mode,
        margin_mm=[float(label.template.margin_mm) for label in labels],
    )


def printer_status(printer):
    """The printer's reported Status, or None if it does not answer status requests."""
    with PrinterConnection(printer.host, printer.port, timeout=_setting('printer_timeout')) as connection:
        return connection.request_status()


@dataclass
class PrintResult:
    count: int
    tape: object
    tape_detected: bool
    confirmed: bool

    def __str__(self):
        message = _('Sent {count} label(s) on {tape} tape').format(count=self.count, tape=self.tape.label)
        if not self.tape_detected:
            message += _(' (tape width not reported by the printer; using the configured width)')
        elif self.confirmed:
            message = _('Printed {count} label(s) on {tape} tape').format(count=self.count, tape=self.tape.label)
        return message


def print_labels(printer, objects, netbox_url, copies=1, template=None):
    """
    Print labels for objects on a LabelPrinter. The labels are rendered for the tape
    the printer reports, falling back to the printer's configured tape width.
    Raises PrinterError or LabelError.
    """
    timeout = _setting('printer_timeout')
    with PrinterConnection(printer.host, printer.port, timeout=timeout) as connection:
        status = connection.request_status()
        if status is not None:
            if status.errors:
                raise PrinterError(', '.join(status.errors))
            if status.tape is None:
                raise PrinterError(
                    _('Unsupported tape loaded: {width} mm {type}').format(
                        width=status.media_width, type=status.media_description
                    )
                )
            tape = status.tape
        else:
            tape = TAPES[printer.tape_width]

        labels = [label for label in build_labels(objects, tape, netbox_url, template) for _ in range(copies)]
        connection.send(encode_labels(labels, tape, printer.cut_mode))
        confirmed = status is not None and connection.wait_for_completion(len(labels), timeout) is not None

    return PrintResult(count=len(labels), tape=tape, tape_detected=status is not None, confirmed=confirmed)
