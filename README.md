# QGIS Ona API Connector Plugin

![App Platform](/img/screenshot_1.png)

![App Platform](/img/screenshot_2.png)

## Overview

The **QGIS Ona API Connector Plugin** allows users to fetch GeoJSON data from the Ona API and load it directly into QGIS as a layer. The plugin fetches and saves the data asynchronously and supports handling multiple pages of data from the API.

## Features

- Fetch GeoJSON data from Ona API
- Load the data directly into QGIS as a layer
- Asynchronous data fetching with QThreadPool
- Password field for API credentials with toggleable visibility
- Supports paginated API requests
- Automatic zoom to layer after loading
- Reset input fields and dialog after loading

## Requirements

To run this plugin, you will need the following installed in your machine:

- `python3.12`
- `httpx`


### Option 1: Automatic Installation (QGIS 3.20+)

For QGIS versions 3.20 and above, the plugin can handle its dependencies automatically. Ensure that you are connected to the internet during installation so QGIS can install the required Python packages. If this doesn't work, kindly try Option 2.

### Option 2: Manual Installation of Python Dependencies

If the automatic installation doesn't work, you will need to manually install the required Python packages.

#### Steps to Install dependencies:

1. First ensure that you have the QGIS software installed as well as python 3.12
2. Click on the Windows Start menu or press the Windows key.
3. Type **OSGeo4W Shell** in the search bar. You should see a result named **OSGeo4W Shell** (it might have a black terminal icon).
4. In the **OSGeo4W** command prompt Install the required packages using pip:
   ```bash
   pip install requests httpx
   ```
If you do not have pip, follow the installation instructions [here](https://pip.pypa.io/en/stable/installation/) to install it.

## Plugin Installation
1. Download the plugin’s **.zip** file from the repository.
2. Open **QGIS**.
3. In the top menu, go to **Plugins > Manage and Install Plugins**.
4. Click the **Install from ZIP option**.
5. Browse for the .zip file you downloaded and click **Install Plugin**.

## Usage Instructions
1. After installation, the plugin will appear in the QGIS toolbar or under **Plugins > QGIS Ona API Connector**.
2. Click the plugin icon to open the main dialog.
3. Fill out the required fields:
   - **API Base URL**: Provide the base domain of the Ona API i.e api.whonghub.org.
   - **Form ID**: The ID of the form from which data will be fetched.
   - **Username and Password**: Enter your Ona credentials. The password field will obscure the input by default.
   - **Page Size**: Set the desired number of records to fetch per page. The maximum allowed is currently 1000 records per page
   - **Select Geo Field**: Select the geographic field from the dropdown (e.g., location). This is populated after clicking the `Fetch Geo Fields` Button.
4. Select a **Save Directory** where the project will be saved.
5. Click **OK** to initiate the data fetch process. The plugin will:
   - Display a progress bar showing the fetching status.
   - Load the fetched GeoJSON data into QGIS as a layer.
   - Zoom to the layer after successful loading.
   - Reset the input fields and close dialog after successful data fetching and layer loading into QGIS.

## Next Steps
1. Add a way to save credentials (username/password) so that they can be pre-loaded to avoid having to re-enter when relaunching the application
2. Refresh interval - Add ability to periodically fetch new data
3. Create a similar plugin for ArcGIS Pro