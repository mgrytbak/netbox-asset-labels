import django_filters
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from dcim.models import DeviceRole, DeviceType, Location, Manufacturer, ModuleType, Platform, Site
from netbox.filtersets import PrimaryModelFilterSet
from tenancy.models import Tenant

from .choices import AppliesToChoices, CutModeChoices, PrinterModelChoices, QRPositionChoices, TapeWidthChoices
from .models import LabelPrinter, LabelTemplate

__all__ = (
    'LabelPrinterFilterSet',
    'LabelTemplateFilterSet',
)


class LabelPrinterFilterSet(PrimaryModelFilterSet):
    printer_model = django_filters.MultipleChoiceFilter(choices=PrinterModelChoices)
    tape_width = django_filters.MultipleChoiceFilter(choices=TapeWidthChoices)
    cut_mode = django_filters.MultipleChoiceFilter(choices=CutModeChoices)

    class Meta:
        model = LabelPrinter
        fields = ('id', 'name', 'host', 'port', 'description')

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value) | Q(host__icontains=value) | Q(description__icontains=value)
        )


def _assignment_filter(field, model, label):
    return django_filters.ModelMultipleChoiceFilter(field_name=field, queryset=model.objects.all(), label=label)


class LabelTemplateFilterSet(PrimaryModelFilterSet):
    applies_to = django_filters.MultipleChoiceFilter(choices=AppliesToChoices)
    qr_position = django_filters.MultipleChoiceFilter(choices=QRPositionChoices)
    manufacturer_id = _assignment_filter('manufacturers', Manufacturer, _('Manufacturer (ID)'))
    device_type_id = _assignment_filter('device_types', DeviceType, _('Device type (ID)'))
    module_type_id = _assignment_filter('module_types', ModuleType, _('Module type (ID)'))
    role_id = _assignment_filter('roles', DeviceRole, _('Device role (ID)'))
    platform_id = _assignment_filter('platforms', Platform, _('Platform (ID)'))
    site_id = _assignment_filter('sites', Site, _('Site (ID)'))
    location_id = _assignment_filter('locations', Location, _('Location (ID)'))
    tenant_id = _assignment_filter('tenants', Tenant, _('Tenant (ID)'))

    class Meta:
        model = LabelTemplate
        fields = ('id', 'name', 'weight', 'description')

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value) | Q(description__icontains=value) | Q(text_template__icontains=value)
        )
