import base64

from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.generic import View

from dcim.filtersets import DeviceFilterSet, ModuleFilterSet
from dcim.models import Device, Module
from extras.ui.panels import CustomFieldsPanel, TagsPanel
from netbox.object_actions import AddObject, BulkDelete, BulkExport
from netbox.ui import attrs, layout, panels
from netbox.views import generic
from utilities.request import safe_for_redirect
from utilities.views import ConditionalLoginRequiredMixin, register_model_view

from . import filtersets, forms, tables
from .choices import AppliesToChoices, FileFormatChoices, PrintMethodChoices
from .models import LabelPrinter, LabelTemplate
from .printing import (
    LabelError, PrinterError, build_labels, encode_labels, get_netbox_url, labels_pdf, labels_png, preview_png,
    print_labels, printer_status,
)
from .ptouch import ERRORS_1, ERRORS_2, MEDIA_TYPES, TAPES

PRINTABLE_MODELS = {
    'device': (Device, DeviceFilterSet),
    'module': (Module, ModuleFilterSet),
}
MAX_LABELS = 200
PRINT_PARAMS = (
    'object_type', 'pk', 'method', 'printer', 'cut_mode', 'file_format', 'template', 'copies', 'tape', 'return_url',
    'csrfmiddlewaretoken',
)
# Printer protocol details needed by the browser for USB printing
USB_CONFIG = {
    'tapes': {tape.code: tape.label for tape in TAPES.values()},
    'errors1': ERRORS_1,
    'errors2': ERRORS_2,
    'mediaTypes': MEDIA_TYPES,
    'messages': {
        'connecting': _('Connecting to printer…'),
        'rendering': _('Rendering labels…'),
        'printing': _('Printing…'),
        'printed': _('Printed {count} label(s) on {tape} tape'),
        'sent': _('Sent {count} label(s) on {tape} tape'),
        'sentNoStatus': _('Sent {count} label(s) on {tape} tape (the printer did not report its loaded tape)'),
        'noInterface': _('This USB device has no printer interface. Is the printer in P-touch Editor Lite mode?'),
        'invalidStatus': _('Invalid status reply from printer'),
        'unsupportedTape': _('Unsupported tape loaded: {width} mm {type}'),
        'printerError': _('Printer reported an error'),
        'noPrinter': _('No printer selected.'),
        'inUse': _('The printer may be in use by another program or driver.'),
    },
}


def label_preview(label):
    """A data: URI of the label image, for use in an <img> tag."""
    return 'data:image/png;base64,' + base64.b64encode(preview_png(label)).decode()


#
# Label printers
#

class LabelPrinterPanel(panels.ObjectAttributesPanel):
    name = attrs.TextAttr('name')
    printer_model = attrs.ChoiceAttr('printer_model', label=_('Model'))
    host = attrs.TextAttr('host', style='font-monospace', copy_button=True)
    port = attrs.NumericAttr('port')
    tape_width = attrs.ChoiceAttr('tape_width', label=_('Configured tape'))
    cut_mode = attrs.ChoiceAttr('cut_mode')
    description = attrs.TextAttr('description')


@register_model_view(LabelPrinter, 'list', path='', detail=False)
class LabelPrinterListView(generic.ObjectListView):
    queryset = LabelPrinter.objects.all()
    filterset = filtersets.LabelPrinterFilterSet
    filterset_form = forms.LabelPrinterFilterForm
    table = tables.LabelPrinterTable
    actions = (AddObject, BulkExport, BulkDelete)


@register_model_view(LabelPrinter)
class LabelPrinterView(generic.ObjectView):
    queryset = LabelPrinter.objects.all()
    template_name = 'generic/object.html'
    layout = layout.SimpleLayout(
        left_panels=[LabelPrinterPanel(), TagsPanel()],
        right_panels=[
            panels.TemplatePanel('netbox_asset_labels/panels/printer_status.html', title=_('Status')),
            CustomFieldsPanel(),
            panels.CommentsPanel(),
        ],
    )


@register_model_view(LabelPrinter, 'status')
class LabelPrinterStatusView(generic.ObjectView):
    """HTML fragment with the printer's live status, loaded into the printer page with HTMX."""
    queryset = LabelPrinter.objects.all()
    template_name = 'netbox_asset_labels/inc/printer_status.html'

    def get(self, request, pk):
        printer = get_object_or_404(self.queryset.restrict(request.user, 'view'), pk=pk)
        context = {'object': printer}
        try:
            context['status'] = printer_status(printer)
        except PrinterError as e:
            context['error'] = e
        return render(request, self.template_name, context)


@register_model_view(LabelPrinter, 'add', detail=False)
@register_model_view(LabelPrinter, 'edit')
class LabelPrinterEditView(generic.ObjectEditView):
    queryset = LabelPrinter.objects.all()
    form = forms.LabelPrinterForm


