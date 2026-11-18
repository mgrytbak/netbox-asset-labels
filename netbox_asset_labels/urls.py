from django.urls import include, path

from utilities.urls import get_model_urls

from . import views

urlpatterns = (
    path('printers/', include(get_model_urls('netbox_asset_labels', 'labelprinter', detail=False))),
    path('printers/<int:pk>/', include(get_model_urls('netbox_asset_labels', 'labelprinter'))),
    path('templates/', include(get_model_urls('netbox_asset_labels', 'labeltemplate', detail=False))),
    path('templates/<int:pk>/', include(get_model_urls('netbox_asset_labels', 'labeltemplate'))),
    path('print/', views.LabelPrintView.as_view(), name='print'),
)
