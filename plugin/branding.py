"""Public identity; import namespace and saved preferences stay stable across upgrades."""
NAME = 'JEV Book Tags'
VERSION = (1, 0, 3)
DEFAULT_MODEL = 'jev-latest'


def icon():
    from qt.core import QIcon
    try:
        return get_icons('images/icon.svg')
    except NameError:
        return QIcon()
