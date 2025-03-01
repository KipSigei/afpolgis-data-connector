# -*- coding: utf-8 -*-
"""
/***************************************************************************
 AfpolGISDialog
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

from qgis.PyQt.QtWidgets import QDialog
from .afpolgis_dialog_base import Ui_AfpolGISDialogBase


class AfpolGISDialog(QDialog, Ui_AfpolGISDialogBase):
    def __init__(self, parent=None, option=None):
        super(AfpolGISDialog, self).__init__(parent)
        self.setupUi(self)

        # Initialize any additional UI elements or logic
        self.setWindowTitle("AfpolGIS Data Connector")
