from netbox.plugins import PluginConfig

__version__ = '0.1.0'


class AssetLabelsConfig(PluginConfig):
    name = 'netbox_asset_labels'
    verbose_name = 'Asset Labels'
    description = 'Print asset labels for devices and modules on Brother P-touch printers'
    version = __version__
    base_url = 'asset-labels'
    min_version = '4.7.0'
    default_settings = {
        # Absolute URL of NetBox used in QR codes, e.g. "https://netbox.example.com".
        # Defaults to the URL of the current request.
        'netbox_url': None,
        # TrueType fonts for label text; Pillow's built-in font is used if unset
        'font_path': None,
        'bold_font_path': None,
        # Seconds to wait for a printer to connect and to report printed labels
        'printer_timeout': 5,
    }


config = AssetLabelsConfig
