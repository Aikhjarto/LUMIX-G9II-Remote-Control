import logging
import os
import urllib.parse
import urllib.request
from typing import Dict, Tuple, List

from qtpy import QtCore, QtGui
from qtpy.QtCore import QUrl, Signal, Slot
from qtpy.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from qtpy.QtWidgets import (
    QAction,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QErrorMessage,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..types import ResourceDict

class QReadOnlyCheckBox(QCheckBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(QtGui.Qt.FocusPolicy.NoFocus)

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        event.ignore()


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

        self.age_in_days_lineedit = QLineEdit()
        self.age_in_days_lineedit.setPlaceholderText("Age in days")
        self.age_in_days_lineedit.setToolTip(
            "0 means no restriction, 1 means today, 2 means today and yesterday,..."
        )

        self.sd_card_select = QComboBox()
        self.sd_card_select.addItem("SD1")
        self.sd_card_select.addItem("SD2")
        self.sd_card_select.currentIndexChanged.connect(self.select_sd)

        pos_int_validator = QtGui.QRegularExpressionValidator(
            QtCore.QRegularExpression("\\d*")
        )
        self.age_in_days_lineedit.setValidator(pos_int_validator)
        self.line_edit = QLineEdit()
        self.line_edit.setText(os.getcwd())
        self.folder_select_button = QPushButton("Folder select")
        self.folder_select_button.clicked.connect(self.select_folder)

        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self.update_image_list_button)
        controls_layout.addWidget(self.q0_checkbox)
        controls_layout.addWidget(self.q1_checkbox)
        controls_layout.addWidget(self.q2_checkbox)
        controls_layout.addWidget(self.q3_checkbox)
        controls_layout.addWidget(self.q4_checkbox)
        controls_layout.addWidget(self.q5_checkbox)
        controls_layout.addWidget(self.age_in_days_lineedit)
        controls_layout.addWidget(self.sd_card_select)

        controls_layout.addWidget(self.folder_select_button)
        controls_layout.addWidget(self.line_edit)

        self.update_image_list_button.pressed.connect(self._emit_image_list_request)

        self.play_mode_table_widget = PlayModeTableWidget()

        layout = QVBoxLayout()
        layout.addLayout(controls_layout)
        layout.addWidget(self.play_mode_table_widget)

        self.setLayout(layout)

    def select_folder(self):
        self.line_edit.setText(
            QFileDialog.getExistingDirectory(self, "Select Directory")
        )

    def select_sd(self):
        raise NotImplementedError

    @Slot()
    def _emit_image_list_request(self):
        for req in self.play_mode_table_widget._network_access_manager.findChildren(
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

        QApplication.sendEvent(
            self,
            QtGui.QStatusTipEvent(
                "Requesting SD Card Content with filter {filter_dict}"
            ),
        )
        self.imageListRequest.emit(filter_dict)


class PlayModeTableWidget(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.host: str = ""
        self._headers: Dict[str, str] = dict()

        self._network_access_manager = QNetworkAccessManager(self)
        self._network_access_manager.finished.connect(self._thumbnail_request_finished_callback)

        # map remote path to local table item
        self._items_dict: Dict[str, QTableWidgetItem] = {}

        # map row to underlying data for additional queries like download of RAW image
        self._resource_dict: Dict[int, ResourceDict] = {}

        # map remote path to thumbnail, where the bytearray holds jpg encoded data
        # and the pixmap is a possibly scaled version to fit in the table
        self._thumbnail_cache: Dict[str, Tuple[QtGui.QPixmap, QtCore.QByteArray]] = {}
        self._large_thumbnail_height: int = 480

        self.horizontalHeader().setStretchLastSection(True)
        self.setContextMenuPolicy(QtGui.Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.contextMenuEvent)

        self._local_folder: str = '.'

    def clear_cache(self):
        self._thumbnail_cache = {}

    def contextMenuEvent(self, pos: QtCore.QPoint):
        # index = self.indexAt(pos)
        # print(index)
        menu = QMenu(self)
        action = menu.addAction("Download Original")
        action.triggered.connect(self.download_selection)
        action = menu.addAction("Download Large Thumbnail")
        action.triggered.connect(self.download_large_thumbnail_for_selection)
        menu.popup(self.viewport().mapToGlobal(pos))

    @property
    def local_folder(self):
        return self._local_folder

    @local_folder.setter
    def local_folder(self, folder: str):
        if not os.path.isdir(folder):
            raise RuntimeError(f'{folder} is not a folder')
        
        self._local_folder

    def _update_downloaded_checkbox(self):
        for row in self.rowCount():
            raise RuntimeError

    def get_local_filename(self, resource: ResourceDict):
        # TODO folder path
        local_filename = os.path.splitext(resource["OriginalFileName"])[0]
        if "CAM_RAW" in resource:
            local_filename += ".RW2"

        if "CAM_RAW_JPG" in resource:
            local_filename += ".JPG"

        if "CAM_AVC_MP4_ORG" in resource:
            local_filename += ".MP4"

        return os.path.join(self._local_folder, local_filename)

    def download_large_thumbnail_for_selection(self):
        for rng in self.selectedRanges():
            for row in range(rng.topRow(), rng.bottomRow() + 1):
                resource = self._resource_dict[row]
                url = resource["CAM_LRGTN"]
                item = self._new_thumbnail_image_item(
                    url, priority=QNetworkRequest.Priority.HighPriority
                )
                self.setItem(row, 0, item)
                self.resizeRowToContents(row)

    def download_selection(self):

        # logger.info("Downloading to %s", self.line_edit.text())
        for rng in self.selectedRanges():
            for row in range(rng.topRow(), rng.bottomRow() + 1):

                resource = self._resource_dict[row]
                # print(row, resource["OriginalFileName"])

                local_filename = os.path.join(self._local_folder,
                                              os.path.splitext(resource["OriginalFileName"]))
                
                if "CAM_RAW" in resource:
                    url = resource["CAM_RAW"]

                if "CAM_RAW_JPG" in resource:
                    url = resource["CAM_RAW_JPG"]

                if "CAM_JPG_ORG" in resource:
                    url = resource["CAM_JPG_ORG"]

                if "CAM_AVC_MP4_ORG" in resource:
                    url = resource["CAM_AVC_MP4_ORG"]

                if not os.path.isfile(local_filename):
                    logger.info("Downloading %s to %s", url, local_filename)
                    QApplication.sendEvent(
                        self,
                        QtGui.QStatusTipEvent(
                            f"Downloading {url} to {local_filename}"
                        ),
                    )
                    urllib.request.urlretrieve(url, local_filename)

                self.cellWidget(row, 1).setCheckState(QtCore.Qt.CheckState.Checked)

        logger.info("Download done")
        QApplication.sendEvent(self, QtGui.QStatusTipEvent("Downloading done"))

    def update_resource_list(resource_list):

        raise NotImplementedError

    def _new_thumbnail_image_item(self, uri: str, priority=None):

        remote_path = urllib.parse.urlsplit(uri).path
        item = QTableWidgetItem()
        self._items_dict[remote_path] = item
        if remote_path in self._thumbnail_cache:
            self._items_dict[remote_path].setData(
                QtCore.Qt.ItemDataRole.DecorationRole,
                self._thumbnail_cache[remote_path][0],
            )
        else:
            item.setText(uri)
            self.send_request(uri, priority=priority)

        return item

    def new_resource_list(self, resource_list: List[ResourceDict]):

        self._resource_dict = {}
        self.clear()
        self.setColumnCount(4)
        self.setRowCount(len(resource_list))

        for row, resource in enumerate(resource_list):

            self._resource_dict[row] = resource

            thumbnail_uri = resource["CAM_TN"]
            item = self._new_thumbnail_image_item(thumbnail_uri)
            self.setItem(row, 0, item)
            self.resizeRowToContents(row)
            self.resizeColumnToContents(0)

            check_box = QReadOnlyCheckBox()
            check_box.setToolTip("Item already on local computer")
            self.setCellWidget(row, 1, check_box)
            local_filename = self.get_local_filename(resource)
            if os.path.isfile(local_filename):
                self.cellWidget(row, 1).setCheckState(QtCore.Qt.CheckState.Checked)

            if "CAM_ORG" in resource:
                typ = 'JPG'
            elif "CAM_RAW" in resource:
                if "CAM_RAW_JPG" in resource:
                    typ = 'RAW+JPG'
                else:
                    typ = "RAW"
            elif "CAM_AVC_MP4_ORG" in resource:
                typ='MP4'
            else:
                logger.error('Cannot find type for resource %s', resource)
 
            description_item = QTableWidgetItem(typ)
            self.setItem(row, 2, description_item)
        

            description_item = QTableWidgetItem()
            description_item.setText(f"Resource {resource}")
            self.setItem(row, 3, description_item)

    def send_request(
        self, url: str, priority: QNetworkRequest.Priority.HighPriority = None
    ):
        qurl = QUrl(url)
        qurl.setHost(self.host)
        request = QNetworkRequest(qurl)
        if priority != None:
            request.setPriority(priority)
        for key, value in self._headers.items():
            request.setRawHeader(key.encode(), value.encode())
        self._network_access_manager.get(request)

    def _thumbnail_request_finished_callback(self, reply: QNetworkReply):
        if not reply.isFinished():
            logger.error("reply {reply} is not finished!")
            return
        
        key = reply.url().path()
        data = reply.readAll()
        item = self._items_dict[key]

        pixmap = QtGui.QPixmap()
        pixmap.loadFromData(data)

        logger.info(f"Got {reply.url().toString()} pixmap w/h {pixmap.width()}/{pixmap.height()}")

        if pixmap.height()>self._large_thumbnail_height:
            pixmap = pixmap.scaledToHeight(self._large_thumbnail_height)
        item.setData(QtCore.Qt.ItemDataRole.DecorationRole, pixmap)
        item.setText("")
        row = item.row()
        item.tableWidget().resizeRowToContents(row)
        item.tableWidget().resizeColumnToContents(0)
        self._thumbnail_cache[key] = (pixmap, data)

        reply.deleteLater()

    @Slot(dict)
    def update_connection_state(self, d):
        self.host = d["host"]
        self._headers = d["headers"]
