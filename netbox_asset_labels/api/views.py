from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from dcim.models import Device, Module
from netbox.api.authentication import IsAuthenticatedOrLoginNotRequired
from netbox.api.viewsets import NetBoxModelViewSet

from .. import filtersets
from ..models import LabelPrinter, LabelTemplate
from ..printing import LabelError, PrinterError, get_netbox_url, print_labels, printer_status
from ..views import MAX_LABELS
from .serializers import LabelPrinterSerializer, LabelPrintSerializer, LabelTemplateSerializer


class LabelPrinterViewSet(NetBoxModelViewSet):
    queryset = LabelPrinter.objects.all()
    serializer_class = LabelPrinterSerializer
    filterset_class = filtersets.LabelPrinterFilterSet


class LabelTemplateViewSet(NetBoxModelViewSet):
    queryset = LabelTemplate.objects.prefetch_related(
        'manufacturers', 'device_types', 'module_types', 'roles', 'platforms', 'sites', 'locations', 'tenants',
    )
    serializer_class = LabelTemplateSerializer
    filterset_class = filtersets.LabelTemplateFilterSet


class LabelPrinterStatusView(APIView):
    """The live status reported by a label printer."""
    permission_classes = [IsAuthenticatedOrLoginNotRequired]

    @extend_schema(responses={200: dict})
    def get(self, request, pk):
        printer = get_object_or_404(LabelPrinter.objects.restrict(request.user, 'view'), pk=pk)
        try:
            printer_state = printer_status(printer)
        except PrinterError as e:
            return Response({'reachable': False, 'status': None, 'error': str(e)})
        if printer_state is None:
            return Response({'reachable': True, 'status': None, 'error': None})
        return Response({
            'reachable': True,
            'status': {
                'ready': not printer_state.errors,
                'errors': printer_state.errors,
                'tape_width': printer_state.tape.label if printer_state.tape else None,
                'tape_type': printer_state.media_description,
            },
            'error': None,
        })


class LabelPrinterPrintView(APIView):
    """Print labels for devices and/or modules on a label printer."""
    permission_classes = [IsAuthenticatedOrLoginNotRequired]

    @extend_schema(request=LabelPrintSerializer, responses={200: dict})
    def post(self, request, pk):
        if request.auth is not None and not getattr(request.auth, 'write_enabled', True):
            raise PermissionDenied('This API token does not permit write operations.')
        printer = get_object_or_404(LabelPrinter.objects.restrict(request.user, 'print'), pk=pk)

        serializer = LabelPrintSerializer(data=request.data)
        serializer.fields['devices'].child_relation.queryset = Device.objects.restrict(request.user, 'view')
        serializer.fields['modules'].child_relation.queryset = Module.objects.restrict(request.user, 'view')
        serializer.fields['template'].queryset = LabelTemplate.objects.restrict(request.user, 'view')
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        objects = [*data.get('devices', []), *data.get('modules', [])]
        if len(objects) > MAX_LABELS:
            return Response({'detail': f'Select at most {MAX_LABELS} objects.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            result = print_labels(
                printer, objects, get_netbox_url(request), copies=data['copies'], template=data.get('template'),
            )
        except LabelError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except PrinterError as e:
            return Response({'detail': str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({
            'detail': str(result),
            'count': result.count,
            'tape_width': result.tape.label,
            'tape_detected': result.tape_detected,
            'confirmed': result.confirmed,
        })
