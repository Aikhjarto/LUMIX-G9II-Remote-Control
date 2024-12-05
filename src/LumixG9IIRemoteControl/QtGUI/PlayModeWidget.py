import logging
import os
import pprint
import urllib.parse
import urllib.request
from typing import Dict, List, Tuple

from didl_lite import didl_lite
from qtpy import QtCore, QtGui
from qtpy.QtCore import QObject, QUrl, Signal, Slot
from qtpy.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from qtpy.QtWidgets import (
    QAction,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QErrorMessage,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..types import CameraContentItem, CameraFileformatIdentfiers


class QReadOnlyCheckBox(QCheckBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(QtGui.Qt.FocusPolicy.NoFocus)

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        event.ignore()


logging.basicConfig()
logger = logging.getLogger()


class CameraPlayModeConnection(QObject):

    def __init__(self, play_mode_widget, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.play_mode_widget: PlayModeWidget = play_mode_widget


class PlayModeWidget(QWidget):

    imageListRequest = Signal(dict)
    localFolderUpdated = Signal(str)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.host: str = ""
        self._headers: Dict[str, str] = dict()

        # TODO: the first thumbnail requests are fast, the last 6 are really slow, like 1 minute
        self._network_access_manager = QNetworkAccessManager(self)
        self._network_access_manager.finished.connect(
            self._thumbnail_request_finished_callback
        )

        # map remote path to local table item
        self._items_dict: Dict[str, QTableWidgetItem] = {}

        # map remote path to thumbnail, where the bytearray holds jpg encoded data
        # and the pixmap is a possibly scaled version to fit in the table
        self._thumbnail_cache: Dict[str, Tuple[QtGui.QPixmap, QtCore.QByteArray]] = {}
        self._large_thumbnail_height: int = 480

        self.play_mode_table_widgets: Dict[str, PlayModeTableWidget] = {}
        self.play_mode_table_widgets["0"] = PlayModeTableWidget(self)
        self.localFolderUpdated.connect(
            self.play_mode_table_widgets["0"].set_local_folder
        )

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

        filters_layout = QHBoxLayout()
        filters_layout.addWidget(self.q0_checkbox)
        filters_layout.addWidget(self.q1_checkbox)
        filters_layout.addWidget(self.q2_checkbox)
        filters_layout.addWidget(self.q3_checkbox)
        filters_layout.addWidget(self.q4_checkbox)
        filters_layout.addWidget(self.q5_checkbox)
        filters_layout.addWidget(self.age_in_days_lineedit)

        self.filter_groupbox = QGroupBox("Image Query Filter")
        self.filter_groupbox.setCheckable(True)
        self.filter_groupbox.setChecked(False)
        self.filter_groupbox.setLayout(filters_layout)

        self.sd_card_select = QComboBox()
        self.sd_card_select.addItem("SD1")
        self.sd_card_select.addItem("SD2")
        self.sd_card_select.currentIndexChanged.connect(self.select_sd)

        pos_int_validator = QtGui.QRegularExpressionValidator(
            QtCore.QRegularExpression("\\d*")
        )
        self.age_in_days_lineedit.setValidator(pos_int_validator)
        self.local_folder_line_edit = QLineEdit()
        self.local_folder_line_edit.setText(os.getcwd())
        self.folder_select_button = QPushButton("Folder select")
        self.folder_select_button.clicked.connect(self.select_folder)

        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self.update_image_list_button)
        controls_layout.addWidget(self.filter_groupbox)
        controls_layout.addWidget(self.sd_card_select)

        controls_layout.addWidget(self.folder_select_button)
        controls_layout.addWidget(self.local_folder_line_edit)

        self.update_image_list_button.pressed.connect(self._emit_image_list_request)

        layout = QVBoxLayout()
        layout.addLayout(controls_layout)

        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.remove_tab)
        self.tab_widget.addTab(self.play_mode_table_widgets["0"], "0")

        layout.addWidget(self.tab_widget)

        self.setLayout(layout)

    def remove_tab(self, index: int):
        if index > 0:
            self.tab_widget.removeTab(index)

    def select_folder(self):
        self.local_folder_line_edit.setText(
            QFileDialog.getExistingDirectory(self, "Select Directory")
        )
        self.localFolderUpdated.emit(self.local_folder_line_edit.text())

    def clear_cache(self):
        self._thumbnail_cache = {}

    @property
    def local_folder(self):
        return self.local_folder_line_edit.text()

    @local_folder.setter
    def local_folder(self, folder: str):
        if not os.path.isdir(folder):
            raise RuntimeError(f"{folder} is not a folder")
        self.local_folder_line_edit.setText(folder)

    def select_sd(self):
        raise NotImplementedError

    @Slot()
    def _emit_image_list_request(self):
        for req in self._network_access_manager.findChildren(QNetworkReply):
            req.abort()
        self._emit_image_list_request_of_directory()

    def _emit_image_list_request_of_directory(self, object_id: str = None):
        filter_dict = {}

        if object_id is not None:
            filter_dict["object_id_str"] = str(object_id)

        if self.filter_groupbox.isChecked():

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
                f"Requesting SD Card Content with filter {filter_dict}"
            ),
        )
        self.imageListRequest.emit(filter_dict)

    @Slot(dict)
    def update_connection_state(self, d):
        self.host = d["host"]
        self._headers = d["headers"]

    def send_request(
        self, url: str, priority: QNetworkRequest.Priority.HighPriority = None
    ):
        qurl = QUrl(url)
        qurl.setHost(self.host)
        request = QNetworkRequest(qurl)
        if priority is not None:
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

        if pixmap.height() > self._large_thumbnail_height:
            pixmap = pixmap.scaledToHeight(self._large_thumbnail_height)
        item.setData(QtCore.Qt.ItemDataRole.DecorationRole, pixmap)
        item.setText("")
        row = item.row()
        item.tableWidget().resizeRowToContents(row)
        item.tableWidget().resizeColumnToContents(0)
        self._thumbnail_cache[key] = (pixmap, data)

        replies_in_queue: List[QNetworkReply] = reply.manager().findChildren(
            QNetworkReply
        )
        count_finished = 0
        for child in replies_in_queue:
            if child.isFinished():
                count_finished += 1

        logger.info(
            f"Got {reply.url().toString()} pixmap w/h {pixmap.width()}/{pixmap.height()} "
            f"{count_finished}/{len(replies_in_queue)} finished"
        )
        reply.deleteLater()

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

    def update_camera_content_list(self, resource_list: List[CameraContentItem]):
        if resource_list:
            parent_id = resource_list[0]["didl_object"].parent_id
            if parent_id not in self.play_mode_table_widgets:
                self.play_mode_table_widgets[parent_id] = PlayModeTableWidget(self)
                self.localFolderUpdated.connect(
                    self.play_mode_table_widgets[parent_id].set_local_folder
                )

            self.play_mode_table_widgets[parent_id].new_camera_content_list(
                resource_list
            )

    def show_container(self, container: didl_lite.Container):
        if container.id == "0":
            # root container is embedded and always existing
            pass

        if container.id not in self.play_mode_table_widgets:
            self.play_mode_table_widgets[container.id] = PlayModeTableWidget(self)
            self.localFolderUpdated.connect(
                self.play_mode_table_widgets[container.id].set_local_folder
            )
            self._emit_image_list_request_of_directory(container.id)

        idx = self.tab_widget.indexOf(self.play_mode_table_widgets[container.id])
        if idx < 0:
            # self.play_mode_table_widgets[container.id].show()
            remote_thumbnail_path = urllib.parse.urlsplit(container.x__thumb_uri).path
            if remote_thumbnail_path in self._thumbnail_cache:
                icon = QtGui.QIcon(self._thumbnail_cache[remote_thumbnail_path][0])
                idx = self.tab_widget.addTab(
                    self.play_mode_table_widgets[container.id], icon, container.id
                )
            else:
                logger.error(
                    "Not implementent: container openend bevor thumbnail was fetched"
                )
                idx = self.tab_widget.addTab(
                    self.play_mode_table_widgets[container.id], container.id
                )
        self.tab_widget.setCurrentIndex(idx)


