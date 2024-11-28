import logging
import urllib.parse
from typing import Dict

from qtpy import QtCore, QtGui
from qtpy.QtCore import QUrl, Signal, Slot
from qtpy.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from qtpy.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QErrorMessage,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

logging.basicConfig()
logger = logging.getLogger()


class PlayModeWidget(QWidget):

    imageListRequest = Signal(dict)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.error_message = QErrorMessage()

        self.update_image_list_button = QPushButton(text="Update")
        self.q0_checkbox = QCheckBox("0")
        self.q1_checkbox = QCheckBox("1")
        self.q2_checkbox = QCheckBox("2")
        self.q3_checkbox = QCheckBox("3")
        self.q4_checkbox = QCheckBox("4")
        self.q5_checkbox = QCheckBox("5")

        self.q0_checkbox.setChecked(True)
        self.q1_checkbox.setChecked(True)
        self.q2_checkbox.setChecked(True)
        self.q3_checkbox.setChecked(True)
        self.q4_checkbox.setChecked(True)
        self.q5_checkbox.setChecked(True)

        # self.quality_group = QButtonGroup()
        # self.quality_group.addButton(self.q0_checkbox)
        # self.quality_group.addButton(self.q1_checkbox)
        # self.quality_group.addButton(self.q2_checkbox)
        # self.quality_group.addButton(self.q3_checkbox)
        # self.quality_group.addButton(self.q4_checkbox)
        # self.quality_group.addButton(self.q5_checkbox)

        self.age_in_days_lineedit = QLineEdit()
        self.age_in_days_lineedit.setPlaceholderText("Age in days")
        self.age_in_days_lineedit.setToolTip(
            "0 means no restriction, 1 means today, 2 means today and yesterday,..."
        )

        pos_int_validator = QtGui.QRegularExpressionValidator(
            QtCore.QRegularExpression("\\d*")
        )
        self.age_in_days_lineedit.setValidator(pos_int_validator)

        # StartingIndex=0,
        # RequestedCount=15,
        # age_in_days: int = None,
        # rating_list: Tuple[int] = (0,),
        # object_id_str="0",

        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self.update_image_list_button)
        controls_layout.addWidget(self.q0_checkbox)
        controls_layout.addWidget(self.q1_checkbox)
        controls_layout.addWidget(self.q2_checkbox)
        controls_layout.addWidget(self.q3_checkbox)
        controls_layout.addWidget(self.q4_checkbox)
        controls_layout.addWidget(self.q5_checkbox)

        controls_layout.addWidget(self.age_in_days_lineedit)

        self.update_image_list_button.pressed.connect(self._emit_image_list_request)

        self.play_mode_table_widget = PlayModeTableWidget()

        layout = QVBoxLayout()
        layout.addLayout(controls_layout)
        layout.addWidget(self.play_mode_table_widget)

        self.setLayout(layout)

    @Slot()
    def _emit_image_list_request(self):
        for req in self.play_mode_table_widget.network_access_manager.findChildren(
            QNetworkReply
        ):
            req.abort()

        filter_dict = {}

        if self.age_in_days_lineedit.text():
            age_in_days = int(self.age_in_days_lineedit.text())
            filter_dict["age_in_days"] = age_in_days

        rating_list = []
        if self.q0_checkbox.isChecked():
            rating_list.append(0)
        if self.q1_checkbox.isChecked():
            rating_list.append(1)
        if self.q2_checkbox.isChecked():
            rating_list.append(2)
        if self.q3_checkbox.isChecked():
            rating_list.append(3)
        if self.q4_checkbox.isChecked():
            rating_list.append(4)
        if self.q5_checkbox.isChecked():
            rating_list.append(5)

        if rating_list:
            filter_dict["rating_list"] = rating_list

        self.imageListRequest.emit(filter_dict)


class PlayModeTableWidget(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.host: str = ""
        self._headers: Dict[str, str] = dict()

        self.network_access_manager = QNetworkAccessManager(self)
        self.network_access_manager.finished.connect(self.reply_finished)

        self.items_dict: Dict[str, QTableWidgetItem] = {}
        self.resource_list = []
        self.thumbnail_cache = {}

    def update_resource_list(self, resource_list):
        self.resource_list = resource_list

        self.clear()
        self.setColumnCount(2)
        self.setRowCount(0)

        for resource in resource_list:

            uri = resource["CAM_TN"]
            key = urllib.parse.urlsplit(uri).path

            item = QTableWidgetItem()
            self.items_dict[key] = item
            numRows = self.rowCount()
            self.insertRow(numRows)
            self.setItem(numRows - 1, 0, item)

            description_item = QTableWidgetItem()
            description_item.setText(f"Resource {resource}")

            self.setItem(numRows - 1, 1, description_item)
            if key in self.thumbnail_cache:
                self.items_dict[key].setData(
                    QtCore.Qt.ItemDataRole.DecorationRole, self.thumbnail_cache[key][0]
                )
                self.resizeRowToContents(numRows)
            else:
                item.setText(uri)
                self.send_request(uri)

    def send_request(self, string: str):
        url = QUrl(string)
        url.setHost(self.host)
        request = QNetworkRequest(url)
        for key, value in self._headers.items():
            request.setRawHeader(key.encode(), value.encode())
        self.network_access_manager.get(request)

    def reply_finished(self, reply: QNetworkReply):
        if not reply.isFinished():
            logger.error("reply {reply} is not finished!")
            return

        data = reply.readAll()

        logger.info(f"reply {reply.url()}")

        pixmap = QtGui.QPixmap()
        pixmap.loadFromData(data)
        key = reply.url().path()
        self.items_dict[key].setData(QtCore.Qt.ItemDataRole.DecorationRole, pixmap)
        row = self.items_dict[key].row()
        self.items_dict[key].tableWidget().resizeRowToContents(row)
        self.thumbnail_cache[key] = (pixmap, data)

        reply.deleteLater()

    @Slot(dict)
    def update_connection_state(self, d):
        self.host = d["host"]
        self._headers = d["headers"]