@register_model_view(LabelPrinter, 'delete')
class LabelPrinterDeleteView(generic.ObjectDeleteView):
    queryset = LabelPrinter.objects.all()


@register_model_view(LabelPrinter, 'bulk_delete', path='delete', detail=False)
class LabelPrinterBulkDeleteView(generic.BulkDeleteView):
    queryset = LabelPrinter.objects.all()
    filterset = filtersets.LabelPrinterFilterSet
    table = tables.LabelPrinterTable


#
# Label templates
#

class LabelTemplatePanel(panels.ObjectAttributesPanel):
    name = attrs.TextAttr('name')
    weight = attrs.NumericAttr('weight')
    description = attrs.TextAttr('description')
    qr_position = attrs.ChoiceAttr('qr_position', label=_('QR code'))
    emphasize_first_line = attrs.BooleanAttr('emphasize_first_line')
    text_align = attrs.ChoiceAttr('text_align', label=_('Text alignment'))
    length_mm = attrs.TextAttr('length_mm', label=_('Length'), format_string='{} mm')
    margin_mm = attrs.TextAttr('margin_mm', label=_('Margin'), format_string='{} mm')


class LabelTemplateAssignmentPanel(panels.ObjectAttributesPanel):
    title = _('Assignment')
    applies_to = attrs.ChoiceAttr('applies_to')
    manufacturers = attrs.RelatedObjectListAttr('manufacturers', linkify=True)
    device_types = attrs.RelatedObjectListAttr('device_types', linkify=True)
    module_types = attrs.RelatedObjectListAttr('module_types', linkify=True)
    roles = attrs.RelatedObjectListAttr('roles', linkify=True)
    platforms = attrs.RelatedObjectListAttr('platforms', linkify=True)
    sites = attrs.RelatedObjectListAttr('sites', linkify=True)
    locations = attrs.RelatedObjectListAttr('locations', linkify=True)
    tenants = attrs.RelatedObjectListAttr('tenants', linkify=True)


@register_model_view(LabelTemplate, 'list', path='', detail=False)
class LabelTemplateListView(generic.ObjectListView):
    queryset = LabelTemplate.objects.all()
    filterset = filtersets.LabelTemplateFilterSet
    filterset_form = forms.LabelTemplateFilterForm
    table = tables.LabelTemplateTable
    actions = (AddObject, BulkExport, BulkDelete)


@register_model_view(LabelTemplate)
class LabelTemplateView(generic.ObjectView):
    queryset = LabelTemplate.objects.all()
    template_name = 'generic/object.html'
    layout = layout.SimpleLayout(
        left_panels=[
            LabelTemplatePanel(),
            LabelTemplateAssignmentPanel(),
            TagsPanel(),
            CustomFieldsPanel(),
        ],
        right_panels=[
            panels.TemplatePanel('netbox_asset_labels/panels/template_preview.html', title=_('Preview')),
            panels.TextCodePanel('text_template', title=_('Text')),
            panels.TextCodePanel('qr_template', title=_('QR code data')),
            panels.CommentsPanel(),
        ],
    )

    def get_extra_context(self, request, instance):
        form = forms.LabelPreviewForm(request.GET or None)
        obj = None
        tape = TAPES[12]
        if form.is_valid():
            obj = form.cleaned_data['device'] or form.cleaned_data['module']
            tape = TAPES[form.cleaned_data['tape']]
        if obj is None:
            # Preview with the first object of the kind the template applies to
            model = Module if instance.applies_to == AppliesToChoices.MODULE else Device
            obj = model.objects.restrict(request.user, 'view').first()

        context = {'preview_form': form, 'preview_object': obj, 'preview_tape': tape}
        if obj is not None:
            try:
                label, = build_labels([obj], tape, get_netbox_url(request), template=instance)
                context['preview'] = label_preview(label)
            except LabelError as e:
                context['preview_error'] = e
        return context


@register_model_view(LabelTemplate, 'add', detail=False)
@register_model_view(LabelTemplate, 'edit')
class LabelTemplateEditView(generic.ObjectEditView):
    queryset = LabelTemplate.objects.all()
    form = forms.LabelTemplateForm


@register_model_view(LabelTemplate, 'delete')
class LabelTemplateDeleteView(generic.ObjectDeleteView):
    queryset = LabelTemplate.objects.all()


@register_model_view(LabelTemplate, 'bulk_delete', path='delete', detail=False)
class LabelTemplateBulkDeleteView(generic.BulkDeleteView):
    queryset = LabelTemplate.objects.all()
    filterset = filtersets.LabelTemplateFilterSet
    table = tables.LabelTemplateTable


#
# Printing
#

