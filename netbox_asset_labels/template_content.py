from django.urls import reverse

from netbox.plugins import PluginTemplateExtension

PRINT_PERMISSION = 'netbox_asset_labels.print_labelprinter'


class PrintLabelButtons(PluginTemplateExtension):
    """"Print label" on device/module pages and "Print labels" on their list pages."""
    models = ['dcim.device', 'dcim.module']

    def _context(self, model):
        request = self.context['request']
        return {
            'print_url': reverse('plugins:netbox_asset_labels:print'),
            'object_type': model._meta.model_name,
            'return_url': request.get_full_path(),
        }

    def buttons(self):
        if not self.context['request'].user.has_perm(PRINT_PERMISSION):
            return ''
        return self.render('netbox_asset_labels/buttons/print_label.html', self._context(self.context['object']))

    def list_buttons(self):
        if not self.context['request'].user.has_perm(PRINT_PERMISSION):
            return ''
        # NetBox passes the list view's model as "object"
        return self.render('netbox_asset_labels/buttons/print_labels.html', self._context(self.context['object']))


template_extensions = [PrintLabelButtons]
