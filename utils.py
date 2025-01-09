import re
from PyQt5.QtCore import *

class FetchODKDataWorker(QThread):
    """Worker thread for fetching data in the background."""

    odk_data_fetched = pyqtSignal(QObject)      # Signal emitted when data is successfully fetched
    odk_fetch_error = pyqtSignal(str)          # Signal emitted when an error occurs
    odk_rogress_updated = pyqtSignal(str)     # Optional: for progress reporting

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
        interrupted
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
        self.is_interrupted = interrupted # Flag for stopping the worker

    def run(self):
        """Main loop that fetches data in the background."""
        try:
            while not self.is_interrupted:
                # Call the plugin method to fetch and save data
                result = self.plugin.fetch_and_save_odk_data(
                    self.api_url,
                    self.username,
                    self.password,
                    self.form_id_str,
                    self.geo_field,
                )
                
                # Emit signal with fetched data or result (adjust as needed)
                self.odk_data_fetched.emit(result)
                
                # Optional: Report progress to the UI
                # self.progress_updated.emit("Data fetched successfully.")

                # Check for the cancellation flag periodically (or at logical points)
                if self.is_interrupted:
                    self.progress_updated.emit("Fetch operation cancelled.")
                    break
                # Stop the loop if no more data or based on other conditions
                break  # Remove this if you want to continuously fetch data
                
        except Exception as e:
            # Emit an error signal to notify the main thread
            self.odk_fetch_error.emit(str(e))

    def stop(self):
        self.is_interrupted = True

class ODKDataHandlers:
    def __init__(self):
        pass

    def is_valid_wkt(self, wkt_string):
        valid_geometries = ["POINT", "LINESTRING", "POLYGON", "MULTIPOINT", "MULTILINESTRING", "MULTIPOLYGON"]
        match = re.match(r'^\s*(\w+)\s*\((.*)\)\s*$', wkt_string, re.IGNORECASE)
        if not match:
            return False  # Invalid format
        
        geometry_type, _ = match.groups()
        return geometry_type.upper() in valid_geometries

    def wkt_to_geometry_obj(self, wkt_string):
        wkt = wkt_string.strip()
        geometry_type, coords = wkt.split('(', 1)
        geometry_type = geometry_type.strip().upper()
        coords = coords.strip().rstrip(')').lstrip('(')

        if geometry_type == "POINT":
            coordinates = [float(coord) for coord in coords.split()]
            geometry_obj =  {"type": "Point", "coordinates": coordinates}

        elif geometry_type == "LINESTRING":
            # Extract all numeric values, including negative and decimal points
            coordinate_values = re.findall(r'-?\d+\.?\d*', coords)
            # Group into triplets (X, Y, Z) for 3D coordinates
            coordinates = [
                [float(coordinate_values[i]), float(coordinate_values[i + 1]), float(coordinate_values[i + 2])]
                for i in range(0, len(coordinate_values), 3)
            ]
            geometry_obj =  {"type": "LineString", "coordinates": coordinates}

        elif geometry_type == "POLYGON":
            # Split by outer ring boundaries, removing leading/trailing spaces
            rings = coords.split('), (')
            rings = [ring.replace('(', '').replace(')', '').strip() for ring in rings]
            coordinates = [
                [[float(coord) for coord in pair.strip().split()] for pair in ring.split(',')]
                for ring in rings
            ]
            geometry_obj = {"type": "Polygon", "coordinates": coordinates}

        # Add handling for other geometry types (MULTIPOINT, etc.) if needed
        else:
            raise ValueError(f"Unsupported geometry type: {geometry_type}")
        
        return geometry_obj

    def flatten_odk_json(self, json_obj, parent_key=''):
        """Recursively flattens a nested JSON object into a dictionary with XPath keys."""
        flattened = {}

        def _flatten(obj, key_prefix=''):
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
                feature = {
                    "type": "Feature",
                    "geometry": geometry,
                    "properties": datum
                }
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
                    nested_geom = datum.get(f, "")
                    if nested_geom and self.is_valid_wkt(nested_geom):
                        geometry = self.wkt_to_geometry_obj(nested_geom)
                        # this means that it is a polygon
                        # build the correspoing collection
                        feature = {
                            "type": "Feature",
                            "geometry": geometry,
                            "properties": datum
                        }
                        return feature
