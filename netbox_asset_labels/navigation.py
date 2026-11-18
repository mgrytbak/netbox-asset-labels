from django.utils.translation import gettext_lazy as _

from netbox.plugins import PluginMenuButton, PluginMenuItem

menu_items = (
    PluginMenuItem(
        link='plugins:netbox_asset_labels:labeltemplate_list',
        link_text=_('Label Templates'),
        permissions=['netbox_asset_labels.view_labeltemplate'],
        buttons=(
            PluginMenuButton(
                'plugins:netbox_asset_labels:labeltemplate_add',
                _('Add'),
                'mdi mdi-plus-thick',
                permissions=['netbox_asset_labels.add_labeltemplate'],
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_asset_labels:labelprinter_list',
        link_text=_('Label Printers'),
        permissions=['netbox_asset_labels.view_labelprinter'],
        buttons=(
            PluginMenuButton(
                'plugins:netbox_asset_labels:labelprinter_add',
                _('Add'),
                'mdi mdi-plus-thick',
                permissions=['netbox_asset_labels.add_labelprinter'],
            ),
        ),
    ),
)
