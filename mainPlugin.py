import logging
import json
import math
from math import pi, cos
import os
import time
import re
import requests
from requests.auth import HTTPBasicAuth

from PyQt5 import *
from qgis.core import (
    Qgis,
    QgsProject,
    QgsVectorLayer,
    QgsRasterLayer,
    QgsFeature,
    QgsGeometry,
    QgsField,
)
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from .fetch_data_dialog import FetchDataDialog
from datetime import datetime, timezone

from .request_threads import (
    OnaRequestThread,
    FetchOnaFormsThread,
    FetchOnaGeoFieldsThread,
)


# Configure logging
logging.basicConfig(
    filename="fetch_data.log",  # Log file name
    filemode="a",  # Append mode
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.DEBUG,  # Log level
)


class AsyncFetchWorker(QObject):
    data_fetched = pyqtSignal(object)  # Emitted with fetched data
    fetch_error = pyqtSignal(str)  # Emitted on error
    progress_updated = pyqtSignal(str)  # Optional: progress updates

    def __init__(self, parent=None):
        super().__init__(parent)

    async def start_fetch(self, url, auth=None, params=None, headers=None):
        """Async function to fetch data."""
        try:
            # Asynchronous fetch with aiohttp
            async with aiohttp.ClientSession(auth=auth, headers=headers) as session:
                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        self.dlg.app_logs.appendPlainText("Resource not found.")
                        return None
                    response.raise_for_status()
                    data = await response.json()
                    if data:
                        self.data_fetched.emit(data)
                        self.data_count = data.get("num_of_submissions")

        except Exception as e:
            raise RuntimeError(f"Error during fetch: {e}")

class RequestThread(QThread):
    data_fetched = pyqtSignal(object)  # Signal to emit the response
    progress_updated = pyqtSignal(str)
    error_occurred = pyqtSignal(str)  # Signal to emit errors

    def __init__(
        self,
        url,
        auth=None,
        params=None,
        headers=None,
        total_records=None,
        records_per_page=None,
    ):
        super().__init__()
        self.url = url
        self.auth = auth
        self.params = params
        self.headers = headers
        self.max_retries = 5
        self.backoff_factor = 0.2
        self.total_records = total_records
        self.records_per_page = records_per_page

    def run(self):
        combined_results = []
        try:
            if (
                self.total_records and self.records_per_page
            ):  # Handle paginated requests
                total_pages = (
                    self.total_records + self.records_per_page - 1
                ) // self.records_per_page
                for page in range(1, total_pages + 1):
                    self.progress_updated.emit(f"Fetching page {page}/{total_pages}...")
                    self.params.update(
                        {"page": page, "page_size": self.records_per_page}
                    )
                    res = self.fetch_data()
                    data = res.json()
                    if data:
                        combined_results.extend(data)
                self.data_fetched.emit(combined_results)
            else:  # Handle unpaginated requests
                self.progress_updated.emit("Fetching unpaginated data...")
                res = self.fetch_data()
                data = res.json()
                self.data_fetched.emit(data)

        except Exception as e:
            self.error_occurred.emit(str(e))

    def fetch_data(self):
        """Fetches data with retries and backoff logic."""
        with requests.Session() as session:  # Use a session
            if self.auth:
                session.auth = self.auth  # Set Basic Auth for the session

            # set headers
            if self.headers:
                session.headers.update(self.headers)

            for attempt in range(self.max_retries):
                try:
                    if self.params:
                        response = session.get(
                            self.url, params=self.params, stream=True
                        )
                    else:
                        response = session.get(self.url, stream=True)
                    return response
                except (
                    requests.RequestException,
                    requests.ConnectionError,
                    requests.ConnectTimeout,
                    requests.ReadTimeout,
                ) as e:
                    print(f"Attempt {attempt + 1} failed: {e}")
                    if attempt < self.max_retries - 1:
                        time.sleep(
                            self.backoff_factor * (2**attempt)
                        )  # Exponential backoff
                    else:
                        self.error_occurred.emit(str(e))


class FetchDataWorker(QThread):
    """Worker thread for fetching data in the background."""

    data_fetched = pyqtSignal(
        object
    )  # Signal emitted when data is successfully fetched
    fetch_error = pyqtSignal(str)  # Signal emitted when an error occurs
    progress_updated = pyqtSignal(str)  # Optional: for progress reporting

    def __init__(
        self,
        plugin,
        api_url,
        formID,
        username,
        password,
        geo_field,
        page_size,
        directory,
        dlg,
        interrupted,
    ):
        super(FetchDataWorker, self).__init__()
        self.plugin = plugin
        self.api_url = api_url
        self.formID = formID
        self.username = username
        self.password = password
        self.geo_field = geo_field
        self.page_size = page_size
        self.directory = directory
        self.dlg = dlg
        self.is_interrupted = interrupted  # Flag for stopping the worker

    def run(self):
        """Main loop that fetches data in the background."""
        try:
            if self.is_interrupted:
                self.progress_updated.emit("Fetch operation cancelled.")
                return

            # Call the plugin method to fetch and save data
            result = self.plugin.fetch_and_save_data(
                self.api_url,
                self.formID,
                self.username,
                self.password,
                self.geo_field,
                self.page_size,
                self.directory,
            )

            # Emit signal with fetched data or result (adjust as needed)
            if not self.is_interrupted:
                self.data_fetched.emit({"test": "me"})
            else:
                self.progress_updated.emit("Operation interrupted before completion.")

        except Exception as e:
            # Emit an error signal to notify the main thread
            self.fetch_error.emit(str(e))
        finally:
            self.quit()

    def stop(self):
        self.is_interrupted = True


class FetchODKDataWorker(QThread):
    """Worker thread for fetching data in the background."""

    odk_data_fetched = pyqtSignal(
        QObject
    )  # Signal emitted when data is successfully fetched
    odk_fetch_error = pyqtSignal(str)  # Signal emitted when an error occurs
    odk_rogress_updated = pyqtSignal(str)  # Optional: for progress reporting

    def __init__(
        self,
        plugin,
        api_url,
        form_id_str,
        username,
        password,
        geo_field,
        page_size,
        directory,
        dlg,
        interrupted,
        odk_from_date,
        odk_to_date,
    ):
        super(FetchODKDataWorker, self).__init__()
        self.plugin = plugin
        self.api_url = api_url
        self.form_id_str = form_id_str
        self.username = username
        self.password = password
        self.geo_field = geo_field
        self.page_size = page_size
        self.directory = directory
        self.dlg = dlg
        self.is_interrupted = interrupted  # Flag for stopping the worker
        self.odk_from_date = odk_from_date
        self.odk_to_date = odk_to_date

    def run(self):
        """Main loop that fetches data in the background."""
        try:
            while not self.is_interrupted:
                # Call the plugin method to fetch and save data
                logging.info(f"The run block has been triggered...")
                result = self.plugin.fetch_and_save_odk_data(
                    self.api_url,
                    self.username,
                    self.password,
                    self.form_id_str,
                    self.geo_field,
                    self.odk_from_date,
                    self.odk_to_date,
                )

                # Emit signal with fetched data or result (adjust as needed)
                self.odk_data_fetched.emit(result)

                # Optional: Report progress to the UI
                # self.progress_updated.emit("Data fetched successfully.")

                # Check for the cancellation flag periodically (or at logical points)
                if self.is_interrupted:
                    self.odk_rogress_updated.emit("Fetch operation cancelled.")
                    break
                # Stop the loop if no more data or based on other conditions
                break  # Remove this if you want to continuously fetch data

        except Exception as e:
            # Emit an error signal to notify the main thread
            self.odk_fetch_error.emit(str(e))

    def stop(self):
        # self.is_interrupted = True
        self.quit()
        self.wait(5000)


class FetchFieldsWorker(QThread):
    """Worker thread for fetching form GeoJSON fields in the background."""

    data_fetched = pyqtSignal(
        QObject
    )  # Signal emitted when data is successfully fetched
    fetch_error = pyqtSignal(str)  # Signal emitted when an error occurs
    progress_updated = pyqtSignal(str)  # Optional: for progress reporting

    def __init__(
        self, plugin, api_url, formID, username, password, directory, dlg, interrupted
    ):
        super(FetchFieldsWorker, self).__init__()
        self.plugin = plugin
        self.api_url = api_url
        self.formID = formID
        self.username = username
        self.password = password
        self.directory = directory
        self.dlg = dlg
        self.is_interrupted = interrupted  # Flag for stopping the worker
        self.hasGeoFields = False

    def run(self):
        """Main loop that fetches data in the background."""
        try:
            while not self.is_interrupted:
                # Call the plugin method to fetch and save data
                result = self.plugin.fetch_and_save_geojson_fields(
                    self.api_url, self.username, self.password, self.formID
                )

                # if result:
                #     self.hasGeoFields = True

                # Emit signal with fetched data or result (adjust as needed)
                self.data_fetched.emit(result)
                # Stop the loop if no more data or based on other conditions
                break  # Remove this if you want to continuously fetch data

        except Exception as e:
            # Emit an error signal to notify the main thread
            self.fetch_error.emit(str(e))

    def stop(self):
        self.is_interrupted = True