class LabelPrintView(ConditionalLoginRequiredMixin, View):
    """
    Preview and print labels for devices or modules. Objects are selected with
    `object_type` (device or module) and either `pk` (repeated) or that model's
    list filters, e.g. ?object_type=device&site_id=1.
    """
    template_name = 'netbox_asset_labels/print.html'

    def get_objects(self, request, data):
        try:
            model, filterset = PRINTABLE_MODELS[data.get('object_type')]
        except KeyError:
            raise Http404(_('Labels can be printed for devices and modules'))
        queryset = model.objects.restrict(request.user, 'view')
        if pks := data.getlist('pk'):
            queryset = queryset.filter(pk__in=pks)
        else:
            filters = data.copy()
            for param in PRINT_PARAMS:
                filters.pop(param, None)
            queryset = filterset(filters, queryset, request=request).qs
        return model, list(queryset[:MAX_LABELS + 1])

    def get_return_url(self, request, objects):
        return_url = request.GET.get('return_url') or request.POST.get('return_url')
        if return_url and safe_for_redirect(return_url):
            return return_url
        if len(objects) == 1:
            return objects[0].get_absolute_url()
        return '/'

    def get_tape(self, form):
        """The tape to render for: chosen in the form, else the (first) network printer's."""
        data = form.cleaned_data if form.is_bound and form.is_valid() else {}
        if data.get('tape'):
            return TAPES[data['tape']]
        printer = data.get('printer') or form.fields['printer'].queryset.first()
        return TAPES[printer.tape_width] if printer else TAPES[12]

    def render_page(self, request, model, objects, form):
        tape = self.get_tape(form)
        template = form.cleaned_data.get('template') if form.is_bound and form.is_valid() else None

        rows = []
        netbox_url = get_netbox_url(request)
        for obj in objects[:MAX_LABELS]:
            row = {'object': obj}
            try:
                label, = build_labels([obj], tape, netbox_url, template=template)
                row.update(template=label.template, preview=label_preview(label))
            except LabelError as e:
                row['error'] = e
            rows.append(row)

        return render(request, self.template_name, {
            'model': model,
            'object_type': model._meta.model_name,
            'rows': rows,
            'too_many': len(objects) > MAX_LABELS,
            'max_labels': MAX_LABELS,
            'form': form,
            'tape': tape,
            'usb_config': USB_CONFIG,
            'return_url': self.get_return_url(request, objects),
        })

    def get_form(self, request, data=None):
        form = forms.LabelPrintForm(data, printers=LabelPrinter.objects.restrict(request.user, 'print'))
        form.fields['template'].queryset = LabelTemplate.objects.restrict(request.user, 'view')
        return form

    def get(self, request):
        model, objects = self.get_objects(request, request.GET)
        # Bind the form only when the preview is being updated
        data = request.GET if 'method' in request.GET else None
        return self.render_page(request, model, objects, self.get_form(request, data))

    def post(self, request):
        model, objects = self.get_objects(request, request.POST)
        form = self.get_form(request, request.POST)
        usb = request.POST.get('method') == PrintMethodChoices.USB

        error = None
        if not form.is_valid():
            error = '; '.join(f'{field}: {", ".join(errors)}' for field, errors in form.errors.items())
        elif not objects:
            error = _('No objects selected')
        elif len(objects) > MAX_LABELS:
            error = _('Select at most {count} objects').format(count=MAX_LABELS)
        if error:
            if usb:
                return HttpResponse(error, status=400, content_type='text/plain; charset=utf-8')
            if form.is_valid():
                messages.error(request, error)
            return self.render_page(request, model, objects, form)

        data = form.cleaned_data
        if data['method'] == PrintMethodChoices.NETWORK:
            return self.print_network(request, model, objects, form)

        tape = self.get_tape(form)
        try:
            labels = build_labels(objects, tape, get_netbox_url(request), template=data['template'])
        except LabelError as e:
            if usb:
                return HttpResponse(str(e), status=400, content_type='text/plain; charset=utf-8')
            messages.error(request, str(e))
            return self.render_page(request, model, objects, form)

        if usb:
            # Printer data for the browser to send to the USB printer (see inc/usb_print.html)
            labels = [label for label in labels for _ in range(data['copies'])]
            response = HttpResponse(
                encode_labels(labels, tape, data['cut_mode']), content_type='application/octet-stream',
            )
            response['X-Label-Count'] = len(labels)
            return response

        if data['file_format'] == FileFormatChoices.PDF:
            labels = [label for label in labels for _ in range(data['copies'])]
            filename, content_type, content = 'labels.pdf', 'application/pdf', labels_pdf(labels, tape)
        else:
            filename, content_type, content = labels_png(labels, tape)
        response = HttpResponse(content, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    def print_network(self, request, model, objects, form):
        printer = form.cleaned_data['printer']
        try:
            result = print_labels(
                printer,
                objects,
                get_netbox_url(request),
                copies=form.cleaned_data['copies'],
                template=form.cleaned_data['template'],
            )
        except (LabelError, PrinterError) as e:
            messages.error(request, _('{printer}: {error}').format(printer=printer, error=e))
            return self.render_page(request, model, objects, form)

        messages.success(request, _('{printer}: {result}').format(printer=printer, result=result))
        return redirect(self.get_return_url(request, objects))
