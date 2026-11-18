from rest_framework import serializers

from dcim.api.serializers import (
    DeviceRoleSerializer, DeviceTypeSerializer, LocationSerializer, ManufacturerSerializer, ModuleTypeSerializer,
    PlatformSerializer, SiteSerializer,
)
from dcim.models import Device, DeviceRole, DeviceType, Location, Manufacturer, Module, ModuleType, Platform, Site
from netbox.api.fields import ChoiceField, SerializedPKRelatedField
from netbox.api.serializers import PrimaryModelSerializer
from tenancy.api.serializers import TenantSerializer
from tenancy.models import Tenant

from ..choices import (
    AppliesToChoices, CutModeChoices, PrinterModelChoices, QRPositionChoices, TapeWidthChoices, TextAlignChoices,
)
from ..models import LabelPrinter, LabelTemplate

__all__ = (
    'LabelPrintSerializer',
    'LabelPrinterSerializer',
    'LabelTemplateSerializer',
)


class LabelPrinterSerializer(PrimaryModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='plugins-api:netbox_asset_labels-api:labelprinter-detail')
    printer_model = ChoiceField(choices=PrinterModelChoices, required=False)
    tape_width = ChoiceField(choices=TapeWidthChoices, required=False)
    cut_mode = ChoiceField(choices=CutModeChoices, required=False)

    class Meta:
        model = LabelPrinter
        fields = (
            'id', 'url', 'display_url', 'display', 'name', 'printer_model', 'host', 'port', 'tape_width', 'cut_mode',
            'description', 'owner', 'comments', 'tags', 'custom_fields', 'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'description')


def _assignment_field(model, serializer):
    return SerializedPKRelatedField(
        queryset=model.objects.all(), serializer=serializer, nested=True, required=False, many=True,
    )


class LabelTemplateSerializer(PrimaryModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='plugins-api:netbox_asset_labels-api:labeltemplate-detail')
    applies_to = ChoiceField(choices=AppliesToChoices, required=False)
    qr_position = ChoiceField(choices=QRPositionChoices, required=False)
    text_align = ChoiceField(choices=TextAlignChoices, required=False)
    manufacturers = _assignment_field(Manufacturer, ManufacturerSerializer)
    device_types = _assignment_field(DeviceType, DeviceTypeSerializer)
    module_types = _assignment_field(ModuleType, ModuleTypeSerializer)
    roles = _assignment_field(DeviceRole, DeviceRoleSerializer)
    platforms = _assignment_field(Platform, PlatformSerializer)
    sites = _assignment_field(Site, SiteSerializer)
    locations = _assignment_field(Location, LocationSerializer)
    tenants = _assignment_field(Tenant, TenantSerializer)

    class Meta:
        model = LabelTemplate
        fields = (
            'id', 'url', 'display_url', 'display', 'name', 'weight', 'applies_to', 'manufacturers', 'device_types',
            'module_types', 'roles', 'platforms', 'sites', 'locations', 'tenants', 'text_template',
            'emphasize_first_line', 'text_align', 'qr_position', 'qr_template', 'length_mm', 'margin_mm',
            'description', 'owner', 'comments', 'tags', 'custom_fields', 'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'description')


class LabelPrintSerializer(serializers.Serializer):
    """Request body for printing labels."""
    devices = serializers.PrimaryKeyRelatedField(queryset=Device.objects.all(), many=True, required=False)
    modules = serializers.PrimaryKeyRelatedField(queryset=Module.objects.all(), many=True, required=False)
    template = serializers.PrimaryKeyRelatedField(
        queryset=LabelTemplate.objects.all(),
        required=False,
        allow_null=True,
        help_text='Template for all labels; by default each object uses its best matching template',
    )
    copies = serializers.IntegerField(min_value=1, max_value=20, default=1)

    def validate(self, data):
        if not data.get('devices') and not data.get('modules'):
            raise serializers.ValidationError('Specify at least one device or module.')
        return data