class FetchDataPlugin(QObject):
    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
                     which provides the hook by which you can manipulate the QGIS
                     application at run time.
        :type iface: QgsInterface
        """
        QObject.__init__(self)
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = self.tr("&AfpolGIS")
        self.toolbar = self.iface.addToolBar("AfpolGIS")
        self.toolbar.setObjectName("AfpolGIS")
        self.features = []
        self.json_data = []
        self.new_features = []
        self.form_versions = None
        self.current_form_version = None
        self.curr_geo_field = None
        self.geo_fields = set()
        self.geo_fields_dict = dict()
        self.geo_types = ["geopoint", "geoshape", "geotrace"]
        self.vlayer = dict()
        self.odk_forms_to_projects_map = dict()

        # Initializing the dialog and other components
        self.dlg = FetchDataDialog(option="GetODK")

        self.dlg.ComboDhisAdminLevels.addItems(
            ["Level 1", "Level 2", "Level 3", "Level 4", "Level 5"]
        )

        self.dlg.comboDhisPeriod.addItems(
            [
                "TODAY",
                "YESTERDAY",
                "LAST_3_DAYS",
                "LAST_7_DAYS",
                "LAST_14_DAYS",
                "THIS_MONTH",
                "LAST_MONTH",
                "LAST_3_MONTHS",
                "LAST_6_MONTHS",
                "LAST_12_MONTHS",
                "THIS_BIMONTH",
                "LAST_BIMONTH",
                "THIS_QUARTER",
                "LAST_QUARTER",
                "LAST_4_QUARTERS",
                "THIS_SIX_MONTH",
                "LAST_SIX_MONTH",
                "LAST_2_SIXMONTHS",
                "THIS_YEAR",
                "LAST_YEAR",
                "LAST_5_YEARS",
                "THIS_FINANCIAL_YEAR",
                "LAST_FINANCIAL_YEAR",
                "LAST_5_FINANCIAL_YEARS",
            ]
        )

        # Set initial domains
        self.dlg.onadata_api_url.setText("api.whonghub.org")
        self.dlg.kobo_api_url.setText("kf.kobotoolbox.org")
        self.dlg.odk_api_url.setText("aap-odk-sinp.cen-nouvelle-aquitaine.dev")
        self.dlg.es_api_url.setText("es.world")
        self.dlg.gts_api_url.setText("gts.health")
        self.dlg.dhis_api_url.setText("dhis-minsante-cm.org")

        # Set default ES API Version
        self.dlg.esAPIVersion.setText("4.3")

        # disable forms dropdown
        self.dlg.comboODKForms.setEnabled(False)
        self.dlg.comboKoboForms.setEnabled(False)

        # ES topography dropdown
        self.dlg.combESTopology.addItems(["Sites", "Labs"])

        # self.dlg.comboProviders.addItems(["OnaData", "GetODK", "KoboToolbox", "GTS"])

        # Connect providers dropdown on change
        # self.dlg.comboProviders.currentIndexChanged.connect(
        #     self.on_providers_change
        # )

        # obscure the password field
        # self.dlg.password.setEchoMode(QLineEdit.Password)
        # self.dlg.mLineEdit.mousePressEvent.connect(self.toggle_password_visibility)

        # self.dlg.horizontalSlider.setMinimum(0)  # Minimum value
        # self.dlg.horizontalSlider.setMaximum(10000)  # Maximum value
        # self.dlg.horizontalSlider.setValue(1000)  # default value
        # self.dlg.slider_label.setText(str(1000))

        # date range controls

        # ONA
        self.dlg.onaDateTimeFrom.setEnabled(False)
        self.dlg.onaDateTimeTo.setEnabled(False)

        # ODK
        self.dlg.ODKDateTimeFrom.setEnabled(False)
        self.dlg.ODKDateTimeTo.setEnabled(False)

        # Kobo
        self.dlg.KoboDateTimeFrom.setEnabled(False)
        self.dlg.KoboDateTimeTo.setEnabled(False)

        # clear version and geo field dropdown
        self.dlg.comboOnaForms.setEnabled(False)
        self.dlg.comboOnaGeoFields.setEnabled(False)
        self.dlg.comboODKGeoFields.setEnabled(False)

        # Connect the "OK" button to the fetch_button_clicked method
        self.dlg.onaOkButton.clicked.connect(self.fetch_button_clicked)
        self.dlg.onaCancelButton.clicked.connect(self.cancel_button_clicked)
        self.dlg.btnRemoveAll.clicked.connect(self.clear_logs)

        # Connect the ODK "OK" button to the fetch_odk_form_data_clicked function
        self.dlg.odkOkButton.clicked.connect(self.fetch_odk_form_data_clicked)

        # Connect the ODK "OK" button to the fetch_kobo_form_data_clicked function
        self.dlg.koboOkButton.clicked.connect(self.fetch_kobo_form_data_clicked)

        self.dlg.btnFetchOnaForms.clicked.connect(self.fetch_ona_forms_handler)

        # Connect the "OK" button in the ODK Tab to the corresponding fetch handler
        self.dlg.btnFetchODKForms.clicked.connect(self.fetch_odk_forms_handler)

        # Connect the "OK" button in the Kobo Tab to the corresponding fetch handler
        self.dlg.btnFetchKoboForms.clicked.connect(self.fetch_kobo_assets_handler)

        # Connect the "Connect" button in the GTS Tab to the corresponding fetch handler
        self.dlg.btnFetchGTSTables.clicked.connect(self.fetch_gts_indicators_handler)

        # Connect the "Connect" button in the DHIS Tab to the corresponding fetch handler
        self.dlg.btnFetchDhisOrgUnits.clicked.connect(self.fetch_dhis_org_units_handler)

        # Connect page size slider on change
        # self.dlg.horizontalSlider.valueChanged.connect(self.update_slider_value_label)

        # Connect calendar widget
        self.dlg.onaDateTimeFrom.dateChanged.connect(self.on_from_date_changed)
        self.dlg.onaDateTimeTo.dateChanged.connect(self.on_to_date_changed)

        # Connect the GTS OK button to handler
        self.dlg.gtsOkButton.clicked.connect(
            self.fetch_gts_tracking_rounds_data_handler
        )

        # Connect the GTS Cancel button to handler
        self.dlg.gtsCancelButton.clicked.connect(self.handle_gts_cancel_btn)

        # Connect form dropdown on change
        self.dlg.comboOnaForms.currentIndexChanged.connect(
            self.fetch_ona_form_geo_fields
        )

        # Connect form version dropdown on change
        self.dlg.comboOnaGeoFields.currentIndexChanged.connect(
            self.on_combo_box_geo_fields_change
        )

        # Connect ODK forms dropdown on change
        self.dlg.comboODKForms.currentIndexChanged.connect(
            self.on_odk_forms_combo_box_change
        )

        # Connect Kobo forms dropdown on change
        self.dlg.comboKoboForms.currentIndexChanged.connect(
            self.on_combo_box_kobo_forms_change
        )

        # Connect ES topography dropdown on change
        self.dlg.combESTopology.currentIndexChanged.connect(
            self.on_es_topography_change
        )

        # Connect GTS table names dropdown on change
        self.dlg.comboGTSTableTypes.currentIndexChanged.connect(
            self.on_gts_tables_combo_box_change
        )

        # Connect GTS field activities dropdown on change
        self.dlg.comboGTSFieldActivities.currentIndexChanged.connect(
            self.on_gts_field_activity_change
        )

        # Connect GTS track rounds on change
        self.dlg.comboGTSTrackingRounds.currentIndexChanged.connect(
            self.on_gts_tracking_rounds_on_change
        )

        # Connect DHIS Levels action
        self.dlg.ComboDhisAdminLevels.currentIndexChanged.connect(
            self.fetch_dhis_org_units_handler
        )

        # DHIS Org units on change
        self.dlg.comboDhisOrgUnits.currentIndexChanged.connect(
            self.on_dhis_org_units_change
        )

        self.dlg.onaOkButton.setEnabled(False)
        self.dlg.odkOkButton.setEnabled(False)
        self.dlg.koboOkButton.setEnabled(False)
        self.dlg.gtsOkButton.setEnabled(False)

        # password visibility
        self.showPassword = False

        # data sync
        self.timer = QTimer()

        # Connect the timer to the data-fetching function
        self.timer.timeout.connect(self.fetch_data_async)

        # ONA sync

        self.ona_sync_timer = QTimer()
        self.ona_sync_timer.timeout.connect(self.ona_fetch_data_sync_enabled)

        # ODK Data sync
        self.odk_sync_timer = QTimer()
        self.odk_sync_timer.timeout.connect(self.on_odk_data_sync_enabled)

        # Kobo Data sync
        self.kobo_sync_timer = QTimer()
        self.kobo_sync_timer.timeout.connect(self.on_kobo_data_sync_enabled)

        # date fields
        self.from_date = None
        self.to_date = None

        # misc
        self.page_size = 20
        self.data_count = 0
        self.fields = None
        self.excluded_types = [
            "deviceid",
            "end",
            "imei",
            "instanceID",
            "phonenumber",
            "simserial",
            "start",
            "subscriberid",
            "today",
            "uuid",
            "_media_all_received",
            "group",
            "repeat",
            "geopoint",
            "gps",
            "geoshape",
            "geotrace",
            "osm",
            "start-geopoint",
            "note",
        ]

        # Initialize QThreadPool for managing worker threads
        self.thread_pool = QThreadPool.globalInstance()

        self.is_interrupted = False

        self.asset_from_date = None

        # Add progress bar to the dialog
        # self.dlg.progress_bar.setValue(0)

        # init worker
        self.worker = None

        self.directory = "./geojson_data"  # Replace with your target directory
        # Create the directory if it doesn't exist
        os.makedirs(self.directory, exist_ok=True)

    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        :param message: String for translation.
        :type message: str, QString
        :returns: Translated string.
        :rtype: QString
        """
        return QCoreApplication.translate("FetchDataPlugin", message)

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        icon_path = os.path.join(self.plugin_dir, "icon.png")
        self.add_action(
            icon_path,
            text=self.tr("AfpolGIS"),
            callback=self.run,
            parent=self.iface.mainWindow(),
        )

    def add_action(
        self,
        icon_path,
        text,
        callback,
        parent=None,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        enabled=True,
    ):
        """Add a toolbar icon to the toolbar."""
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        if status_tip:
            action.setStatusTip(status_tip)
        if whats_this:
            action.setWhatsThis(whats_this)
        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)
        action.triggered.connect(callback)
        action.setEnabled(enabled)
        self.toolbar.addAction(action)
        self.iface.addPluginToMenu(self.menu, action)
        self.actions.append(action)
        return action

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(self.tr("&AfpolGIS"), action)
            self.iface.removeToolBarIcon(action)
        del self.toolbar

    def add_basemap(self):
        # Define the basemap URL (OpenStreetMap in this example)
        basemap_url = "type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        layer_name = "OpenStreetMap"

        # Create a raster layer
        basemap_layer = QgsRasterLayer(basemap_url, layer_name, "wms")

        existing_layer = None
        for layer in QgsProject.instance().mapLayers().values():
            if layer.name() == basemap_layer.name():
                existing_layer = True
                break

        # Check if the layer is valid
        if not basemap_layer.isValid():
            print("Failed to load the basemap layer!")
            return

        if not existing_layer:
            # Add the layer to the project
            QgsProject.instance().addMapLayer(basemap_layer)

            curr_layer = QgsProject.instance().mapLayersByName(f"{layer_name}")[0]

            # Access the active map canvas
            canvas = self.iface.mapCanvas()

            # Set the extent of the canvas to the basemap layer's extent
            canvas.setExtent(curr_layer.extent())

            canvas.refresh()

            print(f"{layer_name} basemap added and zoomed to native resolution.")

    def run(self):
        """Run method that performs all the real work."""
        # Show the dialog
        self.dlg.app_logs.appendPlainText(f"Run has been executed")
        self.dlg.show()
        # self.add_basemap()

    def fetch_data_async(
        self, api_url, formID, username, password, geo_field, page_size, directory
    ):
        """Start the data-fetching timer."""
        value = self.dlg.mQgsDoubleSpinBox.value()
        self.timer.setInterval(int(value) * 1000)
        self.timer.start()
        self.dlg.app_logs.appendPlainText(f"Start of Data Sync...\n")
        self.json_data = []
        self.worker = self.fetch_and_save_data(
            api_url,
            formID,
            username,
            password,
            geo_field,
            page_size,
            directory,
        )
        self.thread_pool.start(self.worker)
        self.dlg.app_logs.appendPlainText(f"Done")

    def providers_map(self):
        return {
            "Onadata": "api.whonghub.org",
            "GetODK": "aap-odk-sinp.cen-nouvelle-aquitaine.dev",
            "Kobo": "kf.kobotoolbox.org",
            "GTS": "gts.health",
        }

    def get_current_provider(self):
        providers = self.providers_map()
        # text = self.dlg.comboProviders.currentText()
        # return providers.get(text)

    def on_providers_change(self):
        # clear credentials input
        self.dlg.username.clear()
        self.dlg.mLineEditPass.clear()

        # text = self.dlg.comboProviders.currentText()
        providers = self.providers_map()
        layout = QtWidgets.QVBoxLayout(self.dlg)
        # selected_provider = providers.get(text)
        # if text == "GetODK":
        #     self.dlg.form_id.hide()
        #     self.dlg.form_id_label.hide()
        #     # self.dlg.btnFG.setGeometry(QtCore.QRect(160, 210, 401, 31))
        #     self.dlg.forms_dropdown = QtWidgets.QComboBox(self.dlg.widget)
        #     self.dlg.forms_dropdown.setGeometry(QtCore.QRect(160, 90, 401, 31))
        #     # self.dlg.btnFG.update()
        #     # self.dlg.btnFG.repaint()
        #     layout.addWidget(self.dlg.forms_dropdown)
        #     self.dlg.setLayout(layout)
        #     self.dlg.forms_dropdown.update()
        # self.dlg.app_logs.appendPlainText(f"Selected Layout {layout}")

    def stop_fetching(self):
        """Stop the data-fetching timer."""
        self.timer.stop()
        self.tr("Stopped fetching data.")
        self.dlg.app_logs.appendPlainText(f"Stopped fetching data.")

    def stop_data_fetching(self):
        if hasattr(self, "worker") and self.worker and self.worker.isRunning():
            self.worker.stop()
            self.is_interrupted = True
            self.worker.quit()
            self.worker.wait(500)  # Wait for the thread to finish
            self.iface.messageBar().pushMessage(
                "Notice", "Data fetching cancelled.", level=Qgis.Warning
            )

    def update_slider_value_label(self, value):
        self.dlg.slider_label.setText(
            str(value)
        )  # Update the label with the current slider value

    def on_from_date_changed(self, value):
        date_str = value.toString("yyyy-MM-dd")
        self.from_date = date_str

    def on_to_date_changed(self, value):
        date_str = value.toString("yyyy-MM-dd")
        self.to_date = date_str

    def cancel_button_clicked(self):
        self.reset_inputs()
        # self.dlg.close()

    def clear_logs(self):
        self.dlg.app_logs.clear()

    def fetch_dhis_org_units_handler(self):
        api_url = self.dlg.dhis_api_url.text()
        username = self.dlg.dhis_username.text()
        password = self.dlg.dhisMLineEdit.text()
        self.fetch_dhis_org_units(api_url, username, password)

    def on_dhis_org_units_change(self):
        org_units_data = self.dlg.comboDhisOrgUnits.currentData()
        if org_units_data:
            curr_org_datasets = org_units_data.get("dataSets")
            if curr_org_datasets:
                for dataset in curr_org_datasets:
                    self.dlg.comboDhisDataSets.addItem(dataset.get("name"))

        return

    def fetch_dhis_org_units(self, api_url, username, password):
        auth = HTTPBasicAuth(username, password)
        adm_level = self.dlg.ComboDhisAdminLevels.currentText()
        cleaned_adm_lvl = adm_level.split(" ")[-1]
        self.dlg.comboDhisOrgUnits.clear()
        self.dlg.comboDhisDataSets.clear()
        self.dlg.btnFetchDhisOrgUnits.setEnabled(False)
        self.dlg.btnFetchDhisOrgUnits.setText("Connecting...")
        self.dlg.btnFetchDhisOrgUnits.repaint()

        page = 1

        feature_collection = {
            "type": "FeatureCollection",
            "features": [],
        }

        url = f"https://{api_url}/api/organisationUnits"
        hasData = True

        while hasData:
            params = [
                ("fields", "id,name,children[id,name],dataSets[id,name],geometry"),
                ("filter", f"level:eq:{cleaned_adm_lvl}"),
                ("filter", "children:gte:0"),
                ("page", page),
                ("pageSize", 1000),
            ]

            response = self.fetch_with_retries(url, auth, params)
            self.dlg.app_logs.appendPlainText(f"Res URL - {response.url}")
            if response.status_code == 200:
                data = response.json()
                result = data.get("organisationUnits")
                pager = data.get("pager")
                if result:
                    for datum in result:
                        org_id = datum.get("id")
                        org_name = datum.get("name")
                        org_datasets = datum.get("dataSets")
                        self.dlg.comboDhisOrgUnits.addItem(
                            org_name, {"id": org_id, "dataSets": org_datasets}
                        )
                        if datum.get("geometry"):
                            geometry = datum.get("geometry")
                            feature_collection["features"].append(
                                {
                                    "type": "Feature",
                                    "geometry": geometry,
                                    "properties": {},
                                }
                            )
                elif not pager.get("nextPage"):
                    hasData = False
                    self.dlg.btnFetchDhisOrgUnits.setEnabled(True)
                    self.dlg.btnFetchDhisOrgUnits.setText("Connect")
                    self.dlg.btnFetchDhisOrgUnits.repaint()
                else:
                    self.iface.messageBar().pushMessage(
                        "Notice", "No Data Found", level=Qgis.Warning
                    )
                    self.dlg.btnFetchDhisOrgUnits.setEnabled(True)
                    self.dlg.btnFetchDhisOrgUnits.setText("Connect")
                    self.dlg.btnFetchDhisOrgUnits.repaint()
                    break
            else:
                self.iface.messageBar().pushMessage(
                    "Error",
                    f"Error fetching data: {response.status_code}",
                    level=Qgis.Critical,
                )
                self.dlg.btnFetchDhisOrgUnits.setEnabled(True)
                self.dlg.btnFetchDhisOrgUnits.setText("Connect")
                self.dlg.btnFetchDhisOrgUnits.repaint()
                break

            page += 1

        if feature_collection["features"] and len(feature_collection["features"]) > 0:
            self.load_data_to_qgis(
                feature_collection, "dhis", f"level_{cleaned_adm_lvl}"
            )

        return

    def fetch_gts_tracking_rounds_data_handler(self):
        api_url = self.dlg.gts_api_url.text()
        username = self.dlg.gts_username.text()
        password = self.dlg.gtsMLineEdit.text()
        selected_tracking_round = self.dlg.comboGTSTrackingRounds.currentData()

        tracking_round_data = self.dlg.comboGTSFieldActivities.currentData()
        self.dlg.app_logs.appendPlainText(
            f"Selected Track - {selected_tracking_round}, Tracking round: {tracking_round_data}"
        )

        if selected_tracking_round and tracking_round_data:
            single_tracking_url = selected_tracking_round.get("url")
            single_round_name = selected_tracking_round.get("round_name")

            url = f"https://{api_url}/fastapi/odata/v1/{single_tracking_url}"
            auth = HTTPBasicAuth(username, password)
            response = self.fetch_with_retries(url, auth)

            feature_collection = {
                "type": "FeatureCollection",
                "features": [],
            }

            params = {"$top": 50000, "$skip": 0}

            hasData = True

            while hasData:
                self.dlg.gtsOkButton.setEnabled(False)
                response = self.fetch_with_retries(url, auth, params)
                if response.status_code == 200:
                    self.dlg.gtsProgressBar.setValue(50)
                    data = response.json()
                    data_list = data.get("value")

                    if data_list:
                        for datum in data_list:
                            long = (
                                datum.get("X") or datum.get("Lon") or datum.get("Long")
                            )
                            lat = datum.get("Y") or datum.get("Lat")

                            if lat and long:
                                geometry = {
                                    "type": "Point",
                                    "coordinates": [float(long), float(lat)],
                                }
                                # try:
                                #     del datum["geometry"]
                                # except ValueError:
                                #     pass
                                feature_collection["features"].append(
                                    {
                                        "type": "Feature",
                                        "geometry": geometry,
                                        "properties": datum,
                                    }
                                )
                    else:
                        hasData = False
                        self.dlg.gtsProgressBar.setValue(100)
                        if (
                            feature_collection["features"]
                            and len(feature_collection["features"]) == 0
                        ):
                            self.dlg.gtsProgressBar.setValue(0)
                            self.iface.messageBar().pushMessage(
                                "Notice",
                                "No Data Found",
                                level=Qgis.Warning,
                                duration=15,
                            )
                        self.dlg.gtsOkButton.setEnabled(True)
                else:
                    hasData = False
                    self.dlg.gtsProgressBar.setValue(0)
                    self.iface.messageBar().pushMessage(
                        "Error",
                        f"Error fetching data: {response.status_code}",
                        level=Qgis.Critical,
                        duration=15,
                    )
                    self.dlg.gtsOkButton.setEnabled(True)

                params["$skip"] += params["$top"]

            if (
                feature_collection["features"]
                and len(feature_collection["features"]) > 0
            ):
                self.load_data_to_qgis(
                    feature_collection, "gts", "_".join(single_round_name.split(" "))
                )

    def handle_gts_cancel_btn(self):
        self.dlg.gtsProgressBar.setValue(0)
        self.dlg.gtsOkButton.setEnabled(True)

    def on_gts_tracking_rounds_on_change(self):
        self.dlg.gtsOkButton.setEnabled(True)

    def on_gts_field_activity_change(self):
        field_activity_data = self.dlg.comboGTSFieldActivities.currentData()
        self.dlg.comboGTSTrackingRounds.clear()

        if field_activity_data:
            for datum in field_activity_data:
                url = datum.get("url")
                round_name = datum.get("round_name")
                self.dlg.comboGTSTrackingRounds.addItem(
                    round_name, {"url": url, "round_name": round_name}
                )

    def fetch_gts_tables_data(self, api_url, username, password, tables_url):
        auth = HTTPBasicAuth(username, password)
        gts_field_activities = dict()
        url = f"https://{api_url}/fastapi/odata/v1/{tables_url}"
        response = self.fetch_with_retries(url, auth)
        if response.status_code == 200:
            data = response.json()
            data_list = data.get("value")
            if data_list:
                for datum in data_list:
                    if tables_url == "track_table_names":
                        table_name = datum.get("table_name")
                        tracking_round_id = datum.get("tracking_round_id")
                        field_activity_name = datum.get("field_activity_name")
                        tracking_round_name = datum.get("tracking_round_name")
                        tracking_round_nb_tracks = datum.get("tracking_round_nb_tracks")

                        if field_activity_name:
                            if not gts_field_activities.get(field_activity_name):
                                gts_field_activities[field_activity_name] = []
                                gts_field_activities[field_activity_name].append(
                                    {
                                        "round_name": tracking_round_name,
                                        "url": f"track/{tracking_round_id}",
                                    }
                                )
                            else:
                                gts_field_activities[field_activity_name].append(
                                    {
                                        "round_name": tracking_round_name,
                                        "url": f"track/{tracking_round_id}",
                                    }
                                )

                    if tables_url == "odk_table_names":
                        table_name = datum.get("table_name")
                        form_id = datum.get("form_id")
                        tracking_round_id = datum.get("tracking_round_id")
                        tracking_round_name = datum.get("tracking_round_name")
                        field_activity_name = datum.get("field_activity_name")
                        if field_activity_name:
                            if not gts_field_activities.get(field_activity_name):
                                gts_field_activities[field_activity_name] = []
                                gts_field_activities[field_activity_name].append(
                                    {
                                        "round_name": tracking_round_name,
                                        "url": f"odk/{tracking_round_id}_{form_id}",
                                    }
                                )
                            else:
                                gts_field_activities[field_activity_name].append(
                                    {
                                        "round_name": tracking_round_name,
                                        "url": f"odk/{tracking_round_id}_{form_id}",
                                    }
                                )

                    if tables_url == "indicator_table_names":
                        table_name = datum.get("table_name")
                        tracking_round_id = datum.get("tracking_round_id")
                        indicator_level = datum.get("indicator_level")
                        if "level" in indicator_level:
                            indicator_level = indicator_level.split("_")[-1]
                        elif "targeted" in indicator_level:
                            indicator_level = "ta"

                        tracking_round_name = datum.get("tracking_round_name")

                        if field_activity_name:
                            if not gts_field_activities.get(field_activity_name):
                                gts_field_activities[field_activity_name] = []
                                gts_field_activities[field_activity_name].append(
                                    {
                                        "round_name": tracking_round_name,
                                        "url": f"indicator/{tracking_round_id}_{indicator_level}",
                                    }
                                )
                            else:
                                gts_field_activities[field_activity_name].append(
                                    {
                                        "round_name": tracking_round_name,
                                        "url": f"indicator/{tracking_round_id}_{indicator_level}",
                                    }
                                )

                for key, val in gts_field_activities.items():
                    self.dlg.comboGTSFieldActivities.addItem(key, val)

                self.dlg.comboGTSFieldActivities.setEnabled(True)
            else:
                self.iface.messageBar().pushMessage(
                    "Notice", "No Data Found", level=Qgis.Warning
                )
        else:
            self.iface.messageBar().pushMessage(
                "Error",
                f"Error fetching data: {response.status_code}",
                level=Qgis.Critical,
            )

    def on_gts_tables_combo_box_change(self):
        api_url = self.dlg.gts_api_url.text()
        username = self.dlg.gts_username.text()
        password = self.dlg.gtsMLineEdit.text()
        tables_url = self.dlg.comboGTSTableTypes.currentData()

        # clear table names dropdown
        self.dlg.comboGTSFieldActivities.clear()

        # Fetch data for each GTS Indicator
        self.fetch_gts_tables_data(api_url, username, password, tables_url)

    def fetch_gts_indicators_handler(self):
        api_url = self.dlg.gts_api_url.text()
        username = self.dlg.gts_username.text()
        password = self.dlg.gtsMLineEdit.text()
        self.fetch_gts_indicators(api_url, username, password)

    def update_gts_ui_components(self, text="Connect"):
        self.dlg.comboGTSTableTypes.setEnabled(True)
        self.dlg.btnFetchGTSTables.setText(text)
        self.dlg.btnFetchGTSTables.setEnabled(True)
        self.dlg.btnFetchGTSTables.repaint()
        time.sleep(0.2)

    def fetch_gts_indicators(self, api_url, username, password):
        auth = HTTPBasicAuth(username, password)
        self.dlg.comboGTSTableTypes.clear()
        self.dlg.btnFetchGTSTables.setEnabled(False)
        self.dlg.btnFetchGTSTables.setText("Connecting...")
        self.dlg.btnFetchGTSTables.repaint()
        field_activities_set = set()
        time.sleep(0.2)

        url = f"https://{api_url}/fastapi/odata/v1/"

        response = self.fetch_with_retries(url, auth)
        if response.status_code == 200:
            data = response.json()
            if data:
                data_list = data.get("value")
                if data_list:
                    gts_tables = [
                        datum
                        for datum in data_list
                        if "table_names" in datum.get("name")
                    ]

                    for table in gts_tables:
                        table_name = table.get("name")
                        table_url = table.get("url")
                        self.dlg.comboGTSTableTypes.addItem(table_name, table_url)

                    self.update_gts_ui_components()
                else:
                    self.update_gts_ui_components()
                    self.iface.messageBar().pushMessage(
                        "Notice", "No Data Found", level=Qgis.Warning
                    )
            else:
                self.update_gts_ui_components()
                self.iface.messageBar().pushMessage(
                    "Notice", "No Data Found", level=Qgis.Warning
                )
        else:
            self.update_gts_ui_components()
            self.iface.messageBar().pushMessage(
                "Error",
                f"Error fetching data: {response.status_code}",
                level=Qgis.Critical,
            )

        return

    def fetch_kobo_form_data_clicked(self):
        api_url = self.dlg.kobo_api_url.text()
        selected_form = self.dlg.comboKoboForms.currentData()
        asset_id = None
        if selected_form:
            asset_id = selected_form.get("asset_uid")
        username = self.dlg.kobo_username.text()
        password = self.dlg.koboMLineEdit.text()
        geo_field = self.dlg.comboKoboGeoFields.currentText()
        kobo_sync_interval = int(self.dlg.koboSyncInterval.value())

        kobo_from_date = self.dlg.KoboDateTimeFrom.date()
        kobo_to_date = self.dlg.KoboDateTimeTo.date()

        from_dt = datetime(
            kobo_from_date.year(), kobo_from_date.month(), kobo_from_date.day(), 0, 0, 0
        )  # 12:00 AM
        to_dt = datetime(
            kobo_to_date.year(), kobo_to_date.month(), kobo_to_date.day(), 23, 59, 59
        )

        # Convert datetime to timestamp string
        kobo_from_timestamp = from_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[
            :-3
        ]  # Adjust to match original format
        kobo_to_timestamp = to_dt.strftime("%Y-%m-%dT%H:%M:%S")

        if asset_id:
            self.fetch_and_save_kobo_data(
                api_url,
                username,
                password,
                asset_id,
                geo_field,
                kobo_from_timestamp,
                kobo_to_timestamp,
            )

            if kobo_sync_interval > 0:
                self.kobo_sync_timer.start(kobo_sync_interval * 1000)

    def on_kobo_data_sync_enabled(self):
        api_url = self.dlg.kobo_api_url.text()
        asset_id = self.dlg.comboKoboForms.currentData()
        username = self.dlg.kobo_username.text()
        password = self.dlg.koboMLineEdit.text()
        geo_field = self.dlg.comboKoboGeoFields.currentText()

        # Fetch latest date fields
        self.fetch_kobo_date_range_fields(api_url, username, password, asset_id)
        time.sleep(1)

        # Extract date fields from time widget
        kobo_from_date = self.dlg.KoboDateTimeFrom.date()
        kobo_to_date = self.dlg.KoboDateTimeTo.date()

        from_dt = datetime(
            kobo_from_date.year(), kobo_from_date.month(), kobo_from_date.day(), 0, 0, 0
        )  # 12:00 AM
        to_dt = datetime(
            kobo_to_date.year(), kobo_to_date.month(), kobo_to_date.day(), 23, 59, 59
        )

        # Convert datetime to timestamp string
        kobo_from_timestamp = from_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[
            :-3
        ]  # Adjust to match original format
        kobo_to_timestamp = to_dt.strftime("%Y-%m-%dT%H:%M:%S")

        if hasattr(self, "vlayer"):
            if self.vlayer.get("layer"):
                self.vlayer["syncData"] = True

        self.fetch_and_save_kobo_data(
            api_url,
            username,
            password,
            asset_id,
            geo_field,
            kobo_from_timestamp,
            kobo_to_timestamp,
        )

    def fetch_and_save_kobo_data(
        self, api_url, username, password, asset_id, geo_field, from_date, to_date
    ):
        auth = HTTPBasicAuth(username, password)
        selected_form = self.dlg.comboKoboForms.currentData()
        asset_name = selected_form.get("asset_name")
        self.dlg.koboOkButton.setEnabled(False)

        self.dlg.koboOkButton.repaint()
        time.sleep(0.5)

        sort_param = json.dumps({"_submission_time": -1})

        params = {
            "sort": sort_param,
            "limit": 1000,
            "start": 0,
        }

        if from_date and to_date:
            params["query"] = json.dumps(
                {"_submission_time": {"$gte": from_date, "$lte": to_date}}
            )

        feature_collection = {
            "type": "FeatureCollection",
            "features": [],
        }

        url = f"https://{api_url}/api/v2/assets/{asset_id}/data.json"
        hasData = True

        while hasData:
            response = self.fetch_with_retries(url, auth, params=params)
            if response.status_code == 200:
                data = response.json()
                data_list = data.get("results")
                if data_list:
                    self.dlg.koboPorgressBar.setValue(100)
                    for datum in data_list:
                        self.get_geo_data(datum, geo_field, feature_collection)

                elif not data.get("next"):
                    hasData = False
                    self.dlg.koboOkButton.setEnabled(True)
                else:
                    hasData = False
                    self.iface.messageBar().pushMessage(
                        "Notice", "No Data Found", level=Qgis.Warning
                    )
                    self.dlg.koboOkButton.setEnabled(True)
                    break
            else:
                hasData = False
                self.iface.messageBar().pushMessage(
                    "Error",
                    f"Error fetching data: {response.status_code}",
                    level=Qgis.Critical,
                )
                self.dlg.koboOkButton.setEnabled(True)
                break

            params["start"] += params["limit"]

        # count = len(feature_collection["features"])
        # self.dlg.app_logs.appendPlainText(f"Features count: {count}")

        if feature_collection["features"] and len(feature_collection["features"]) > 0:
            cleaned_asset_name = "".join(asset_name.split(" "))

            self.load_data_to_qgis(feature_collection, cleaned_asset_name, geo_field)

    def fetch_kobo_date_range_fields(self, api_url, username, password, asset_id):
        auth = HTTPBasicAuth(username, password)
        selected_form = self.dlg.comboKoboForms.currentData()
        asset_from_date = selected_form.get("date_created")
        url = f"https://{api_url}/api/v2/assets/{asset_id}/data.json"
        sort_param = json.dumps({"_submission_time": -1})
        params = {
            "sort": sort_param,
            "start": 0,
            "limit": 1,  # just a single submission is required
        }

        response = self.fetch_with_retries(url, auth, params)

        if response.status_code == 200:
            data = response.json()
            results = data.get("results")
            if results:
                latest_submission_date = results[0].get("_submission_time")

                from_dt = datetime.strptime(asset_from_date, "%Y-%m-%dT%H:%M:%S.%fZ")
                to_dt = datetime.strptime(latest_submission_date, "%Y-%m-%dT%H:%M:%S")

                # Adjust the times
                from_dt = from_dt.replace(
                    hour=0, minute=0, second=0, microsecond=0
                )  # 12:00 AM
                to_dt = to_dt.replace(hour=23, minute=59, second=59, microsecond=0)

                from_date = QDate(from_dt.year, from_dt.month, from_dt.day)
                to_date = QDate(to_dt.year, to_dt.month, to_dt.day)

                self.dlg.KoboDateTimeFrom.setDate(from_date)
                self.dlg.KoboDateTimeTo.setDate(to_date)

                self.dlg.KoboDateTimeFrom.setEnabled(True)
                self.dlg.KoboDateTimeTo.setEnabled(True)

                self.dlg.KoboDateTimeFrom.repaint()
                self.dlg.KoboDateTimeTo.repaint()
                self.dlg.koboOkButton.setEnabled(True)
                time.sleep(0.5)
            else:
                self.iface.messageBar().pushMessage(
                    "Notice", "No Data Found", level=Qgis.Warning
                )
        else:
            self.iface.messageBar().pushMessage(
                "Error",
                f"Error fetching data: {response.status_code}",
                level=Qgis.Critical,
            )

        return

    def fetch_kobo_geo_fields(self, api_url, username, password, asset_id):
        auth = HTTPBasicAuth(username, password)
        url = f"https://{api_url}/api/v2/assets/{asset_id}.json"
        params = {"metadata": "on"}
        self.dlg.comboKoboGeoFields.setEnabled(False)
        response = self.fetch_with_retries(url, auth, params=params)
        if response.status_code == 200:
            self.dlg.comboKoboGeoFields.clear()
            data = response.json()
            self.asset_from_date = data.get("date_created")
            content = data.get("content")
            survey_arr = content.get("survey")
            geo_fields = [
                field.get("$autoname") or field.get("name")
                for field in survey_arr
                if field.get("type") in self.geo_types
            ]
            if geo_fields:
                self.dlg.comboKoboGeoFields.addItems(geo_fields)
                self.dlg.comboKoboGeoFields.setEnabled(True)
        else:
            self.iface.messageBar().pushMessage(
                "Error",
                f"Error fetching data: {response.status_code}",
                level=Qgis.Critical,
            )

    def on_combo_box_kobo_forms_change(self):
        api_url = self.dlg.kobo_api_url.text()
        username = self.dlg.kobo_username.text()
        password = self.dlg.koboMLineEdit.text()
        selected_form = self.dlg.comboKoboForms.currentData()
        asset_id = selected_form.get("asset_uid")
        self.fetch_kobo_geo_fields(api_url, username, password, asset_id)
        self.fetch_kobo_date_range_fields(api_url, username, password, asset_id)

    def fetch_kobo_assets_handler(self):
        api_url = self.dlg.kobo_api_url.text()
        username = self.dlg.kobo_username.text()
        password = self.dlg.koboMLineEdit.text()
        self.fetch_kobo_assets(api_url, username, password)

    def fetch_kobo_assets(self, api_url, username, password):
        auth = HTTPBasicAuth(username, password)
        self.dlg.comboKoboForms.clear()
        self.dlg.btnFetchKoboForms.setEnabled(False)
        self.dlg.btnFetchKoboForms.setText("Connecting...")
        self.dlg.btnFetchKoboForms.repaint()
        time.sleep(0.5)

        url = f"https://{api_url}/api/v2/assets.json"
        response = self.fetch_with_retries(url, auth)

        if response.status_code == 200:
            assets = response.json()
            assets_list = assets.get("results")
            if assets_list:
                assets_with_geo_data = [
                    asset
                    for asset in assets_list
                    if asset.get("summary", {}).get("geo")
                ]

                if assets_with_geo_data:
                    self.asset_from_date = assets_with_geo_data[0].get("date_created")
                    for geo_asset in assets_with_geo_data:
                        asset_uid = geo_asset.get("uid")
                        asset_label = geo_asset.get("name")
                        self.dlg.comboKoboForms.addItem(
                            asset_label,
                            {
                                "asset_uid": asset_uid,
                                "date_created": geo_asset.get("date_created"),
                                "asset_name": asset_label,
                            },
                        )
                    self.dlg.comboKoboForms.setEnabled(True)

            self.dlg.btnFetchKoboForms.setEnabled(True)
            self.dlg.btnFetchKoboForms.setText("Connect")
            self.dlg.btnFetchKoboForms.repaint()
            time.sleep(0.5)

        else:
            self.iface.messageBar().pushMessage(
                "Error",
                f"Error fetching data: {response.status_code}",
                level=Qgis.Critical,
            )
            self.dlg.btnFetchKoboForms.setText("Connect")
            self.dlg.btnFetchKoboForms.setEnabled(True)

        return

    def on_combo_box_geo_fields_change(self, index):
        text = self.dlg.comboOnaGeoFields.currentText()
        self.curr_geo_field = text.split("-")[0].strip()
        self.dlg.onaProgressBar.setValue(0)

    def flatten_es_props(self, datum, parent_key="", sep="."):
        items = []

        if isinstance(datum, dict):
            for key, value in datum.items():
                new_key = f"{parent_key}{sep}{key}" if parent_key else key
                items.extend(self.flatten_es_props(value, new_key, sep=sep).items())
        elif isinstance(datum, list):
            for index, value in enumerate(datum):
                new_key = f"{parent_key}{sep}{index}" if parent_key else str(index)
                items.extend(self.flatten_es_props(value, new_key, sep=sep).items())
        else:
            items.append((parent_key, datum))

        return dict(items)

    def on_es_topography_change(self):
        api_url = self.dlg.es_api_url.text()
        es_api_version = self.dlg.esAPIVersion.text()
        topography = self.dlg.combESTopology.currentText()
        topography_param = topography.lower()

        url = f"https://{api_url}/api/{es_api_version}-prod/{topography_param}"

        response = self.fetch_with_retries(url)

        feature_collection = {
            "type": "FeatureCollection",
            "features": [],
        }

        if response.status_code == 200:
            data = response.json()
            if data:
                for datum in data:
                    geometry = datum.get("geometry")
                    if geometry:
                        try:
                            del datum["geometry"]
                        except ValueError:
                            pass

                        flattened_props = self.flatten_es_props(datum)
                        feature_collection["features"].append(
                            {
                                "type": "Feature",
                                "geometry": geometry,
                                "properties": flattened_props,
                            }
                        )
                if (
                    feature_collection["features"]
                    and len(feature_collection["features"]) > 0
                ):
                    self.load_data_to_qgis(feature_collection, "es", topography_param)
            else:
                self.iface.messageBar().pushMessage(
                    "Notice", "No Data Found", level=Qgis.Warning
                )
        else:
            self.iface.messageBar().pushMessage(
                "Error",
                f"Error fetching data: {response.status_code}",
                level=Qgis.Critical,
            )

    def on_odk_forms_combo_box_change(self):
        form_data = self.dlg.comboODKForms.currentData()
        form_id_str = form_data.get("form_id")
        project_id = form_data.get("project_id")
        api_url = self.dlg.odk_api_url.text()
        username = self.dlg.odk_username.text()
        password = self.dlg.odkmLineEdit.text()
        self.fetch_odk_geo_fields(api_url, username, password, project_id, form_id_str)
        self.fetch_odk_date_range_fields(
            api_url, username, password, project_id, form_id_str
        )

        # fetch time fields to activate date range filters

    def fetch_odk_date_range_fields(
        self, api_url, username, password, project_id, form_id_str
    ):
        auth = HTTPBasicAuth(username, password)
        url = f"https://{api_url}/v1/projects/{project_id}/forms/{form_id_str}"

        # headers for additional metadata
        headers = {"X-Extended-Metadata": "true"}
        response = self.fetch_with_retries(url, auth, params=None, headers=headers)
        if response.status_code == 200:
            data = response.json()
            from_timestamp = data.get("createdAt")
            to_timestamp = data.get("lastSubmission")

            from_dt = datetime.strptime(from_timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
            to_dt = datetime.strptime(to_timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")

            # Adjust the times
            from_dt = from_dt.replace(
                hour=0, minute=0, second=0, microsecond=0
            )  # 12:00 AM
            to_dt = to_dt.replace(
                hour=23, minute=59, second=59, microsecond=0
            )  # 11:59:59 PM

            from_date = QDate(from_dt.year, from_dt.month, from_dt.day)
            to_date = QDate(to_dt.year, to_dt.month, to_dt.day)

            self.dlg.ODKDateTimeFrom.setDate(from_date)
            self.dlg.ODKDateTimeTo.setDate(to_date)

            self.dlg.ODKDateTimeFrom.update()
            self.dlg.ODKDateTimeTo.update()
            self.dlg.ODKDateTimeFrom.setEnabled(True)
            self.dlg.ODKDateTimeTo.setEnabled(True)

            self.dlg.odkOkButton.setEnabled(True)

            self.dlg.ODKDateTimeFrom.setDisplayFormat("yyyy-MM-dd")
            self.dlg.ODKDateTimeTo.setDisplayFormat("yyyy-MM-dd")

            # set calendar range
            # self.dlg.ODKDateTimeFrom.setDateTimeRange(
            #     from_date, to_date)
            # self.dlg.ODKDateTimeTo.setDateTimeRange(
            #     from_date, to_date)

            self.dlg.ODKDateTimeFrom.update()
            self.dlg.ODKDateTimeTo.update()
        else:
            self.iface.messageBar().pushMessage(
                "Error",
                f"Error fetching Date Ranges: {response.status_code}",
                level=Qgis.Critical,
            )
            self.dlg.ODKDateTimeFrom.setEnabled(False)
            self.dlg.ODKDateTimeTo.setEnabled(False)

    def fetch_odk_geo_fields(
        self, api_url, username, password, project_id, form_id_str
    ):
        auth = HTTPBasicAuth(username, password)
        url = f"https://{api_url}/v1/projects/{project_id}/forms/{form_id_str}/fields"
        params = {"odata": True}
        self.dlg.comboODKGeoFields.setEnabled(False)
        response = self.fetch_with_retries(url, auth, params=params)
        if response.status_code == 200:
            self.dlg.comboODKGeoFields.clear()
            data = response.json()
            geo_fields = [
                field.get("name")
                for field in data
                if field.get("type") in self.geo_types
            ]
            if geo_fields:
                self.dlg.comboODKGeoFields.addItems(geo_fields)
                self.dlg.comboODKGeoFields.setEnabled(True)
        else:
            self.iface.messageBar().pushMessage(
                "Error",
                f"Error fetching data: {response.status_code}",
                level=Qgis.Critical,
            )

    def fetch_and_save_geojson_fields(self, api_url, username, password, formID):
        self.fetchGeoFields(api_url, username, password, formID)

    def fetch_ona_forms_handler(self):
        self.stop_workers()
        api_url = self.dlg.onadata_api_url.text()
        username = self.dlg.onadata_username.text()
        password = self.dlg.onaMLineEdit.text()
        sync = self.dlg.onaSyncInterval.value()
        self.dlg.app_logs.appendPlainText(f"sync interval - {sync}")
        self.fetch_ona_forms(api_url, username, password)

    def handle_ona_forms_data_fetched(self, data):
        if data:
            for datum in data:
                title = datum.get("title")
                form_id = datum.get("formid")
                self.dlg.comboOnaForms.addItem(title, form_id)

            self.dlg.btnFetchOnaForms.setEnabled(True)
            self.dlg.btnFetchOnaForms.setText("Connect")
            self.dlg.btnFetchOnaForms.repaint()

        self.dlg.comboOnaForms.setEnabled(True)

    def handle_ona_forms_fetch_error(self, msg):
        self.iface.messageBar().pushMessage(
            "Error", f"Error fetching data: {msg}", level=Qgis.Critical
        )

    def handle_ona_forms_no_data(self, msg):
        self.iface.messageBar().pushMessage("Notice", {msg}, level=Qgis.Warning)
        self.dlg.btnFetchOnaForms.setEnabled(True)
        self.dlg.btnFetchOnaForms.setText("Connect")
        self.dlg.btnFetchOnaForms.repaint()

    def handle_ona_forms_status_error(self, msg):
        self.iface.messageBar().pushMessage(
            "Error", f"Error fetching data: {msg}", level=Qgis.Critical
        )
        self.dlg.btnFetchOnaForms.setEnabled(True)
        self.dlg.btnFetchOnaForms.setText("Connect")
        self.dlg.btnFetchOnaForms.repaint()

    def fetch_ona_forms(self, api_url, username, password):
        auth = HTTPBasicAuth(username, password)
        self.dlg.comboOnaForms.clear()
        self.dlg.btnFetchOnaForms.setEnabled(False)
        self.dlg.btnFetchOnaForms.setText("Connecting...")
        self.dlg.btnFetchOnaForms.repaint()

        url = f"https://{api_url}/{username}/formList"

        self.fetch_ona_forms_worker = FetchOnaFormsThread(
            url, auth, params=None, headers=None
        )

        # Connect signals to the handler methods
        self.fetch_ona_forms_worker.data_fetched.connect(
            self.handle_ona_forms_data_fetched
        )
        self.fetch_ona_forms_worker.error_occurred.connect(
            self.handle_ona_forms_fetch_error
        )
        self.fetch_ona_forms_worker.no_data.connect(self.handle_ona_forms_no_data)
        self.fetch_ona_forms_worker.status_error.connect(
            self.handle_ona_forms_status_error
        )
        self.fetch_ona_forms_worker.start()

    def handle_geo_fields_fetched(self, data):
        if isinstance(data, dict):
            geo_fields_set = data.get("geo_fields_set")
            geo_fields_dict = data.get("geo_fields_dict")

            for i, gf in enumerate(geo_fields_set):
                cleaned_gf = gf.strip()
                self.dlg.comboOnaGeoFields.addItem(cleaned_gf)
                geo_label = geo_fields_dict[cleaned_gf]
                if geo_label:
                    self.dlg.comboOnaGeoFields.setItemText(
                        i, f"{cleaned_gf} - ({geo_label})"
                    )

            self.dlg.onaOkButton.setEnabled(True)

            self.dlg.comboOnaForms.setEnabled(True)
            self.dlg.comboOnaGeoFields.setEnabled(True)

            self.dlg.app_logs.appendPlainText(
                f"Number of Geo Fields Found: {len(geo_fields_set)} \n"
            )
    
    def handle_geo_fields_progress(self, data):
        if isinstance(data, str):
            self.dlg.app_logs.appendPlainText(data)
        elif isinstance(data, dict):
            page = data.get("curr_page")
            total_pages = data.get("total_pages")
            progress = (int(page) / int(total_pages)) * 100 if int(total_pages) > 1 else 100
            self.dlg.onaProgressBar.setValue(math.ceil(progress))

    def fetch_ona_form_geo_fields(self):
        # clear geo fields combo box

        self.dlg.comboOnaForms.setEnabled(False)
        self.dlg.onaOkButton.setEnabled(False)
        self.dlg.comboOnaForms.repaint()
        self.dlg.onaOkButton.repaint()

        self.dlg.comboOnaGeoFields.clear()

        self.dlg.comboOnaGeoFields.setEnabled(False)
        self.dlg.comboOnaGeoFields.repaint()
        self.dlg.app_logs.clear()
        # reset geo fields
        self.geo_fields = set()

        api_url = self.dlg.onadata_api_url.text()
        formID = self.dlg.comboOnaForms.currentData()
        username = self.dlg.onadata_username.text()
        password = self.dlg.onaMLineEdit.text()

        auth = HTTPBasicAuth(username, password)
        url = f"https://{api_url}/api/v1/forms/{formID}/versions"

        self.fetch_ona_geo_fields_worker = FetchOnaGeoFieldsThread(
            url, auth, params=None, headers=None, formID=formID
        )

        self.fetch_ona_geo_fields_worker.data_fetched.connect(
            self.handle_geo_fields_fetched
        )
        self.fetch_ona_geo_fields_worker.progress_updated.connect(
            self.handle_geo_fields_progress
        )
        self.fetch_ona_geo_fields_worker.count_and_date_fields_fetched.connect(
            self.handle_date_and_count_fields
        )
        self.fetch_ona_geo_fields_worker.count_and_date_fields_error_occurred.connect(
            self.handle_date_and_count_fields_error
        )
        self.fetch_ona_geo_fields_worker.error_occurred.connect(self.handle_fetch_error)
        self.fetch_ona_geo_fields_worker.status_error.connect(self.handle_status_error)
        self.fetch_ona_geo_fields_worker.start()

    def fetch_odk_forms_handler(self):
        api_url = self.dlg.odk_api_url.text()
        username = self.dlg.odk_username.text()
        password = self.dlg.odkmLineEdit.text()
        self.fetch_odk_projects(api_url, username, password)

    def fetch_odk_forms_per_proj(self, api_url, username, password, project_ids):
        auth = HTTPBasicAuth(username, password)
        for proj_id in project_ids:
            url = f"https://{api_url}/v1/projects/{proj_id}/forms"
            response = self.fetch_with_retries(url, auth)
            if response.status_code == 200:
                forms = response.json()
                if forms:
                    for i, form in enumerate(forms):
                        form_id = form.get("xmlFormId")
                        form_name = form.get("name")
                        project_id = form.get("projectId")
                        self.dlg.comboODKForms.addItem(
                            form_name, {"form_id": form_id, "project_id": project_id}
                        )
                        self.dlg.comboODKForms.setItemText(i, form_id)
                        if not self.odk_forms_to_projects_map.get(form_id):
                            self.odk_forms_to_projects_map[form_id] = proj_id
                    self.dlg.btnFetchODKForms.setEnabled(True)
                    self.dlg.btnFetchODKForms.setText("Connect")
                    self.dlg.btnFetchODKForms.repaint()
                    self.dlg.comboODKForms.setEnabled(True)
                else:
                    self.iface.messageBar().pushMessage(
                        "Notice", "No Forms Found", level=Qgis.Warning
                    )
            else:
                self.dlg.btnFetchODKForms.setEnabled(True)
                self.dlg.btnFetchODKForms.setText("Connect")
                self.dlg.btnFetchODKForms.repaint()
        return

    def fetch_odk_projects(self, api_url, username, password):
        auth = HTTPBasicAuth(username, password)
        self.dlg.comboODKForms.clear()
        self.dlg.btnFetchODKForms.setEnabled(False)
        self.dlg.btnFetchODKForms.setText("Connecting...")
        self.dlg.btnFetchODKForms.repaint()

        url = f"https://{api_url}/v1/projects"
        response = self.fetch_with_retries(url, auth)

        if response.status_code == 200:
            odk_projects = response.json()
            project_ids = [project.get("id") for project in odk_projects]
            if project_ids:
                self.fetch_odk_forms_per_proj(api_url, username, password, project_ids)
            else:
                self.iface.messageBar().pushMessage(
                    "Notice", "No Projects Found", level=Qgis.Warning
                )
                self.dlg.btnFetchODKForms.setEnabled(True)
        else:
            self.iface.messageBar().pushMessage(
                "Error",
                f"Error fetching data: {response.status_code}",
                level=Qgis.Critical,
            )
            self.dlg.btnFetchODKForms.setText("Connect")
            self.dlg.btnFetchODKForms.setEnabled(True)

    def on_odk_data_sync_enabled(self):
        api_url = self.dlg.odk_api_url.text()
        form_id_str = self.dlg.comboODKForms.currentText()
        username = self.dlg.odk_username.text()
        password = self.dlg.odkmLineEdit.text()
        geo_field = self.dlg.comboODKGeoFields.currentText()
        odk_sync_interval = int(self.dlg.odkSyncInterval.value())
        self.fetch_odk_date_range_fields(
            api_url,
            username,
            password,
            form_id_str,
        )
        time.sleep(3)
        # extract date fields
        odk_from_date = self.dlg.ODKDateTimeFrom.date()
        odk_to_date = self.dlg.ODKDateTimeTo.date()

        from_dt = datetime(
            odk_from_date.year(), odk_from_date.month(), odk_from_date.day(), 0, 0, 0
        )  # 12:00 AM
        to_dt = datetime(
            odk_to_date.year(), odk_to_date.month(), odk_to_date.day(), 23, 59, 59
        )

        # Convert datetime to timestamp string
        odk_from_timestamp = (
            from_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        )  # Adjust to match original format
        odk_to_timestamp = to_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        if hasattr(self, "vlayer"):
            if self.vlayer.get("layer"):
                self.vlayer["syncData"] = True

        self.fetch_and_save_odk_data(
            api_url,
            username,
            password,
            form_id_str,
            geo_field,
            odk_from_timestamp,
            odk_to_timestamp,
        )

    def fetch_odk_form_data_clicked(self):
        # Extract parameters from the dialog
        api_url = self.dlg.odk_api_url.text()
        form_id_str = self.dlg.comboODKForms.currentText()
        username = self.dlg.odk_username.text()
        password = self.dlg.odkmLineEdit.text()
        geo_field = self.dlg.comboODKGeoFields.currentText()
        odk_sync_interval = int(self.dlg.odkSyncInterval.value())
        # extract date fields
        odk_from_date = self.dlg.ODKDateTimeFrom.date()
        odk_to_date = self.dlg.ODKDateTimeTo.date()

        from_dt = datetime(
            odk_from_date.year(), odk_from_date.month(), odk_from_date.day(), 0, 0, 0
        )  # 12:00 AM
        to_dt = datetime(
            odk_to_date.year(), odk_to_date.month(), odk_to_date.day(), 23, 59, 59
        )  # 11:59:59 PM

        # Convert datetime to timestamp string
        odk_from_timestamp = (
            from_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        )  # Adjust to match original format
        odk_to_timestamp = to_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        page_size = 1000
        directory = True

        if directory:
            # Create a worker for background data fetching
            # self.odk_worker = FetchODKDataWorker(
            #     self,
            #     api_url,
            #     form_id_str,
            #     username,
            #     password,
            #     geo_field,
            #     page_size,
            #     directory,
            #     self.dlg,
            #     False,
            #     odk_from_timestamp,
            #     odk_to_timestamp
            # )

            # # # Connect signals to handle results in the main thread
            # self.odk_worker.odk_data_fetched.connect(self.on_data_fetched)
            # self.odk_worker.odk_fetch_error.connect(self.on_fetch_error)
            # self.odk_worker.odk_rogress_updated.connect(self.on_progress_update)

            # # Start the thread
            # self.odk_worker.start()
            # if odk_sync_interval > 0:
            #     self.odk_sync_timer.start(odk_sync_interval * 1000)

            self.fetch_and_save_odk_data(
                api_url,
                username,
                password,
                form_id_str,
                geo_field,
                odk_from_timestamp,
                odk_to_timestamp,
            )

            if odk_sync_interval > 0:
                self.odk_sync_timer.start(odk_sync_interval * 1000)

    def is_valid_wkt(self, wkt_string):
        # Define basic geometry types
        valid_geometries = [
            "POINT",
            "LINESTRING",
            "POLYGON",
            "MULTIPOINT",
            "MULTILINESTRING",
            "MULTIPOLYGON",
        ]

        # Extract the geometry type
        match = re.match(r"^\s*(\w+)\s*\((.*)\)\s*$", wkt_string, re.IGNORECASE)
        if not match:
            return False  # Invalid format

        geometry_type, coordinates_part = match.groups()
        geometry_type = geometry_type.upper()

        # Check if geometry type is valid
        if geometry_type not in valid_geometries:
            return False
        else:
            return True

    def wkt_to_geometry_obj(self, wkt_string):
        # Identify the geometry type and coordinates
        wkt = wkt_string.strip()
        geometry_type, coords = wkt.split("(", 1)
        geometry_type = geometry_type.strip().upper()
        coords = coords.strip().rstrip(")").lstrip("(")

        if geometry_type == "POINT":
            # Take only the first two values (X and Y)
            coordinate_values = coords.split()
            coordinates = [float(coordinate_values[0]), float(coordinate_values[1])]
            geometry_obj = {"type": "Point", "coordinates": coordinates}

        elif geometry_type == "LINESTRING" or geometry_type == "GEOTRACE":
            # Extract all numeric values, including negative and decimal points
            coordinate_values = re.findall(r"-?\d+\.?\d*", coords)
            # Group into pairs (X, Y), ignoring the Z component if present
            coordinates = [
                [float(coordinate_values[i]), float(coordinate_values[i + 1])]
                for i in range(
                    0,
                    len(coordinate_values),
                    2 if len(coordinate_values) % 3 != 0 else 3,
                )
            ]
            geometry_obj = {"type": "LineString", "coordinates": coordinates}

        elif geometry_type == "POLYGON":
            rings = coords.split("), (")
            rings = [ring.replace("(", "").replace(")", "").strip() for ring in rings]
            coordinates = [
                [
                    [float(pair.split()[0]), float(pair.split()[1])]
                    for pair in ring.split(",")
                ]
                for ring in rings
            ]
            geometry_obj = {"type": "Polygon", "coordinates": coordinates}
        else:
            raise ValueError(f"Unsupported geometry type: {geometry_type}")

        return geometry_obj

    def get_odk_geo_data(self, datum, geom_field):
        field_keys = datum.keys()
        if geom_field in field_keys:
            # this means that the geo field is not inside a repeat
            # build the corresponding geometry/feature collection
            geom = datum.get(geom_field)
            # determine whether polygon or point
            if geom and self.is_valid_wkt(geom):
                geometry = self.wkt_to_geometry_obj(geom)
                # this means that it is a polygon
                # build the correspoing collection
                feature = {"type": "Feature", "geometry": geometry, "properties": datum}
                return feature
        else:
            # flatten the datum
            repeat_geo_arr = []
            for k in datum.keys():
                field_arr = k.split("/")
                if geom_field in field_arr:
                    repeat_geo_arr.append(k)
            if repeat_geo_arr:
                for f in repeat_geo_arr:
                    nested_geom = datum.get(f)
                    if nested_geom and self.is_valid_wkt(nested_geom):
                        geometry = self.wkt_to_geometry_obj(nested_geom)
                        # this means that it is a polygon
                        # build the correspoing collection
                        feature = {
                            "type": "Feature",
                            "geometry": geometry,
                            "properties": datum,
                        }
                        return feature

    def flatten_odk_json(self, json_obj, parent_key=""):
        """Recursively flattens a nested JSON object into a dictionary with XPath keys."""
        flattened = {}

        def _flatten(obj, key_prefix=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    new_key = f"{key_prefix}/{k}" if key_prefix else k
                    _flatten(v, new_key)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    _flatten(item, f"{key_prefix}[{i}]")
            else:
                flattened[key_prefix] = obj

        _flatten(json_obj)
        return flattened

    def fetch_and_save_odk_data(
        self,
        api_url,
        username,
        password,
        form_id_str,
        geo_field,
        odk_from_date,
        odk_to_date,
    ):
        auth = HTTPBasicAuth(username, password)
        self.dlg.odkOkButton.setEnabled(False)
        params = {"$expand": "*", "$wkt": True}

        if odk_from_date and odk_to_date:
            filter_query = f"__system/submissionDate ge {odk_from_date} and __system/submissionDate le {odk_to_date}"
            params["$filter"] = filter_query

        project_id = self.odk_forms_to_projects_map.get(form_id_str)

        feature_collection = {
            "type": "FeatureCollection",
            "features": [],
        }
        url = f"https://{api_url}/v1/projects/{project_id}/forms/{form_id_str}.svc/Submissions"
        response = self.fetch_with_retries(url, auth, params=params)
        if response.status_code == 200:
            data = response.json()
            data_list = data.get("value")
            if data_list:
                self.dlg.odkProgressBar.setvalue(100)
                for datum in data_list:
                    flat_data = self.flatten_odk_json(datum)
                    feature = self.get_odk_geo_data(flat_data, geo_field)
                    if feature:
                        feature_collection["features"].append(feature)
                if (
                    feature_collection["features"]
                    and len(feature_collection["features"]) > 0
                ):
                    self.load_data_to_qgis(feature_collection, form_id_str, geo_field)

                    self.dlg.odkOkButton.setEnabled(True)
                else:
                    self.iface.messageBar().pushMessage(
                        "Notice",
                        f"The selected geo field doesn't have geo data",
                        level=Qgis.Warning,
                        duration=10,
                    )
                    self.dlg.odkOkButton.setEnabled(True)
            else:
                self.iface.messageBar().pushMessage(
                    "Notice", f"No Data Available", level=Qgis.Warning
                )
        else:
            self.iface.messageBar().pushMessage(
                "Error",
                f"Error fetching data: {response.status_code}",
                level=Qgis.Critical,
            )

    # Slots to handle signals
    def on_data_fetched(self, data):
        self.iface.messageBar().pushMessage(
            "Success", "Data fetched successfully!", level=Qgis.Success
        )
        # Process and display data in QGIS as needed

    def on_fetch_error(self, error_message):
        self.iface.messageBar().pushMessage(
            "Error", f"Error fetching data: {error_message}", level=Qgis.Critical
        )

    def on_progress_update(self, message):
        self.iface.messageBar().pushMessage("Progress", message, level=Qgis.Info)

    def loop_cleanup(self):
        """Ensure the event loop is closed."""
        if self.loop and self.loop.is_running():
            logging.debug("Stopping event loop")
            self.loop.stop()
            self.loop.close()

    def handle_data_fetched(self, data):
        formID = self.dlg.comboOnaForms.currentData()
        geo_field = self.curr_geo_field

        self.dlg.app_logs.appendPlainText("Data Fetch Complete, Building GeoJSON... \n")

        if isinstance(data, dict) or (isinstance(data, list) and len(data) == 0):
            self.dlg.app_logs.appendPlainText(
                "No Data Available For the selected date range"
            )

            if self.ona_sync_timer.isActive():
                self.ona_sync_timer.stop()
                self.dlg.onaOkButton.setEnabled(True)
        else:
            feature_collection = {
                "type": "FeatureCollection",
                "features": [],
            }

            for datum in data:
                self.get_geo_data(datum, geo_field, feature_collection)

            if (
                feature_collection["features"]
                and len(feature_collection["features"]) > 0
            ):
                # self.dlg.onaProgressBar.setValue(100)
                self.dlg.app_logs.appendPlainText("Building GeoJSON Complete. Adding Layer to Map...\n")
                self.load_data_to_qgis(feature_collection, formID, geo_field)
                if not self.ona_sync_timer.isActive():
                    self.dlg.onaOkButton.setEnabled(True)
            else:
                self.dlg.app_logs.appendPlainText(
                    "The selected geo field doesn't have geo data"
                )
                if not self.ona_sync_timer.isActive():
                    self.dlg.onaOkButton.setEnabled(True)

    def handle_fetch_error(self, message):
        self.dlg.app_logs.appendPlainText(f"Error - {message}")
        self.iface.messageBar().pushMessage(
            "Error", f"{message}", level=Qgis.Critical, duration=10
        )

    def handle_status_error(self, msg):
        self.dlg.app_logs.appendPlainText(f"Error - {msg}")
        self.iface.messageBar().pushMessage(
            "Error", f"{msg}", level=Qgis.Critical, duration=10
        )

    def handle_date_and_count_fields(self, data):
        if data:
            self.data_count = data.get("count")
            get_from_date = data.get("from_date")
            get_to_date = data.get("to_date")

            from_dt = datetime.fromisoformat(get_from_date).astimezone(timezone.utc)
            to_dt = datetime.fromisoformat(get_to_date).astimezone(timezone.utc)

            from_dt = from_dt.replace(
                hour=0, minute=0, second=0, microsecond=0
            )  # 12:00 AM
            to_dt = to_dt.replace(hour=23, minute=59, second=59, microsecond=0)

            from_date = QDate(from_dt.year, from_dt.month, from_dt.day)
            to_date = QDate(to_dt.year, to_dt.month, to_dt.day)

            self.dlg.onaDateTimeFrom.setDate(from_date)
            self.dlg.onaDateTimeTo.setDate(to_date)

            # set Date ranges
            # self.dlg.onaDateTimeFrom.setMinimumDate(
            #     from_date
            # )
            # self.dlg.onaDateTimeFrom.setMaximumDate(
            #     to_date
            # )
            # self.dlg.onaDateTimeTo.setMinimumDate(
            #     from_date
            # )
            # self.dlg.onaDateTimeTo.setMaximumDate(
            #     to_date
            # )

            # UI updates
            self.dlg.onaDateTimeFrom.setEnabled(True)
            self.dlg.onaDateTimeTo.setEnabled(True)
            self.dlg.onaDateTimeFrom.repaint()
            self.dlg.onaDateTimeTo.repaint()

    def handle_date_and_count_fields_error(self, message):
        self.dlg.app_logs.appendPlainText(f"Error - {message}")
        self.iface.messageBar().pushMessage(
            "Error", f"{message}", level=Qgis.Critical, duration=10
        )

    def handle_ona_data_fetch_progress(self, data):
        self.dlg.app_logs.appendPlainText(f"data")
        if data:
            if isinstance(data, dict):
                page = data.get("curr_page")
                total_pages = data.get("total_pages")
                progress = (int(page) / int(total_pages)) * 100 if int(total_pages) > 1 else 100
                self.dlg.onaProgressBar.setValue(math.ceil(progress))

    def ona_fetch_data_sync_enabled(self):
        # disable OK button during sync
        self.dlg.onaOkButton.setEnabled(False)
        api_url = self.dlg.onadata_api_url.text()
        formID = self.dlg.comboOnaForms.currentData()
        username = self.dlg.onadata_username.text()
        password = self.dlg.onaMLineEdit.text()
        page_size = int(self.dlg.onaPageSize.value())

        # data count url
        auth = HTTPBasicAuth(username, password)
        url = f"https://{api_url}/api/v1/data/{formID}.json"
        params = dict()

        ona_from_date = self.dlg.onaDateTimeFrom.date()
        ona_to_date = self.dlg.onaDateTimeTo.date()

        from_dt = datetime(
            ona_from_date.year(), ona_from_date.month(), ona_from_date.day(), 0, 0, 0
        )  # 12:00 AM
        to_dt = datetime(
            ona_to_date.year(), ona_to_date.month(), ona_to_date.day(), 23, 59, 59
        )

        ona_from_timestamp = from_dt.strftime("%Y-%m-%dT%H:%M:%S")
        ona_to_timestamp = to_dt.strftime("%Y-%m-%dT%H:%M:%S")

        if ona_from_timestamp and ona_to_timestamp:
            params["query"] = json.dumps(
                {
                    "_submission_time": {
                        "$gte": ona_from_timestamp,
                        "$lte": ona_to_timestamp,
                    }
                }
            )

        if hasattr(self, "vlayer"):
            if self.vlayer.get("layer"):
                self.vlayer["syncData"] = True

        self.ona_worker = OnaRequestThread(
            url,
            auth,
            params,
            headers=None,
            total_records=self.data_count,
            records_per_page=page_size,
            formID=formID,
        )

        # Connect signals to the handler methods
        self.ona_worker.data_fetched.connect(self.handle_data_fetched)
        self.ona_worker.progress_updated.connect(self.handle_ona_data_fetch_progress)
        self.ona_worker.count_and_date_fields_fetched.connect(
            self.handle_date_and_count_fields
        )
        self.ona_worker.count_and_date_fields_error_occurred.connect(
            self.handle_date_and_count_fields_error
        )
        self.ona_worker.error_occurred.connect(self.handle_fetch_error)
        self.ona_worker.start()

    def fetch_button_clicked(self):
        """Handles the Fetch button click event."""
        # Extract parameters from the dialog

        # disable button
        self.dlg.onaOkButton.setEnabled(False)
        self.dlg.onaProgressBar.setValue(0)
        self.dlg.onaOkButton.repaint()

        api_url = self.dlg.onadata_api_url.text()
        formID = self.dlg.comboOnaForms.currentData()
        username = self.dlg.onadata_username.text()
        password = self.dlg.onaMLineEdit.text()
        geo_field = self.curr_geo_field
        ona_sync_interval = int(self.dlg.onaSyncInterval.value())
        page_size = int(self.dlg.onaPageSize.value())
        directory = True

        # data count url
        auth = HTTPBasicAuth(username, password)
        url = f"https://{api_url}/api/v1/data/{formID}.json"
        params = dict()

        ona_from_date = self.dlg.onaDateTimeFrom.date()
        ona_to_date = self.dlg.onaDateTimeTo.date()

        from_dt = datetime(
            ona_from_date.year(), ona_from_date.month(), ona_from_date.day(), 0, 0, 0
        )  # 12:00 AM
        to_dt = datetime(
            ona_to_date.year(), ona_to_date.month(), ona_to_date.day(), 23, 59, 59
        )

        ona_from_timestamp = from_dt.strftime("%Y-%m-%dT%H:%M:%S")
        ona_to_timestamp = to_dt.strftime("%Y-%m-%dT%H:%M:%S")

        if ona_from_timestamp and ona_to_timestamp:
            params["query"] = json.dumps(
                {
                    "_submission_time": {
                        "$gte": ona_from_timestamp,
                        "$lte": ona_to_timestamp,
                    }
                }
            )

        self.ona_worker = OnaRequestThread(
            url,
            auth,
            params,
            headers=None,
            total_records=self.data_count,
            records_per_page=page_size,
            formID=formID,
        )

        # Connect signals to the handler methods
        self.ona_worker.data_fetched.connect(self.handle_data_fetched)
        self.ona_worker.progress_updated.connect(
            self.handle_ona_data_fetch_progress
        )
        self.ona_worker.count_and_date_fields_fetched.connect(
            self.handle_date_and_count_fields
        )
        self.ona_worker.count_and_date_fields_error_occurred.connect(
            self.handle_date_and_count_fields_error
        )
        self.ona_worker.error_occurred.connect(self.handle_fetch_error)
        self.ona_worker.start()

        if ona_sync_interval > 0:
            self.ona_sync_timer.start(ona_sync_interval * 1000)

    def fetch_with_retries(
        self,
        url,
        auth=None,
        params=None,
        headers=None,
        max_retries=5,
        backoff_factor=0.2,
    ):
        with requests.Session() as session:  # Use a session
            if auth:
                session.auth = auth  # Set Basic Auth for the session

            # set headers
            if headers:
                session.headers.update(headers)

            for attempt in range(max_retries):
                try:
                    if params:
                        response = session.get(url, params=params, stream=True)
                    else:
                        response = session.get(url, stream=True)

                    if response.status_code == 404:
                        return response  # Return if the resource is not found
                    # response.raise_for_status()  # Raise HTTPError for bad responses (4xx and 5xx)
                    return response  # Successful request

                except (
                    requests.RequestException,
                    requests.ConnectionError,
                    requests.ConnectTimeout,
                    requests.ReadTimeout,
                ) as e:
                    print(f"Attempt {attempt + 1} failed: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(backoff_factor * (2**attempt))  # Exponential backoff
                    else:
                        self.dlg.app_logs.appendPlainText(f"Failed to fetch data")
                        self.iface.messageBar().pushMessage(
                            "Error", f"{e}", level=Qgis.Critical, duration=10
                        )
                        self.dlg.accept()

    def retrieve_all_geofields(self, fields):
        for field in fields:
            if field.get("children"):
                self.retrieve_all_geofields(field.get("children"))
            else:
                if field.get("type") in self.geo_types:
                    cleaned_geo_field_name = field.get("name", "").strip()
                    cleaned_geo_field_label = ""
                    if isinstance(field.get("label", ""), dict):
                        labels = field.get("label", "")
                        cleaned_geo_field_label = (
                            labels.get("English (en)", "").strip()
                            or labels.get("English", "").strip()
                        )
                    elif isinstance(field.get("label", ""), str):
                        cleaned_geo_field_label = field.get("label", "").strip()
                    self.geo_fields.add(cleaned_geo_field_name)
                    if not self.geo_fields_dict.get(cleaned_geo_field_name):
                        self.geo_fields_dict[cleaned_geo_field_name] = (
                            cleaned_geo_field_label
                        )
        return self.geo_fields

    def fetch_time_fields(self, api_url, username, password, formID):
        auth = HTTPBasicAuth(username, password=password)
        url = f"https://{api_url}/api/v1/forms/{formID}.json"
        self.dlg.app_logs.appendPlainText(f"Fetching Form Metadata... \n")
        resp = self.fetch_with_retries(url, auth)
        if resp.status_code == 200:
            self.dlg.app_logs.appendPlainText(f"Done")
            data = resp.json()
            get_from_date = data.get("date_created")
            get_to_date = data.get("last_submission_time") or data.get("date_modified")

            from_dt = datetime.fromisoformat(get_from_date).astimezone(timezone.utc)
            to_dt = datetime.fromisoformat(get_to_date).astimezone(timezone.utc)

            from_dt = from_dt.replace(
                hour=0, minute=0, second=0, microsecond=0
            )  # 12:00 AM
            to_dt = to_dt.replace(hour=23, minute=59, second=59, microsecond=0)

            from_date = QDate(from_dt.year, from_dt.month, from_dt.day)
            to_date = QDate(to_dt.year, to_dt.month, to_dt.day)

            self.dlg.onaDateTimeFrom.setDate(from_date)
            self.dlg.onaDateTimeTo.setDate(to_date)
            # self.dlg.mDateTimeEditFrom.setDateTimeRange(
            #     datetime.fromisoformat(self.from_date), datetime.fromisoformat(self.to_date))
            # self.dlg.mDateTimeEditTo.setDateTimeRange(
            #     datetime.fromisoformat(self.from_date), datetime.fromisoformat(self.to_date))
            self.dlg.onaDateTimeFrom.setEnabled(True)
            self.dlg.onaDateTimeTo.setEnabled(True)
            self.dlg.onaDateTimeFrom.repaint()
            self.dlg.onaDateTimeTo.repaint()

    def fetchDataCount(self, api_url, username, password, formID):
        auth = HTTPBasicAuth(username, password=password)
        url = f"https://{api_url}/api/v1/forms/{formID}.json"
        self.dlg.app_logs.appendPlainText(f"Fetching Submissions Count...")
        resp = self.fetch_with_retries(url, auth)
        if resp.status_code == 200:
            data = resp.json()
            count = data.get("num_of_submissions")
            self.dlg.app_logs.appendPlainText(
                f"Done. Number Of Submissions - {count} \n"
            )
            return count

    def fetchGeoFields(self, api_url, username, password, formID):
        auth = HTTPBasicAuth(username, password)
        url = f"https://{api_url}/api/v1/forms/{formID}/versions"
        self.dlg.app_logs.appendPlainText(f"Fetching Form Versions...")
        resp = self.fetch_with_retries(url, auth)
        if resp.status_code == 200:
            versions = resp.json()
            self.dlg.app_logs.appendPlainText(
                f"Done. Number of form versions - {len(versions)}"
            )
            if versions:
                for v in versions:
                    version_str = v.get("version")
                    version_url = f"https://{api_url}/api/v1/forms/{formID}/versions/{version_str}"
                    self.dlg.app_logs.appendPlainText(
                        f"Fetching Form Schema for {version_str}..."
                    )
                    res = self.fetch_with_retries(version_url, auth)
                    if res.status_code == 200:
                        self.dlg.app_logs.appendPlainText(f"Done \n")
                        the_v = json.dumps(res.json())
                        fields = json.loads(the_v).get("children")
                        self.geo_fields = self.retrieve_all_geofields(fields)
                if self.geo_fields:
                    for i, gf in enumerate(self.geo_fields):
                        cleaned_gf = gf.strip()
                        self.dlg.comboOnaGeoFields.addItem(cleaned_gf)
                        geo_label = self.geo_fields_dict[cleaned_gf]
                        if geo_label:
                            self.dlg.comboOnaGeoFields.setItemText(
                                i, f"{cleaned_gf} - ({geo_label})"
                            )
                    self.dlg.onaOkButton.setEnabled(True)

                self.dlg.app_logs.appendPlainText(
                    f"Number of Geo Fields Found: {len(self.geo_fields)} \n"
                )
                self.dlg.comboOnaGeoFields.setEnabled(True)
        else:
            self.iface.messageBar().pushMessage(
                "Notice",
                f"Failed to fetch form versions: Status code {resp.status_code}",
                level=Qgis.Warning,
            )
        return

    def fetchFormFields(self, api_url, username, password, formID):
        auth = HTTPBasicAuth(username, password=password)
        url = f"https://{api_url}/api/v1/forms/{formID}/form.json"
        # clear any initial logs
        self.dlg.app_logs.clear()
        self.dlg.app_logs.appendPlainText(f"Fetching Form Schema...")
        resp = self.fetch_with_retries(url)
        if resp.status_code == 200:
            self.dlg.app_logs.appendPlainText(f"Done \n")
            data = resp.json()
            # get columns
            children = data.get("children")
            field_props = ",".join(
                map(
                    str,
                    [
                        c.get("name")
                        for c in children
                        if c.get("name") and c.get("type") not in self.excluded_types
                    ],
                )
            )
            return field_props

    def dataFetch(
        self, base_url, username, password, form_id, geo_field, fields, page, page_size
    ):
        auth = HTTPBasicAuth(username, password=password)
        url = f"https://{base_url}/api/v1/data/{form_id}.json"
        params = {"page": page, "page_size": page_size}
        if self.from_date and self.to_date:
            params["query"] = json.dumps(
                {"_submission_time": {"$gte": self.from_date, "$lte": self.to_date}}
            )
        self.dlg.app_logs.appendPlainText(f"Fetching Page {page} of geojson data...")
        response = self.fetch_with_retries(url, auth, params=params)
        if response.status_code == 200:
            # Calculate progress
            self.dlg.app_logs.appendPlainText(f"Done \n")
            total_pages = math.ceil((int(self.data_count) / int(page_size)))
            progress = (page / total_pages) * 100 if total_pages > 1 else 100
            # self.dlg.onaProgressBar.setValue(math.ceil(progress))
        elif response.status_code in [401, 500, 502, 503]:
            self.dlg.app_logs.appendPlainText(
                f"Fetch failed!!! Status Code - {response.status_code}"
            )
        return response

    def flatten_dict(self, data, parent_key="", sep="/"):
        flattened = {}

        for key, value in data.items():
            new_key = f"{parent_key}{sep}{key}" if parent_key else key

            if isinstance(value, dict):
                # Recursively flatten the dictionary
                flattened.update(self.flatten_dict(value, new_key, sep=sep))
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        if i == 0:
                            # Don't append [0] for the first item
                            flattened.update(self.flatten_dict(item, new_key, sep=sep))
                        else:
                            flattened.update(
                                self.flatten_dict(item, f"{new_key}[{i}]", sep=sep)
                            )
                    else:
                        if i == 0:
                            flattened[new_key] = item
                        else:
                            flattened[f"{new_key}[{i}]"] = item
            else:
                flattened[new_key] = value

        return flattened

    def build_feature_collection(self, filtered_datum, geom, feature_collection):
        # determine whether polygon or point
        if geom and geom.__contains__(";") and len(geom.split(";")) > 1:
            coords_arr = geom.split(";")
            # this means that it is a polygon
            # build the correspoing collection
            coodinates = [
                [
                    float(x.strip().split(" ")[1]),
                    float(x.strip().split(" ")[0]),
                ]
                for x in coords_arr
            ]
            poly_feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [coodinates],
                },
                "properties": filtered_datum,
            }
            feature_collection["features"].append(poly_feature)
        elif geom and not geom.__contains__(";"):
            # this means its a feature point
            point_arr = geom.strip().split(" ")
            point_feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        float(point_arr[1]),
                        float(point_arr[0]),
                    ],
                },
                "properties": filtered_datum,
            }
            feature_collection["features"].append(point_feature)

    def get_geo_data(self, datum, geom_field, feature_collection):
        field_keys = datum.keys()
        filtered_datum = {
            key: value
            for key, value in datum.items()
            if not isinstance(value, list)
            and not isinstance(value, dict)
            and key not in self.geo_fields
        }
        if geom_field in field_keys:
            # this means that the geo field is not inside a repeat
            # build the corresponding geometry/feature collection
            geom = datum.get(geom_field, "")
            # build feature collection
            self.build_feature_collection(filtered_datum, geom, feature_collection)
        else:
            # flatten the datum
            repeat_geo_arr = []
            flattened_data = self.flatten_dict(datum)
            for k in flattened_data.keys():
                field_arr = k.split("/")
                if geom_field in field_arr:
                    repeat_geo_arr.append(k)
            if repeat_geo_arr:
                for f in repeat_geo_arr:
                    nested_geom = flattened_data.get(f, "")
                    self.build_feature_collection(
                        filtered_datum, nested_geom, feature_collection
                    )

    def getTheGeoJson(
        self,
        api_url,
        username,
        password,
        formID,
        geo_field,
        page_size,
        page,
        response=None,
    ):
        self.dlg.onaOkButton.setEnabled(False)
        if page == 1 and not response:
            self.data_count = self.fetchDataCount(api_url, username, password, formID)
            response = self.dataFetch(
                api_url,
                username,
                password,
                formID,
                geo_field,
                self.fields,
                page,
                page_size,
            )
        if response and response.status_code == 200:
            data = response.json()
            if len(data) == 0:
                self.dlg.app_logs.appendPlainText(
                    "No Data Available For the selected date range"
                )
                self.dlg.onaProgressBar.setValue(0)
                self.dlg.onaOkButton.setEnabled(True)
                # self.dlg.progress_bar.update()
                return

            # features_list = data.get("features")
            # self.features.extend(features_list)
            self.json_data.extend(data)
            page = page + 1
            response = self.dataFetch(
                api_url,
                username,
                password,
                formID,
                geo_field,
                self.fields,
                page,
                page_size,
            )
            self.getTheGeoJson(
                api_url,
                username,
                password,
                formID,
                geo_field,
                page_size,
                page,
                response,
            )
        else:
            if self.json_data:
                feature_collection = {
                    "type": "FeatureCollection",
                    "features": [],
                }
                for datum in self.json_data:
                    self.get_geo_data(datum, geo_field, feature_collection)

                if (
                    feature_collection["features"]
                    and len(feature_collection["features"]) > 0
                ):
                    self.dlg.onaProgressBar.setValue(100)
                    self.load_data_to_qgis(
                        feature_collection,
                        api_url,
                        username,
                        password,
                        formID,
                        page_size,
                        geo_field,
                    )
                    self.dlg.onaOkButton.setEnabled(True)
                else:
                    self.dlg.app_logs.appendPlainText(
                        "The selected geo field doesn't have geo data"
                    )
                    if self.worker:
                        self.worker.stop()
                    self.dlg.onaOkButton.setEnabled(True)
            else:
                self.dlg.app_logs.appendPlainText(
                    "No Data Available For the selected date range"
                )
                return

        return self.json_data
        # with open(f"{formID}_{geo_field}", "w") as outfile:
        #     print("Writting geo data to json file...")
        #     json.dump(feature_collection, outfile)

    def fetch_and_save_data(
        self, api_url, formID, username, password, geo_field, page_size, directory
    ):
        self.getTheGeoJson(
            api_url,
            username,
            password,
            formID,
            geo_field,
            page_size,
            page=1,
            response=None,
        )

    def validate_geojson(self, geojson_data):
        """Validate if the fetched data is a valid GeoJSON."""
        if not isinstance(geojson_data, dict):
            return False

        if geojson_data.get("type") != "FeatureCollection":
            return False

        if not isinstance(geojson_data.get("features"), list):
            return False

        if len(geojson_data.get("features")) == 0:
            return False

        return True

    def geojson_to_wkt(self, geometry):
        geom_type = geometry["type"]
        coords = geometry["coordinates"]

        if geom_type == "Point":
            return f"POINT ({coords[0]} {coords[1]})"

        elif geom_type == "LineString":
            coord_str = ", ".join([f"{x} {y}" for x, y in coords])
            return f"LINESTRING ({coord_str})"

        elif geom_type == "Polygon":
            rings = []
            for ring in coords:
                ring_str = ", ".join([f"{x} {y}" for x, y in ring])
                rings.append(f"({ring_str})")
            return f"POLYGON ({', '.join(rings)})"

        elif geom_type == "MultiPolygon":
            polygons = []
            for polygon in coords:
                rings = []
                for ring in polygon:
                    ring_str = ", ".join([f"{x} {y}" for x, y in ring])
                    rings.append(f"({ring_str})")
                polygons.append(f"({', '.join(rings)})")
            return f"MULTIPOLYGON ({', '.join(polygons)})"
        else:
            raise ValueError(f"Unsupported geometry type: {geom_type}")

    def load_data_to_qgis(self, geojson_data, formID, geo_field):
        """Load the fetched GeoJSON data into QGIS as a layer."""
        # validate fetched GeoJSON
        if not self.validate_geojson(geojson_data):
            self.iface.messageBar().pushMessage("Invalid GeoJSON data.")
            return  # Stop if the GeoJSON is invalid

        else:
            layer_name = f"{formID}_{geo_field}"
            features = geojson_data["features"]
            chunk_size = 10000  # make this configurable
            # Define the layer with the same geometry type and fields as the GeoJSON data
            feature_type = features[0].get("geometry").get("type")
            vlayer = QgsVectorLayer(
                f"{feature_type}?crs=EPSG:4326", f"{layer_name}", "memory"
            )
            pr = vlayer.dataProvider()

            if not vlayer.isValid():
                self.iface.messageBar().pushMessage("Failed to load Layer")
                return
            else:
                if (
                    self.vlayer
                    and self.vlayer.get("layer")
                    and self.vlayer.get("syncData")
                ):
                    self.vlayer = {"syncData": True, "layer": vlayer}
                    self.update_layer_data(f"{layer_name}", geojson_data, vlayer)
                elif not self.vlayer.get("layer") or not self.vlayer.get("syncData"):
                    # Start editing to add fields and features
                    vlayer.startEditing()
                    prop_keys = [
                        QgsField(f"{prop}", QVariant.String)
                        for prop in features[0].get("properties").keys()
                    ]
                    pr.addAttributes(prop_keys)  # Add fields as needed
                    vlayer.updateFields()

                    # Add features to the layer
                    for feature in features:
                        new_feature = QgsFeature(vlayer.fields())
                        # Convert GeoJSON geometry to WKT
                        geometry_wkt = self.geojson_to_wkt(feature["geometry"])
                        geometry = QgsGeometry.fromWkt(geometry_wkt)
                        if geometry:
                            new_feature.setGeometry(geometry)
                        new_feature.setAttributes(
                            list(feature.get("properties").values())
                        )  # Adjust based on properties
                        pr.addFeatures([new_feature])

                    # Commit changes and add to project
                    vlayer.commitChanges()

                    QgsProject.instance().addMapLayer(vlayer)
                    canvas = self.iface.mapCanvas()
                    curr_layer = QgsProject.instance().mapLayersByName(f"{layer_name}")[
                        0
                    ]

                    # Set the extent of the canvas to the basemap layer's extent
                    canvas.setExtent(curr_layer.extent())

                    canvas.refresh()

                    self.dlg.app_logs.appendPlainText(
                        f"Layer {layer_name} Added Successfully!"
                    )
                    self.vlayer = {"syncData": False, "layer": vlayer}

        # Close and reset the dialog after layer is successfully added
        # if int(self.dlg.mQgsDoubleSpinBox.value()):
        #     if self.vlayer.get("layer"):
        #         self.vlayer["syncData"] = True
        #     self.fetch_data_async(
        #         api_url,
        #         formID,
        #         username,
        #         password,
        #         self.curr_geo_field,
        #         page_size,
        #         self.directory,
        #     )

        #     self.dlg.progress_bar.setValue(0)
        # else:
        #     pass
        # self.reset_inputs()  # Reset input fields
        # self.dlg.close()  # Close the dialog

    def update_layer_data(self, layer_name, geojson_data, vlayer):
        """Fetch new data and update the existing layer in QGIS."""
        vlayer = self.iface.activeLayer()

        vlayer.startEditing()

        # Collect all unique property keys from the new data
        all_property_keys = set()
        for feature_data in geojson_data["features"]:
            all_property_keys.update(feature_data.get("properties", {}).keys())

        # Ensure layer fields include all property keys
        layer_fields = [field.name() for field in vlayer.fields()]
        for key in all_property_keys:
            if key not in layer_fields:
                # Add missing fields dynamically
                vlayer.addAttribute(
                    QgsField(key, QVariant.String)
                )  # Adjust type if needed
                layer_fields.append(key)

        vlayer.updateFields()  # Refresh the field structure

        # Delete existing features
        vlayer.deleteFeatures([feature.id() for feature in vlayer.getFeatures()])

        # Load new features
        for feature_data in geojson_data["features"]:
            new_feature = QgsFeature(vlayer.fields())

            # Set geometry
            geometry_wkt = self.geojson_to_wkt(feature_data["geometry"])
            geometry = QgsGeometry.fromWkt(geometry_wkt)
            if geometry:
                new_feature.setGeometry(geometry)

            # Align attributes with updated fields
            properties = feature_data.get("properties", {})
            attributes = [
                properties.get(field_name, None) for field_name in layer_fields
            ]
            new_feature.setAttributes(attributes)

            vlayer.addFeature(new_feature)

        # Commit changes and refresh the layer
        vlayer.commitChanges()
        vlayer.triggerRepaint()
        self.dlg.app_logs.appendPlainText(f"Layer {layer_name} Updated Successfully!")
    
    # stop workers if they are running
    def stop_workers(self):
        if hasattr(self, "ona_worker") and self.ona_worker.isRunning():
            self.ona_worker.quit()

        if hasattr(self, "fetch_ona_forms_worker") and self.fetch_ona_forms_worker.isRunning():
            self.fetch_ona_forms_worker.quit()

        if hasattr(self, "fetch_ona_geo_fields_worker") and self.fetch_ona_geo_fields_worker.isRunning():
            self.fetch_ona_geo_fields_worker.quit()

    def reset_inputs(self):
        """Reset all input fields in the dialog."""
        # self.dlg.api_url.setText("")
        self.features = []
        self.new_features = []
        self.fields = None
        # self.dlg.form_id.clear()
        self.dlg.app_logs.clear()
        self.dlg.onaProgressBar.setValue(0)
        if self.ona_sync_timer.isActive():
            self.ona_sync_timer.stop()

        self.stop_workers()

        self.dlg.onaOkButton.setEnabled(True)
        self.dlg.btnFetchOnaForms.setEnabled(True)

        self.dlg.comboOnaForms.setEnabled(True)
