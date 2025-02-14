"""
/***************************************************************************
 AfpolGIS
                                 A QGIS plugin
 Fetch and load geospatial data from ODK, Onadata, Kobo, ES World, GTS and DHIS
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                             -------------------
        begin                : 2025-01-09
        git sha              : $Format:%H$
        copyright            : (C) 2025 by Kipchirchir Cheroigin
        email                : kcheroigin@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

def classFactory(iface):
  from .afpolgis import AfpolGIS
  return AfpolGIS(iface)

# any other initialisation needed