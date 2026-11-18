from django.utils.translation import gettext_lazy as _

from utilities.choices import ChoiceSet

from . import layout, ptouch


class PrinterModelChoices(ChoiceSet):
    PT_E550W = 'pt-e550w'
    PT_P750W = 'pt-p750w'

    CHOICES = (
        (PT_E550W, 'PT-E550W'),
        (PT_P750W, 'PT-P750W'),
    )


class TapeWidthChoices(ChoiceSet):
    CHOICES = tuple((tape.code, tape.label) for tape in ptouch.TAPES.values())


class CutModeChoices(ChoiceSet):
    TAB = ptouch.CUT_TAB
    FULL = ptouch.CUT_FULL
    NONE = ptouch.CUT_NONE

    CHOICES = (
        (TAB, _('Full cut, with half-cut peel tab')),
        (FULL, _('Full cut after each label')),
        (NONE, _('No cut')),
    )


class AppliesToChoices(ChoiceSet):
    ALL = 'all'
    DEVICE = 'device'
    MODULE = 'module'

    CHOICES = (
        (ALL, _('Devices and modules')),
        (DEVICE, _('Devices')),
        (MODULE, _('Modules')),
    )


class QRPositionChoices(ChoiceSet):
    NONE = layout.QR_NONE
    LEFT = layout.QR_LEFT
    RIGHT = layout.QR_RIGHT

    CHOICES = (
        (LEFT, _('Left of text')),
        (RIGHT, _('Right of text')),
        (NONE, _('No QR code')),
    )


class TextAlignChoices(ChoiceSet):
    LEFT = layout.ALIGN_LEFT
    CENTER = layout.ALIGN_CENTER

    CHOICES = (
        (LEFT, _('Left')),
        (CENTER, _('Center')),
    )


class PrintMethodChoices(ChoiceSet):
    NETWORK = 'network'
    USB = 'usb'
    DOWNLOAD = 'download'

    CHOICES = (
        (NETWORK, _('Network printer')),
        (USB, _('USB printer on this computer')),
        (DOWNLOAD, _('Download')),
    )


class FileFormatChoices(ChoiceSet):
    PDF = 'pdf'
    PNG = 'png'

    CHOICES = (
        (PDF, _('PDF (one page per label)')),
        (PNG, _('PNG (ZIP for several labels)')),
    )
