# AfpolGIS Data Connector

![App Platform](/img/screenshot_1.png)

![App Platform](/img/screenshot_2.png)

## Overview

The **AfpolGIS Data Connector** allows users to fetch Geospatial data from diverse Data API's and load it directly into QGIS as a layer. The plugin fetches and loads the data asynchronously, supports filtering data by date ranges as well as real time synchronization of data.

## Features

- Fetch Geospatial data from Onadata, ODK, KoboToolbox, GTS, ES World and DHIS
- Load the data directly into QGIS as a layer
- Asynchronous data fetching with QThread
- Filtering Data by Date Ranges
- Supports paginated API requests
- Automatic zoom to layer after loading

## Requirements

To run this plugin, you will need the following installed in your machine:

- `python 3.12`


### Option 1: Automatic Installation (QGIS 3.20+)

For QGIS versions 3.20 and above, the plugin can handle its dependencies automatically. Ensure that you are connected to the internet during installation so QGIS can install the required Python packages. If this doesn't work, kindly try Option 2.

### Option 2: Manual Installation of Python Dependencies

If the automatic installation doesn't work, you will need to manually install the required Python packages.

## Plugin Installation
1. Download the plugin’s **.zip** file from the repository.
2. Open **QGIS**.
3. In the top menu, go to **Plugins > Manage and Install Plugins**.
4. Click the **Install from ZIP option**.
5. Browse for the .zip file you downloaded and click **Install Plugin**.

## Usage Instructions
1. After installation, the plugin will appear in the QGIS toolbar or under **Plugins > AfpolGIS Data Connector**.
2. Click the plugin icon to open the main dialog.
3. Fill out the required fields:
   - Input your credentials
   - Depending on the selected platform tab, you have selection options that you will go through depending on the use case
4. Click **OK** to initiate the data fetch process. The plugin will:
   - Display a progress bar showing the fetching status.
   - Load the fetched GeoJSON data into QGIS as a layer.
   - Zoom to the layer after successful loading.
   - Reset the input fields and close dialog after successful data fetching and layer loading into QGIS.

## Next Steps
1. Add a way to save credentials (username/password) so that they can be pre-loaded to avoid having to re-enter when relaunching the application
2. The sync functionality currently works per layer per platform. The plan is to add functionality to have the sync work for all OnaData, Kobo or ODK layers added to QGIS
3. Add a search field to filter long list of form names on dropdown
4. Create a similar plugin for ArcGIS Pro