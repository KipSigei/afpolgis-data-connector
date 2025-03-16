
# AfPoLGIS QGIS Plugin Technical Guide
- [AfPoLGIS QGIS Plugin Technical Guide](#afpolgis-qgis-plugin-technical-guide)
  - [1. Getting Started](#1-getting-started)
    - [1.1 Requirements](#11-requirements)
    - [1.2 Installation from QGIS App Repository](#12-installation-from-qgis-app-repository)
  - [2. Overview of the Plugin Interface](#2-overview-of-the-plugin-interface)
  - [3. OnaData Integration](#3-onadata-integration)
    - [3.1 Interface Details](#31-interface-details)
    - [3.2 Workflow for Onadata](#32-workflow-for-onadata)
  - [4. ODK Integration](#4-odk-integration)
    - [4.1 Interface Details](#41-interface-details)
    - [4.2 Workflow for ODK](#42-workflow-for-odk)
  - [5. KoboToolbox Integration](#5-kobotoolbox-integration)
    - [5.1 Interface Details](#51-interface-details)
    - [5.2 Workflow for KoboToolbox](#52-workflow-for-kobotoolbox)
  - [6. Environmental Surveillance (ES) Integration](#6-environmental-surveillance-es-integration)
    - [6.1 Interface Details](#61-interface-details)
    - [6.2 Workflow for ES](#62-workflow-for-es)
  - [7. GTS Integration](#7-gts-integration)
    - [7.1 Interface Details](#71-interface-details)
    - [7.2 Workflow for GTS](#72-workflow-for-gts)
  - [8. DHIS Integration](#8-dhis-integration)
    - [8.1 Interface Details](#81-interface-details)
    - [8.2 Workflow for DHIS](#82-workflow-for-dhis)
  - [9. POLIS Integration](#9-polis-integration)
    - [Interface Details for POLIS](#interface-details-for-polis)
    - [Workflow for POLIS](#workflow-for-polis)
  - [10. AFRO Boundaries](#10-afro-boundaries)
    - [Interface Details for AFRO Boundaries](#interface-details-for-afro-boundaries)
    - [Workflow for AFRO Boundaries](#workflow-for-afro-boundaries)
  - [9. Additional Functionality and Best Practices](#9-additional-functionality-and-best-practices)
    - [9.1 Logs and Diagnostics](#91-logs-and-diagnostics)
    - [9.2 Customizing Your Data Layers](#92-customizing-your-data-layers)
    - [9.3 Exporting Data](#93-exporting-data)
    - [9.4 Troubleshooting Tips](#94-troubleshooting-tips)
  - [10. Conclusion](#10-conclusion)

---

## 1. Getting Started
This comprehensive guide walks you through installing and using the **AfPoLGIS Data Connector** plugin within QGIS. The plugin connects QGIS to multiple external data platforms, enabling you to fetch and visualize spatial data from diverse sources. In this guide, we explain how to set up and use each of the seven integrations supported by the plugin: **Onadata, ODK, KoboToolbox, ES, GTS, DHIS and POLIS**.

![App Platform](/img/screenshot_1.png)

![App Platform](/img/screenshot_2.png)

### 1.1 Requirements
- **QGIS Version:** Ensure that you have QGIS **version 3 or above** installed on your system.
- **Internet Connection:** A stable internet connection is required to communicate with remote data services.
- **User Credentials:** You should have valid login credentials for the external data platforms you intend to use (Onadata, ODK, KoboToolbox, etc.).

### 1.2 Installation from QGIS App Repository
1. **Launch QGIS:** Open your QGIS application.
2. **Access Plugin Manager:** Click on the **Plugins** menu and select **Manage and Install Plugins...**.
3. **Search for the Plugin:** In the search bar, type **"AfPoLGIS Data Connector"**.
4. **Install the Plugin:** Click on the plugin from the search results, then click **Install**.
5. **Plugin Activation:** Once installed, the plugin is activated automatically. You can now access its interface from the **Plugins** menu or via its dedicated panel in the QGIS workspace.

> **Tip:** If you encounter any issues during installation, ensure that your QGIS version is up-to-date and that your internet connection is active.

---

## 2. Overview of the Plugin Interface

Once the plugin is installed, you will notice several tabs within its interface. These tabs correspond to the supported data integrations and additional functionalities:
- **OnaData**
- **ODK**
- **KoboToolbox**
- **ES (Environmental Surveillance)**
- **GTS (Geospatial Tracking System)** 
- **DHIS**
- **POLIS**
- **AFRO boundaries**

Each integration follows a similar workflow:
1. **Input Configuration:** Fill in required parameters such as API Base URL, credentials, and filtering options. Note that we have provided a default API Base URL for each integration
2. **Connection Establishment:** Click **Connect** to authenticate and retrieve available datasets or forms.
3. **Data Selection:** Choose the specific dataset, form, or category from a dropdown list.
4. **Data Loading:** Click **Load Data To Map** to import the selected data as a geospatial layer in your QGIS project.
5. **Data Export (Optional):** Use the **Export CSV** option if you need to download the data in CSV format.

---

## 3. OnaData Integration

OnaData (now known as PADACOR) is a widely used platform for managing form data submissions. This integration helps users pull spatial data submitted through OnaData forms directly into QGIS.

### 3.1 Interface Details
- **API Base URL:** Enter the endpoint URL (e.g., `esurv.afro.who.int`).
- **Credentials:** Provide your OnaData username and password if you already have an account.
- **Form Selection:** A dropdown that lists available forms linked to your account after authenticating with the platform.
- **Geo Field Option:** Specify which field holds geographic data of interest, if your form contains multiple geometry fields defined.
- **Sync Options:** Configure date filters (e.g., Date From, Date To), sync intervals, and pagination (Page Size).

### 3.2 Workflow for Onadata
1. **Connect:** After entering the desired API URL and correct credentials, click **Connect** button. The plugin will verify your credentials and fetch a list of forms.
2. **Select Data:** Choose the desired form from the dropdown list.
3. **Customize Sync:** Adjust the date range and other options to target specific submissions.
4. **Load Data:** Click **Load Data To Map** to import the chosen form's data as a layer.
5. **Export (Optional):** If needed for futher analysis using other softwares i.e Power BI, ArcGIS, etc, export the data to CSV by clicking **Export CSV**.

> **Note:** The progress indicators and error logs can help troubleshoot any connection issues that might be encountered.

---

## 4. ODK Integration

ODK (Open Data Kit) is a popular tool for mobile data collection. The integration allows you to retrieve and visualize your ODK data effortlessly.

### 4.1 Interface Details
- **API Base URL:** Input the URL of your ODK server (e.g., `odk.server.url`).
- **Credentials:** Enter your ODK username and password if your already have an account.
- **Form Selection:** A list populated with available ODK forms after a successful connection.
- **Geo Field & Filters:** Option to specify a geographic field defined in the form and apply filters like date ranges or sync intervals.

### 4.2 Workflow for ODK
1. **Establish Connection:** Fill in the server URL and your credentials, then click **Connect**.
2. **Retrieve Forms:** The plugin retrieves and displays a list of available forms in your account.
3. **Select and Configure:** Choose a form, set your sync options (including date filters if necessary - you can leave as default), and select the geo field that you want to visualize.
4. **Data Import:** Click **Load Data To Map** to import the data into QGIS.
5. **CSV Export:** Use the **Export CSV** option to save a local copy of the data if desired.

> **Tip:** Double-check that your ODK server URL is correct, as minor errors can cause connection failures.

---

## 5. KoboToolbox Integration

KoboToolbox is a robust platform for data collection and analysis, especially in humanitarian contexts. This integration makes it easy to bring your KoboToolbox data into QGIS.

### 5.1 Interface Details
- **API Base URL:** Typically `kf.kobotoolbox.org` or a custom instance URL.
- **Credentials:** Enter your KoboToolbox username and password.
- **Form List:** Displays forms available in your account once connected.
- **Geo Field & Filtering Options:** Options to specify the geographic field and apply various data filters like date ranges and sync intervals.

### 5.2 Workflow for KoboToolbox
1. **Connection Setup:** Navigate to the **Kobo** tab and input your API URL and credentials.
2. **Authenticate and Retrieve:** Click **Connect** to authenticate and pull the list of forms.
3. **Form and Field Selection:** Choose the form you want to use and specify the geo field you want to load as a layer.
4. **Set Sync Parameters:** Define date filters, sync intervals, and page sizes if necessary - you can leave as default.
5. **Load Data:** Click **Load Data To Map** to import the dataset into your QGIS project.
6. **Optional CSV Export:** Export the data to CSV using the **Export CSV** button if required.

---

## 6. Environmental Surveillance (ES) Integration

The Environmental Surveillance is a platform that monitors environmental samples to detect pathogens early, enabling prompt public health interventions. 

### 6.1 Interface Details
- **API Base URL:** Input the URL of your ES server (e.g., `es.world`).
- **Version Specification:** Enter the Environmental Surveillance API version if needed (for example, currently its version 4.3).
- **Topography/Index:** Specify the index or dataset name, often related to the geographic or thematic content (e.g., "Sites").

### 6.2 Workflow for ES
1. **Configure Connection:** In the **ES** tab, fill in the API URL, version, and topography details.
2. **Establish Connection:** Click **Connect** to initiate a connection to the ES server. A progress bar will indicate connection status.
3. **Data Query:** After connection, the plugin retrieves available data based on the selected topography.
4. **Import Data:** Click **Load Data To Map** to visualize the data within QGIS.
5. **CSV Export Option:** If you need the data for offline analysis, use the **Export CSV** option.

---

## 7. GTS Integration

The GTS integration facilitates connection to the GTS platform, which is used for managing health data i.e disease outbreaks, vaccination coverage and health facility locations

### 7.1 Interface Details
- **API Base URL:** Enter the GTS endpoint (e.g., `gts.health`).
- **Credentials:** Input your GTS username and password, if required.
- **Category Selection:** Choose a specific data category relevant to your work.
- **Field Activity and Tracking Rounds:** Options to select the activity type and the corresponding tracking round, if applicable.

### 7.2 Workflow for GTS
1. **Initial Setup:** In the **GTS** tab, provide the API URL (if necessary) and your credentials.
2. **Connect:** Click **Connect** to authenticate and fetch available categories.
3. **Select Options:** From the dropdown menus, choose the appropriate Category. The categories currently supported in the platform are `odk_tables`, `indicator_tables` and `tracking_tables`. Once you select the required category below it you can select the corresponding Field Activity and Tracking Round.
4. **Data Import:** Click **Load Data To Map** to load the selected data as layer into QGIS.
5. **Exporting Data:** Utilize the **Export CSV** button if you need to export the dataset.

> **Best Practice:** Use the logs and progress feedback to verify that data retrieval aligns with your selections.

---

## 8. DHIS Integration

DHIS (District Health Information Software) is widely used for health data management. This integration allows you to import structured health data directly from DHIS2 into QGIS.

### 8.1 Interface Details
- **API Base URL:** Provide the URL of your DHIS server or instance (e.g., `dhis-minsante-cm.org`).
- **Credentials:** Enter your DHIS2 username and password.
- **Data Category:** Options include Selecting a Program or Dataset.
- **Administrative Level:** Select the administrative level (e.g., Level 1, Level 2) for your data.
- **Program or Dataset:** Based on the selected category, choose the relevant program or dataset.
- **Time Period:** Filter the data using predefined relative periods such as “TODAY”, “LAST_7_DAYS”, "LAST_3_MONTHS", etc.

### 8.2 Workflow for DHIS
1. **Connect to DHIS:** In the **DHIS** tab, enter the API Base URL along with your DHIS credentials, then click **Connect**.
2. **Retrieve Data Options:** The plugin will display available programs, datasets, and administrative levels.
3. **Set Parameters:** Select the Category, Admin Level, Program/Dataset, Indicator and the desired time period.
4. **Load Data:** Click **Load Data To Map** to import the DHIS data into your QGIS project.
5. **CSV Export:** Optionally, export the data to a CSV file by clicking **Export CSV**.

> **Note:** Ensure that your DHIS account has the necessary permissions to access the selected datasets.

---

## 9. POLIS Integration

POLIS (Polio Information System) is a WHO platform used to track and visualize polio-related data, including immunization coverage and surveillance indicators

### Interface Details for POLIS
- **API Base URL:** Enter the POLIS service endpoint (e.g., default is set to `extranet.who.int/polis`).
- **Auth Token:** Provide your authentication token if required. If you do not have a token, you may need to request one (e.g., by contacting `polis@who.int`).
- **Admin Selection:**
  - **Select Area:** For instance, "AFRO" (or another region, if applicable).
  - **Select Country:** You can either choose a specific Country or **Show All**.
  - **Select Province:** You can either choose a specific Province or **Show All**.
  - **Select District:** You can either choose a specific District or **Show All**.
- **Classification:**
  - **Select Visual Category:** Choose one from indicators, Viruses or Cases.
  - **Indicator:** Select a specific indicator (e.g., polio percentage for 6M-59M).
  - **Select Virus Type** Select the virus type i.e VDPV 1
- **Sync Options:**
  - **Date Range (From / To):** Filter data by a specific time frame.

### Workflow for POLIS
1. **Establish Connection:**
   1. In the **POLIS** tab, enter the API Base URL (e.g., `extranet.who.int/polis`) and your **Auth Token** if required.
   2. Click **Connect** to authenticate and retrieve available administrative levels, countries, or indicators.
2. **Select Data Parameters:**
   1. **Admin Selection:** Choose the region (e.g., AFRO), country (e.g., ALGERIA), and province if needed.
   2. **Classification:** Pick a visual category and corresponding indicators.
3. **Configure Date Range:** Specify **From** and **To** dates to narrow your data query.
4. **Load Data:** Click **Load Data To Map** to import the selected POLIS data layer into your QGIS project.
5. **CSV Export (Optional):** If needed, use **Export CSV** to download the retrieved data for offline analysis.

> **Tip:** Pay attention to the classification and indicator options to ensure you load the correct data for your mapping or analysis needs.

---

## 10. AFRO Boundaries
These are the administrative boundary shapefiles for countries within the WHO African Region

### Interface Details for AFRO Boundaries
- **Options:**
  - **Admin Level:** A dropdown menu that lets you choose between different administrative levels (e.g., **Countries**, **Regions**, **Districts**, etc.).

> **Note:** The AFRO Boundaries tab may not require explicit credentials since we currently load the shapefiles from a public github repository, but this is temporary. The long term plan is to load from the AFRO Geo Database, and this might require credentials.


### Workflow for AFRO Boundaries
1. **Select Admin Level:** From the dropdown, pick the desired administrative level (e.g., **Countries**, **Regions**, or **Districts**).
2. **Confirm and Load:** Click **OK** to retrieve and import the shapefile into your QGIS project.

> **Best Practice:** Combine the AFRO Boundaries layer with other data sources (e.g., health indicators) to produce rich, multi-layered maps for analysis.

---

## 9. Additional Functionality and Best Practices

### 9.1 Logs and Diagnostics
- **Logs Tab:** Use this tab to review detailed logs and error messages. This is especially useful when troubleshooting connection issues or data import errors.
- **Real-time Feedback:** The plugin provides progress indicators (such as progress bar, percentage completion and push messages) to help monitor data retrieval and sync processes.

### 9.2 Customizing Your Data Layers
- Once data is loaded into QGIS, you can take advantage of QGIS’s powerful styling, labeling, and spatial analysis tools.
- **Layer Management:** Organize your imported layers by grouping them, renaming them, or adjusting symbology for improved visualization.

### 9.3 Exporting Data
- **CSV Export:** Each integration provides an option to export the fetched data as a CSV file. This is useful for further analysis in other analysis softwares or for backup purposes.

### 9.4 Troubleshooting Tips
- **Connection Issues:** Verify that API URL's are correct and that your credentials are current.
- **Data Sync Problems:** Check the filtering parameters (e.g., date ranges, page sizes) to ensure they match the dataset's available data.
- **Consult the Logs:** Use the Logs tab to pinpoint errors or misconfigurations during the connection process.

---

## 10. Conclusion

The **AfPoLGIS Data Connector** plugin simplifies the process of integrating spatial data from diverse sources into QGIS. Whether you are using Onadata, ODK, KoboToolbox, Environmental Surveillance, GTS, or DHIS, the plugin provides a consistent workflow to authenticate, query, and import data seamlessly. By following this guide, you can ensure that you set up each integration correctly and make full use of QGIS’s capabilities for spatial data analysis.

**Happy Mapping!**
