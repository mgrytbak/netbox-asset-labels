from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from dcim.models import Device, Module
from netbox.models import PrimaryModel
from utilities.querysets import RestrictedQuerySet

from .choices import (
    AppliesToChoices, CutModeChoices, PrinterModelChoices, QRPositionChoices, TapeWidthChoices, TextAlignChoices,
)

__all__ = (
    'LabelPrinter',
    'LabelTemplate',
    'label_attributes',
)

DEFAULT_TEXT_TEMPLATE = '{{ object.name or object }}\n{{ object.asset_tag or object.serial or "" }}'
DEFAULT_QR_TEMPLATE = '{{ url }}'


class LabelPrinter(PrimaryModel):
    name = models.CharField(
        verbose_name=_('name'),
        max_length=100,
        unique=True,
    )
    printer_model = models.CharField(
        verbose_name=_('model'),
        max_length=20,
        choices=PrinterModelChoices,
        default=PrinterModelChoices.PT_E550W,
    )
    host = models.CharField(
        verbose_name=_('host'),
        max_length=255,
        help_text=_('IP address or hostname of the printer'),
    )
    port = models.PositiveIntegerField(
        verbose_name=_('port'),
        default=9100,
        validators=[MinValueValidator(1), MaxValueValidator(65535)],
    )
    tape_width = models.PositiveSmallIntegerField(
        verbose_name=_('tape width'),
        choices=TapeWidthChoices,
        default=12,
        help_text=_('Used when the printer does not report the loaded tape'),
    )
    cut_mode = models.CharField(
        verbose_name=_('cut mode'),
        max_length=10,
        choices=CutModeChoices,
        default=CutModeChoices.TAB,
    )

    clone_fields = ('printer_model', 'port', 'tape_width', 'cut_mode')

    class Meta:
        ordering = ('name',)
        verbose_name = _('label printer')
        verbose_name_plural = _('label printers')

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('plugins:netbox_asset_labels:labelprinter', args=[self.pk])


def label_attributes(obj):
    """Return the attributes a LabelTemplate is matched against for a Device or Module."""
    if isinstance(obj, Device):
        device, kind = obj, AppliesToChoices.DEVICE
        manufacturer, device_type, module_type = obj.device_type.manufacturer, obj.device_type, None
    elif isinstance(obj, Module):
        device, kind = obj.device, AppliesToChoices.MODULE
        manufacturer, device_type, module_type = obj.module_type.manufacturer, None, obj.module_type
    else:
        raise TypeError(f'Labels can only be printed for devices and modules, not {type(obj).__name__}')
    return {
        'kind': kind,
        'manufacturers': manufacturer,
        'device_types': device_type,
        'module_types': module_type,
        'roles': device.role,
        'platforms': device.platform,
        'sites': device.site,
        'locations': device.location,
        'tenants': device.tenant,
    }


class LabelTemplateQuerySet(RestrictedQuerySet):

    def for_object(self, obj):
        """
        Return the templates applicable to a Device or Module, best match first. As with
        config contexts, a template matches if each of its assignment fields is either
        empty or contains the object's value (or, for nested objects, one of its parents).
        """
        attrs = label_attributes(obj)
        queryset = self.filter(applies_to__in=(AppliesToChoices.ALL, attrs.pop('kind')))
        for field, value in attrs.items():
            condition = Q(**{f'{field}__isnull': True})
            if value is not None:
                get_ancestors = getattr(value, 'get_ancestors', None)
                values = list(get_ancestors(include_self=True)) if get_ancestors else [value]
                condition |= Q(**{f'{field}__in': values})
            queryset = queryset.filter(condition)
        return queryset.distinct().order_by('-weight', 'name')


class LabelTemplate(PrimaryModel):
    name = models.CharField(
        verbose_name=_('name'),
        max_length=100,
        unique=True,
    )
    weight = models.PositiveSmallIntegerField(
        verbose_name=_('weight'),
        default=1000,
        help_text=_('When several templates match an object, the one with the highest weight is used'),
    )
    applies_to = models.CharField(
        verbose_name=_('applies to'),
        max_length=10,
        choices=AppliesToChoices,
        default=AppliesToChoices.ALL,
    )

    # Assignment
    manufacturers = models.ManyToManyField(to='dcim.Manufacturer', related_name='+', blank=True)
    device_types = models.ManyToManyField(to='dcim.DeviceType', related_name='+', blank=True)
    module_types = models.ManyToManyField(to='dcim.ModuleType', related_name='+', blank=True)
    roles = models.ManyToManyField(to='dcim.DeviceRole', related_name='+', blank=True)
    platforms = models.ManyToManyField(to='dcim.Platform', related_name='+', blank=True)
    sites = models.ManyToManyField(to='dcim.Site', related_name='+', blank=True)
    locations = models.ManyToManyField(to='dcim.Location', related_name='+', blank=True)
    tenants = models.ManyToManyField(to='tenancy.Tenant', related_name='+', blank=True)

    # Content
    text_template = models.TextField(
        verbose_name=_('text'),
        blank=True,
        default=DEFAULT_TEXT_TEMPLATE,
        help_text=_('Jinja2 template; each non-empty line becomes a line on the label'),
    )
    qr_position = models.CharField(
        verbose_name=_('QR code'),
        max_length=10,
        choices=QRPositionChoices,
        default=QRPositionChoices.LEFT,
    )
    qr_template = models.TextField(
        verbose_name=_('QR code data'),
        blank=True,
        default=DEFAULT_QR_TEMPLATE,
        help_text=_('Jinja2 template; the object URL by default'),
    )
    emphasize_first_line = models.BooleanField(
        verbose_name=_('emphasize first line'),
        default=True,
        help_text=_('Print the first line larger and bold'),
    )
    text_align = models.CharField(
        verbose_name=_('text alignment'),
        max_length=10,
        choices=TextAlignChoices,
        default=TextAlignChoices.LEFT,
    )
    length_mm = models.DecimalField(
        verbose_name=_('length (mm)'),
        max_digits=5,
        decimal_places=1,
        blank=True,
        null=True,
        validators=[MinValueValidator(5), MaxValueValidator(1000)],
        help_text=_('Fixed label length; leave empty to fit the content'),
    )
    margin_mm = models.DecimalField(
        verbose_name=_('margin (mm)'),
        max_digits=3,
        decimal_places=1,
        default=2,
        validators=[MinValueValidator(2), MaxValueValidator(50)],
        help_text=_('Blank tape before and after the content'),
    )

    objects = LabelTemplateQuerySet.as_manager()

    clone_fields = (
        'weight', 'applies_to', 'manufacturers', 'device_types', 'module_types', 'roles', 'platforms', 'sites',
        'locations', 'tenants', 'text_template', 'qr_position', 'qr_template', 'emphasize_first_line',
        'text_align', 'length_mm', 'margin_mm',
    )

    class Meta:
        ordering = ('-weight', 'name')
        verbose_name = _('label template')
        verbose_name_plural = _('label templates')

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('plugins:netbox_asset_labels:labeltemplate', args=[self.pk])
