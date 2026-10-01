from calibre.customize import InterfaceActionBase


class JevCatalogPlugin(InterfaceActionBase):
    name = 'JEV Book Tags'
    description = 'Classify library books with TypeSafe AI JEV.'
    author = 'CalibreJevCatalog contributors'
    version = (1, 1, 1)
    minimum_calibre_version = (9, 0, 0)
    supported_platforms = ['windows', 'osx', 'linux']
    actual_plugin = 'calibre_plugins.jev_catalog.action:JevCatalogAction'

    def is_customizable(self):
        return True

    def config_widget(self):
        from calibre_plugins.jev_catalog.config import ConfigWidget
        from calibre.gui2.ui import get_gui
        gui = get_gui()
        return ConfigWidget(gui.current_db.new_api if gui else None, gui=gui)

    def save_settings(self, widget):
        widget.save_settings()
        if self.actual_plugin_ is not None:
            self.actual_plugin_.apply_settings()
