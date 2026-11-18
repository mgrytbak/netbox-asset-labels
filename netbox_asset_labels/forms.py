from django import forms
from django.utils.translation import gettext_lazy as _

from dcim.models import Device, DeviceRole, DeviceType, Location, Manufacturer, Module, ModuleType, Platform, Site
from netbox.forms import PrimaryModelFilterSetForm, PrimaryModelForm
from tenancy.models import Tenant
from utilities.forms.fields import DynamicModelChoiceField, DynamicModelMultipleChoiceField, TagFilterField
from utilities.forms.rendering import FieldSet
from utilities.forms.utils import add_blank_choice

from .choices import (
    AppliesToChoices, CutModeChoices, FileFormatChoices, PrinterModelChoices, PrintMethodChoices, QRPositionChoices,
    TapeWidthChoices, TextAlignChoices,
)
from .models import LabelPrinter, LabelTemplate

__all__ = (
    'LabelPreviewForm',
    'LabelPrintForm',
    'LabelPrinterFilterForm',
    'LabelPrinterForm',
    'LabelTemplateFilterForm',
    'LabelTemplateForm',
)

TEMPLATE_HELP = _(
    'Jinja2 template. Available variables: <code>object</code> (the device or module), <code>device</code>, '
    '<code>module</code>, <code>site</code>, <code>location</code>, <code>rack</code>, <code>tenant</code>, '
    '<code>role</code> and <code>url</code> (absolute URL of the object).'
)


#
# Printers
#

class LabelPrinterForm(PrimaryModelForm):
    fieldsets = (
        FieldSet('name', 'printer_model', 'description', 'tags', name=_('Printer')),
        FieldSet('host', 'port', name=_('Connection')),
        FieldSet('tape_width', 'cut_mode', name=_('Printing')),
    )

    class Meta:
        model = LabelPrinter
        fields = (
            'name', 'printer_model', 'host', 'port', 'tape_width', 'cut_mode', 'description', 'owner', 'comments',
            'tags',
        )


class LabelPrinterFilterForm(PrimaryModelFilterSetForm):
    model = LabelPrinter
    fieldsets = (
        FieldSet('q', 'filter_id', 'tag'),
        FieldSet('printer_model', 'tape_width', 'cut_mode', name=_('Printer')),
        FieldSet('owner_group_id', 'owner_id', name=_('Ownership')),
    )
    printer_model = forms.MultipleChoiceField(label=_('Model'), choices=PrinterModelChoices, required=False)
    tape_width = forms.MultipleChoiceField(label=_('Tape width'), choices=TapeWidthChoices, required=False)
    cut_mode = forms.MultipleChoiceField(label=_('Cut mode'), choices=CutModeChoices, required=False)
    tag = TagFilterField(model)


#
# Templates
#

