import requests
import time
import json
import typing
import xml.etree.ElementTree as ET

from PyQt5 import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

geo_types = ["geopoint", "geoshape", "geotrace"]

def retrieve_all_geofields(fields, geo_fields_set, geo_fields_dict):
    for field in fields:
        if field.get("children"):
            retrieve_all_geofields(field.get("children"), geo_fields_set, geo_fields_dict)
        else:
            if field.get("type") in geo_types:
                cleaned_geo_field_name = field.get("name", "").strip()
                cleaned_geo_field_label = ""
                if isinstance(field.get("label", ""), dict):
                    labels = field.get("label", "")
                    cleaned_geo_field_label = labels.get("English (en)", "").strip() or labels.get("English", "").strip()
                elif isinstance(field.get("label", ""), str):
                    cleaned_geo_field_label = field.get("label", "").strip()
                geo_fields_set.add(cleaned_geo_field_name)
                if not geo_fields_dict.get(cleaned_geo_field_name):
                    geo_fields_dict[cleaned_geo_field_name] = cleaned_geo_field_label

def fetch_data(url, auth=None, params=None, headers=None, max_retries=5, backoff_factor=0.2, callback=None):
    """Fetches data with retries and backoff logic."""
    with requests.Session() as session:  # Use a session
        if auth:
            session.auth = auth # Set Basic Auth for the session
        
        # set headers
        if headers:
            session.headers.update(headers)

        for attempt in range(max_retries):
            try:
                if params:
                    response = session.get(url, params=params, stream=True, timeout=60)
                else:
                    response = session.get(url, stream=True, timeout=60)
                return response
            except (
                requests.RequestException,
                requests.ConnectionError,
                requests.ConnectTimeout,
                requests.ReadTimeout) as e:
                print(f"Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(backoff_factor * (2 ** attempt))  # Exponential backoff
                else:
                    if callback:
                        callback.emit(str(e))
                    else:
                        raise

class OnaRequestThread(QThread):
    data_fetched = pyqtSignal(object)  # Signal to emit the response
    progress_updated = pyqtSignal(object)
    error_occurred = pyqtSignal(object)  # Signal to emit errors
    no_data = pyqtSignal(object)

    count_and_date_fields_fetched = pyqtSignal(object)
    count_and_date_fields_error_occurred = pyqtSignal(str)

    def __init__(self, url, auth=None, params=None, headers=None, total_records=None, records_per_page=None, formID=None):
        super().__init__()
        self.url = url
        self.auth = auth
        self.params = params
        self.headers = headers
        self.max_retries = 5
        self.backoff_factor = 0.2
        self.total_records = total_records
        self.records_per_page = records_per_page
        self.formID = formID

    def fetch_form_details(self):
        domain = self.url.split("/")[2]
        if self.formID:
            form_id = self.formID
            url = f"https://{domain}/api/v1/forms/{form_id}.json"
            resp = fetch_data(url, self.auth, callback=self.error_occurred)
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    data_count = data.get("num_of_submissions")
                    from_date = data.get("date_created")
                    to_date = data.get("last_submission_time") or data.get("date_modified")
                    data_dict = {
                        "count": data_count,
                        "from_date": from_date,
                        "to_date": to_date
                    }
                    self.count_and_date_fields_fetched.emit(data_dict)
                    return data_dict
            else:
                self.count_and_date_fields_error_occurred.emit("No Data Found")
        return

    def run(self):
        combined_results = []
        try:
            # fetch data count and date fields
            data_dict = self.fetch_form_details()
            total_records = None

            if data_dict:
                total_records = data_dict.get("count")

            if total_records and self.records_per_page:  # Handle paginated requests
                total_pages = (total_records + self.records_per_page - 1) // self.records_per_page
                for page in range(1, total_pages + 1):
                    self.progress_updated.emit({
                        "curr_page": page,
                        "total_pages": total_pages
                    })
                    self.params.update({"page": page, "page_size": self.records_per_page})
                    res = fetch_data(self.url, self.auth, self.params, callback=self.error_occurred)
                    if res.status_code == 200:
                        data = res.json()
                        if data:
                            combined_results.extend(data)
                        else:
                            self.no_data.emit("No Data Available for selected Form")

                if combined_results:
                    self.data_fetched.emit(combined_results)
                else:
                    self.no_data.emit("No Data Available for selected Form")
            else:  # Handle unpaginated requests
                self.progress_updated.emit("Fetching unpaginated data...")
                res = fetch_data(self.url, self.auth, self.params, callback=self.error_occurred)
                data = res.json()
                if data:
                    self.data_fetched.emit(data)
                else:
                    self.no_data.emit("No Data Available for selected Form")

        except Exception as e:
            self.error_occurred.emit(str(e))
    
    def fetch_data(self):
        """Fetches data with retries and backoff logic."""
        with requests.Session() as session:  # Use a session
            if self.auth:
                session.auth = self.auth # Set Basic Auth for the session

            # set headers
            if self.headers:
                session.headers.update(self.headers)

            for attempt in range(self.max_retries):
                try:
                    if self.params:
                        response = session.get(self.url, params=self.params, stream=True, timeout=60)
                    else:
                        response = session.get(self.url, stream=True, timeout=60)
                    return response
                except (
                    requests.RequestException,
                    requests.ConnectionError,
                    requests.ConnectTimeout,
                    requests.ReadTimeout) as e:
                    print(f"Attempt {attempt + 1} failed: {e}")
                    if attempt < self.max_retries - 1:
                        time.sleep(self.backoff_factor * (2 ** attempt))  # Exponential backoff
                    else:
                        self.error_occurred.emit(str(e))


class FetchOnaFormsThread(QThread):
    data_fetched = pyqtSignal(object)  # Signal to emit the response
    progress_updated = pyqtSignal(str)
    error_occurred = pyqtSignal(str)  # Signal to emit errors
    status_error = pyqtSignal(str)
    no_data = pyqtSignal(str)

    def __init__(self, url, auth=None, params=None, headers=None):
        super().__init__()
        self.url = url
        self.auth = auth
        self.params = params
        self.headers = headers
        self.max_retries = 5
        self.backoff_factor = 0.2
        self.hasData = True

    def run(self):
        combined_results = []

        # fetch user profile
        domain = self.url.split("/")[2]
        username = self.url.split("/")[3]

        user_url = f"https://{domain}/api/v1/user"

        user_res = fetch_data(user_url, self.auth, callback=self.error_occurred)

        api_token = None

        if user_res.status_code == 200:
            user_dets = user_res.json()
            api_token = user_dets.get("api_token")
        
        if api_token:
            headers = {
                "Authorization": f"Token {api_token}"
            }
            response = fetch_data(
                self.url, None, None, headers=headers, max_retries=5, backoff_factor=0.2, callback=self.error_occurred)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
    
                if root:
                    ns = {"xforms": "http://openrosa.org/xforms/xformsList"}
                    for xform in root.findall("xforms:xform", ns):
                        title = xform.find("xforms:name", ns).text
                        form_id = xform.find("xforms:downloadUrl", ns).text.split("/")[-2]
                        combined_results.append({
                            "title": title,
                            "formid": form_id
                        })
                    self.data_fetched.emit(combined_results)

                else:
                    self.hasData = False
                    self.no_data.emit("No Data Found")
            else:
                self.hasData = False
                self.status_error.emit(str(response.status_code))


class FetchOnaGeoFieldsThread(QThread):
    data_fetched = pyqtSignal(object)  # Signal to emit the response
    progress_updated = pyqtSignal(object)
    error_occurred = pyqtSignal(str)  # Signal to emit errors
    status_error = pyqtSignal(str)
    no_data = pyqtSignal(str)

    count_and_date_fields_fetched = pyqtSignal(object)
    count_and_date_fields_error_occurred = pyqtSignal(str)

    def __init__(self, url, auth=None, params=None, headers=None, formID=None):
        super().__init__()
        self.url = url
        self.auth = auth
        self.params = params
        self.headers = headers
        self.max_retries = 5
        self.backoff_factor = 0.2
        self.hasData = True
        self.formID = formID
    
    def fetch_form_details(self):
        domain = self.url.split("/")[2]
        if self.formID:
            form_id = self.formID
            url = f"https://{domain}/api/v1/forms/{form_id}.json"
            resp = fetch_data(url, self.auth, callback=self.error_occurred)
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    data_count = data.get("num_of_submissions")
                    from_date = data.get("date_created")
                    to_date = data.get("last_submission_time") or data.get("date_modified")
                    data_dict = {
                        "count": data_count,
                        "from_date": from_date,
                        "to_date": to_date
                    }
                    self.count_and_date_fields_fetched.emit(data_dict)
                    return data_dict
            else:
                self.count_and_date_fields_error_occurred.emit("No Data Found")
        return

    def run(self):
        geofields_set = set()
        geofields_dict = dict()

        # fetch versions
        domain = self.url.split("/")[2]
        form_id = self.formID

        if form_id:
            _ = self.fetch_form_details()

        response = fetch_data(self.url, self.auth, callback=self.error_occurred)
        if response.status_code == 200:
            versions = response.json()
            if versions:
                total_versions = len(versions)
                self.progress_updated.emit(f"Total Form versions - {total_versions}")

                for i, v in enumerate(versions):
                    version_str = v.get("version")
                    version_url = f"https://{domain}/api/v1/forms/{form_id}/versions/{version_str}"
                    self.progress_updated.emit(f"Fetching Form Schema for {version_str}...")
                    self.progress_updated.emit({
                        "curr_page": i + 1,
                        "total_pages": total_versions
                    })
                    res = fetch_data(version_url, self.auth, callback=self.error_occurred)
                    if res.status_code == 200:
                        self.progress_updated.emit(f"Done \n")
                        the_v = res.json()
                        if the_v:
                            fields = the_v.get("children")
                            retrieve_all_geofields(fields, geofields_set, geofields_dict)
                    else:
                        version_url = f"https://{domain}/api/v1/forms/{form_id}/form.json"
                        self.progress_updated.emit(f"Unable to fetch older Form Versions, Falling back to default...")
                        res = fetch_data(version_url, self.auth, callback=self.error_occurred)
                        if res.status_code == 200:
                            self.progress_updated.emit(f"Done \n")
                            the_v = res.json()
                            fields = the_v.get("children")
                            if fields:
                                retrieve_all_geofields(fields, geofields_set, geofields_dict)
                        else:
                            self.error_occurred.emit(f"Request Failed, status code - {res.status_code}")

                if geofields_set and geofields_dict:
                    self.data_fetched.emit({
                        "geo_fields_set": geofields_set,
                        "geo_fields_dict": geofields_dict
                    })

            else:
                self.error_occurred.emit("No versions found")
        else:
            if response.status_code == 500:
                version_url = f"https://{domain}/api/v1/forms/{form_id}/form.json"
                self.progress_updated.emit(f"Unable to fetch older Form Versions, Falling back to default...")
                res = fetch_data(version_url, self.auth, callback=self.error_occurred)
                if res.status_code == 200:
                    self.progress_updated.emit(f"Done \n")
                    the_v = json.dumps(res.json())
                    fields = json.loads(the_v).get("children")
                    retrieve_all_geofields(fields, geofields_set, geofields_dict)
                    if geofields_set and geofields_dict:
                        self.data_fetched.emit({
                            "geo_fields_set": geofields_set,
                            "geo_fields_dict": geofields_dict
                        })
                else:
                    self.error_occurred.emit(f"Request Failed, status code - {res.status_code}")
            else:
                self.status_error.emit(f"Failed, status code - {response.status_code}")


class FetchODKFormsThread(QThread):
    data_fetched = pyqtSignal(object)  # Signal to emit the response
    progress_updated = pyqtSignal(object)
    error_occurred = pyqtSignal(object)  # Signal to emit errors

    def __init__(self, url, auth=None, params=None, headers=None, total_records=None, records_per_page=None, formID=None):
        super().__init__()
        self.url = url
        self.auth = auth
        self.params = params
        self.headers = headers
        self.max_retries = 5
        self.backoff_factor = 0.2
        self.total_records = total_records
        self.records_per_page = records_per_page
        self.formID = formID


                




        


