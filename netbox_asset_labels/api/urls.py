from django.urls import path

from netbox.api.routers import NetBoxRouter

from . import views

router = NetBoxRouter()
router.register('printers', views.LabelPrinterViewSet)
router.register('templates', views.LabelTemplateViewSet)

urlpatterns = [
    path('printers/<int:pk>/status/', views.LabelPrinterStatusView.as_view(), name='labelprinter-status'),
    path('printers/<int:pk>/print/', views.LabelPrinterPrintView.as_view(), name='labelprinter-print'),
    *router.urls,
]