class LabelTemplateForm(PrimaryModelForm):
    manufacturers = DynamicModelMultipleChoiceField(
        label=_('Manufacturers'), queryset=Manufacturer.objects.all(), required=False,
    )
    device_types = DynamicModelMultipleChoiceField(
        label=_('Device types'), queryset=DeviceType.objects.all(), required=False,
        query_params={'manufacturer_id': '$manufacturers'},
    )
    module_types = DynamicModelMultipleChoiceField(
        label=_('Module types'), queryset=ModuleType.objects.all(), required=False,
        query_params={'manufacturer_id': '$manufacturers'},
    )
    roles = DynamicModelMultipleChoiceField(
        label=_('Device roles'), queryset=DeviceRole.objects.all(), required=False,
    )
    platforms = DynamicModelMultipleChoiceField(
        label=_('Platforms'), queryset=Platform.objects.all(), required=False,
    )
    sites = DynamicModelMultipleChoiceField(
        label=_('Sites'), queryset=Site.objects.all(), required=False,
    )
    locations = DynamicModelMultipleChoiceField(
        label=_('Locations'), queryset=Location.objects.all(), required=False,
        query_params={'site_id': '$sites'},
    )
    tenants = DynamicModelMultipleChoiceField(
        label=_('Tenants'), queryset=Tenant.objects.all(), required=False,
    )

    fieldsets = (
        FieldSet('name', 'weight', 'description', 'tags', name=_('Template')),
        FieldSet(
            'applies_to', 'manufacturers', 'device_types', 'module_types', 'roles', 'platforms', 'sites',
            'locations', 'tenants', name=_('Assignment'),
        ),
        FieldSet(
            'text_template', 'emphasize_first_line', 'text_align', 'qr_position', 'qr_template', name=_('Content'),
        ),
        FieldSet('length_mm', 'margin_mm', name=_('Size')),
    )

    class Meta:
        model = LabelTemplate
        fields = (
            'name', 'weight', 'applies_to', 'manufacturers', 'device_types', 'module_types', 'roles', 'platforms',
            'sites', 'locations', 'tenants', 'text_template', 'emphasize_first_line', 'text_align', 'qr_position',
            'qr_template', 'length_mm', 'margin_mm', 'description', 'owner', 'comments', 'tags',
        )
        widgets = {
            'text_template': forms.Textarea(attrs={'class': 'font-monospace', 'rows': 4}),
            'qr_template': forms.Textarea(attrs={'class': 'font-monospace', 'rows': 2}),
        }
        help_texts = {
            'text_template': TEMPLATE_HELP,
            'qr_template': TEMPLATE_HELP,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['applies_to'].help_text = _(
            'Empty assignment fields match any object. Device types only match devices and module types only '
            'modules; all other fields are taken from the (parent) device.'
        )


class LabelTemplateFilterForm(PrimaryModelFilterSetForm):
    model = LabelTemplate
    fieldsets = (
        FieldSet('q', 'filter_id', 'tag'),
        FieldSet('applies_to', 'qr_position', name=_('Template')),
        FieldSet(
            'manufacturer_id', 'device_type_id', 'module_type_id', 'role_id', 'platform_id', 'site_id',
            'location_id', 'tenant_id', name=_('Assignment'),
        ),
        FieldSet('owner_group_id', 'owner_id', name=_('Ownership')),
    )
    applies_to = forms.MultipleChoiceField(label=_('Applies to'), choices=AppliesToChoices, required=False)
    qr_position = forms.MultipleChoiceField(label=_('QR code'), choices=QRPositionChoices, required=False)
    manufacturer_id = DynamicModelMultipleChoiceField(
        label=_('Manufacturer'), queryset=Manufacturer.objects.all(), required=False,
    )
    device_type_id = DynamicModelMultipleChoiceField(
        label=_('Device type'), queryset=DeviceType.objects.all(), required=False,
    )
    module_type_id = DynamicModelMultipleChoiceField(
        label=_('Module type'), queryset=ModuleType.objects.all(), required=False,
    )
    role_id = DynamicModelMultipleChoiceField(label=_('Device role'), queryset=DeviceRole.objects.all(), required=False)
    platform_id = DynamicModelMultipleChoiceField(label=_('Platform'), queryset=Platform.objects.all(), required=False)
    site_id = DynamicModelMultipleChoiceField(label=_('Site'), queryset=Site.objects.all(), required=False)
    location_id = DynamicModelMultipleChoiceField(label=_('Location'), queryset=Location.objects.all(), required=False)
    tenant_id = DynamicModelMultipleChoiceField(label=_('Tenant'), queryset=Tenant.objects.all(), required=False)
    tag = TagFilterField(model)


#
# Printing
#

class LabelPreviewForm(forms.Form):
    """Pick a sample object and tape to preview a template with."""
    device = DynamicModelChoiceField(label=_('Device'), queryset=Device.objects.all(), required=False)
    module = DynamicModelChoiceField(label=_('Module'), queryset=Module.objects.all(), required=False)
    tape = forms.TypedChoiceField(label=_('Tape'), choices=TapeWidthChoices, coerce=int, initial=12)


class LabelPrintForm(forms.Form):
    method = forms.ChoiceField(label=_('Output'), choices=PrintMethodChoices, initial=PrintMethodChoices.NETWORK)
    printer = forms.ModelChoiceField(
        label=_('Printer'), queryset=LabelPrinter.objects.all(), required=False, empty_label=None,
    )
    cut_mode = forms.ChoiceField(label=_('Cut mode'), choices=CutModeChoices, initial=CutModeChoices.TAB)
    file_format = forms.ChoiceField(label=_('Format'), choices=FileFormatChoices, initial=FileFormatChoices.PDF)
    template = forms.ModelChoiceField(
        label=_('Template'),
        queryset=LabelTemplate.objects.all(),
        required=False,
        empty_label=_('Best match per object'),
    )
    copies = forms.IntegerField(label=_('Copies'), min_value=1, max_value=20, initial=1)
    tape = forms.TypedChoiceField(
        label=_('Tape'),
        choices=add_blank_choice(TapeWidthChoices),
        coerce=int,
        empty_value=None,
        required=False,
        help_text=_(
            "Used for the preview and downloads; defaults to the network printer's configured tape. "
            "Printers report their loaded tape when printing."
        ),
    )

    def __init__(self, *args, printers=None, **kwargs):
        super().__init__(*args, **kwargs)
        if printers is not None:
            self.fields['printer'].queryset = printers
            if not printers.exists():
                # Without a printer the user may print on, only USB and download remain
                self.fields['method'].choices = [
                    choice for choice in PrintMethodChoices.CHOICES if choice[0] != PrintMethodChoices.NETWORK
                ]
                self.fields['method'].initial = PrintMethodChoices.USB

    def clean(self):
        super().clean()
        if self.cleaned_data.get('method') == PrintMethodChoices.NETWORK and not self.cleaned_data.get('printer'):
            raise forms.ValidationError({'printer': _('Select a printer.')})
