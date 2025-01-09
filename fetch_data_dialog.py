from qgis.PyQt.QtWidgets import QDialog
from .forms.fetch_data_dialog_base import Ui_FetchGeoJSON

class FetchDataDialog(QDialog, Ui_FetchGeoJSON):
    def __init__(self, parent=None, option=None):
        super(FetchDataDialog, self).__init__(parent)
        self.setupUi(self)

        # Initialize any additional UI elements or logic
        self.setWindowTitle("AfpolGIS Data Connector")
