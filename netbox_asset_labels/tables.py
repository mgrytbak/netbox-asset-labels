import django_tables2 as tables
from django.utils.translation import gettext_lazy as _

from netbox.tables import PrimaryModelTable, columns

from .models import LabelPrinter, LabelTemplate

__all__ = (
    'LabelPrinterTable',
    'LabelTemplateTable',
)


class LabelPrinterTable(PrimaryModelTable):
    name = tables.Column(verbose_name=_('Name'), linkify=True)
    printer_model = columns.ChoiceFieldColumn(verbose_name=_('Model'))
    tape_width = columns.ChoiceFieldColumn(verbose_name=_('Tape width'))
    cut_mode = columns.ChoiceFieldColumn(verbose_name=_('Cut mode'))
    tags = columns.TagColumn(url_name='plugins:netbox_asset_labels:labelprinter_list')

    class Meta(PrimaryModelTable.Meta):
        model = LabelPrinter
        fields = (
            'pk', 'id', 'name', 'printer_model', 'host', 'port', 'tape_width', 'cut_mode', 'description', 'owner',
            'comments', 'tags', 'created', 'last_updated',
        )
        default_columns = ('pk', 'name', 'printer_model', 'host', 'tape_width', 'cut_mode', 'description')


class LabelTemplateTable(PrimaryModelTable):
    name = tables.Column(verbose_name=_('Name'), linkify=True)
    applies_to = columns.ChoiceFieldColumn(verbose_name=_('Applies to'))
    qr_position = columns.ChoiceFieldColumn(verbose_name=_('QR code'))
    text_align = columns.ChoiceFieldColumn(verbose_name=_('Text alignment'))
    emphasize_first_line = columns.BooleanColumn(verbose_name=_('Emphasize first line'))
    manufacturers = columns.ManyToManyColumn(verbose_name=_('Manufacturers'), linkify_item=True)
    device_types = columns.ManyToManyColumn(verbose_name=_('Device types'), linkify_item=True)
    module_types = columns.ManyToManyColumn(verbose_name=_('Module types'), linkify_item=True)
    roles = columns.ManyToManyColumn(verbose_name=_('Roles'), linkify_item=True)
    platforms = columns.ManyToManyColumn(verbose_name=_('Platforms'), linkify_item=True)
    sites = columns.ManyToManyColumn(verbose_name=_('Sites'), linkify_item=True)
    locations = columns.ManyToManyColumn(verbose_name=_('Locations'), linkify_item=True)
    tenants = columns.ManyToManyColumn(verbose_name=_('Tenants'), linkify_item=True)
    tags = columns.TagColumn(url_name='plugins:netbox_asset_labels:labeltemplate_list')

    class Meta(PrimaryModelTable.Meta):
        model = LabelTemplate
        fields = (
            'pk', 'id', 'name', 'weight', 'applies_to', 'manufacturers', 'device_types', 'module_types', 'roles',
            'platforms', 'sites', 'locations', 'tenants', 'qr_position', 'text_align', 'emphasize_first_line',
            'length_mm', 'margin_mm', 'description', 'owner', 'comments', 'tags', 'created', 'last_updated',
        )
        default_columns = (
            'pk', 'name', 'weight', 'applies_to', 'device_types', 'module_types', 'roles', 'sites', 'tenants',
            'description',
        )