class PlayModeTableWidget(QTableWidget):
    def __init__(self, play_mode_widget: PlayModeWidget, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.play_mode_widget = play_mode_widget

        self.horizontalHeader().setStretchLastSection(True)
        self.setContextMenuPolicy(QtGui.Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.contextMenuEvent)

        self.itemDoubleClicked.connect(self.itemDoubleClickedHandler)

        self._local_folder = "."

        # map row to underlying data for additional queries like download of RAW image
        self._camera_content_cache: Dict[int, CameraContentItem] = {}

        # map row to OriginalFilename to downloaded-checkbox
        self._downloaded_checkbox_map: Dict[int, Dict[str, QReadOnlyCheckBox]] = {}

    def contextMenuEvent(self, pos: QtCore.QPoint):
        index = self.indexAt(pos)
        print(index)
        menu = QMenu(self)
        action = menu.addAction("Download Original")
        action.triggered.connect(self.download_selection)
        action = menu.addAction("Download Large Thumbnail")
        action.triggered.connect(self.download_large_thumbnail_for_selection)

        action = menu.addAction("Resize Rows to Contents")
        action.triggered.connect(self.resizeRowsToContents)

        if len(self.selectedIndexes()) == 1:
            row = self.itemAt(pos).row()
            obj = self._camera_content_cache[row]["didl_object"]
            if isinstance(obj, didl_lite.Container):
                action = menu.addAction("Open Container")
                action.triggered.connect(
                    lambda x=self._camera_content_cache[row]: self.open_container(x)
                )

        menu.popup(self.viewport().mapToGlobal(pos))

    # def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent):
    #     event.accept()
    #     index = self.indexAt(event.pos())
    #     logger.info("Double click at index %s, row %s, column %s, with item",
    #                 index, index.row(), index.column())
    #     camera_content_item = self._camera_content_cache[index.row()]
    #     if isinstance(camera_content_item["didl_object"], didl_lite.Container):
    #         containerview = QTableWidget()

    # TODO double click on container item should bring up a new table with container's content.
    # There are two signals:
    # def itemDoubleClickedHandler(self, item: QTableWidgetItem):
    #     logger.info("Clicked at item %s in row %s", item, item.row())

    def itemDoubleClickedHandler(self, item: QTableWidgetItem):
        logger.info("Clicked at item %s in row %s", item, item.row())
        camera_content_item = self._camera_content_cache[item.row()]
        self.open_container(camera_content_item)

    def open_container(self, camera_content_item: CameraContentItem):
        if isinstance(camera_content_item["didl_object"], didl_lite.Container):
            self.play_mode_widget.show_container(camera_content_item["didl_object"])

    # def cellDoubleClicked(int row, int column):

    def set_local_folder(self, folder: str):
        self._local_folder = folder
        self._update_downloaded_checkbox()

    def get_local_folder(self):
        return self._local_folder

    def get_local_filenames(
        self, content_item: CameraContentItem
    ) -> Dict[CameraFileformatIdentfiers, str]:
        d = {}
        for key, value in content_item["resources"].items():
            if original_filename := value["additional_info"].get("OriginalFileName"):
                local_filename = os.path.join(self._local_folder, original_filename)
                d[key] = local_filename
        return d

    def _update_downloaded_checkbox(self):
        for row, filename_map in self._downloaded_checkbox_map.items():
            for filename, checkbox in filename_map.items():
                checkbox.setChecked(
                    os.path.isfile(os.path.join(self._local_folder, filename))
                )

    def download_large_thumbnail_for_selection(self):
        for rng in self.selectedRanges():
            for row in range(rng.topRow(), rng.bottomRow() + 1):
                resource = self._camera_content_cache[row]
                url = resource["resources"]["CAM_LRGTN"]["res"].uri
                item = self.play_mode_widget._new_thumbnail_image_item(
                    url, priority=QNetworkRequest.Priority.HighPriority
                )
                self.setItem(row, 0, item)
                self.resizeRowToContents(row)

    def download_selection(self):

        def urlretrieve_reporthook(blocknum: int, bs: int, size: int):
            if (blocknum % 100) == 0:
                # Note: size is -1 since download is done in streaming mode
                logger.info(
                    "Downloading %s to %s: %0.3f MB / %0.3f ",
                    url,
                    local_filename,
                    (blocknum * bs / 1024 / 1024),
                    filesize / 1024 / 1024,
                )
                QApplication.sendEvent(
                    self,
                    QtGui.QStatusTipEvent(
                        f"Downloading {url} to {local_filename}:{blocknum*bs/1024}%"
                    ),
                )

        # logger.info("Downloading to %s", self.line_edit.text())
        for rng in self.selectedRanges():
            for row in range(rng.topRow(), rng.bottomRow() + 1):

                camera_content_item = self._camera_content_cache[row]
                # print(row, resource["OriginalFileName"])
                local_filenames = self.get_local_filenames(camera_content_item)
                for typ, local_filename in local_filenames.items():
                    url = camera_content_item["resources"][typ]["res"].uri
                    filesize = int(camera_content_item["resources"][typ]["res"].size)
                    if not os.path.isfile(local_filename):
                        QApplication.sendEvent(
                            self,
                            QtGui.QStatusTipEvent(
                                f"Downloading {url} to {local_filename}"
                            ),
                        )
                        logger.info("Downloading %s to %s", url, local_filename)
                        # TODO: download of urlretrieve is fast, but startup of first image takes half a minute
                        # Maybe download with Qt since it has already a connection open
                        urllib.request.urlretrieve(
                            url,
                            filename=local_filename,
                            reporthook=urlretrieve_reporthook,
                        )
                        urllib.request.urlcleanup()

                    self._downloaded_checkbox_map[row][
                        os.path.basename(local_filename)
                    ].setChecked(os.path.isfile(local_filename))

        logger.info("Download done")
        QApplication.sendEvent(self, QtGui.QStatusTipEvent("Downloading done"))

    def new_camera_content_list(self, camera_content_list: List[CameraContentItem]):

        self._camera_content_cache = {}
        self.clear()
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels(
            ["Thumbnail", "Sync", "Type", "Date", "Debuginfo"]
        )
        self.setRowCount(len(camera_content_list))

        for row, camera_content_item in enumerate(camera_content_list):
            if not isinstance(camera_content_item["didl_object"], didl_lite.Item):
                pprint.pprint("new_camera_content_list")
                pprint.pprint(camera_content_item)

            self._camera_content_cache[row] = camera_content_item
            try:
                if "CAM_TN" in camera_content_item:
                    thumbnail_uri = camera_content_item["CAM_TN"]
                else:
                    thumbnail_uri = camera_content_item["resources"]["CAM_TN"][
                        "res"
                    ].uri

                item = self.play_mode_widget._new_thumbnail_image_item(thumbnail_uri)
                self.setItem(row, 0, item)
                self.resizeRowToContents(row)
                self.resizeColumnToContents(0)
            except Exception:
                logger.error(
                    "error parsing camera_content_item %s", camera_content_item
                )
                pass

            local_filenames_dict = self.get_local_filenames(camera_content_item)

            check_box_layout = QHBoxLayout()
            check_box_map = {}
            for key, local_filename in local_filenames_dict.items():
                check_box = QReadOnlyCheckBox()
                check_box.setToolTip(f"{key} already on local computer?")
                if os.path.isfile(local_filename):
                    check_box.setCheckState(QtCore.Qt.CheckState.Checked)
                check_box_map[os.path.basename(local_filename)] = check_box
                check_box_layout.addWidget(check_box)
            self._downloaded_checkbox_map[row] = check_box_map
            check_box_widget = QWidget()
            check_box_widget.setLayout(check_box_layout)
            self.setCellWidget(row, 1, check_box_widget)
            self.resizeColumnToContents(1)

            description_item = QTableWidgetItem(
                str(type(camera_content_item["didl_object"]))
            )
            self.setItem(row, 2, description_item)
            self.resizeColumnToContents(2)

            try:
                date = camera_content_item["didl_object"].date
            except AttributeError:
                pass
            else:
                date_item = QTableWidgetItem(date)
                self.setItem(row, 3, date_item)
                self.resizeColumnToContents(3)

            description_item = QTableWidgetItem()
            description_item.setText(f"Resource {camera_content_item}")
            self.setItem(row, 4, description_item)
