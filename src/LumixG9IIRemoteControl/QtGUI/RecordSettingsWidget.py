import pprint
import traceback
import xml.etree.ElementTree
from typing import Dict

from PySide6 import QtCore, QtGui
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import LumixG9IIRemoteControl.LumixG9IIRemoteControl


class RecordSettingsWidget(QTabWidget):

    requestCamCgiCall = Signal(dict)

    def __init__(
        self,
        g9ii: LumixG9IIRemoteControl.LumixG9IIRemoteControl.LumixG9IIRemoteControl,
        *args,
        **kwargs,
    ):
        self.g9ii: (
            LumixG9IIRemoteControl.LumixG9IIRemoteControl.LumixG9IIRemoteControl
        ) = g9ii
        self._allmenu_parent_map = {}
        self._id_map: Dict[str, QWidget] = {}
        super().__init__(*args, **kwargs)

    def _no_raise(func):
        def no_raise(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                traceback.print_exception(e)

        return no_raise

    @Slot(xml.etree.ElementTree.ElementTree)
    def apply_curmenu_xml(self, curmenu_tree: xml.etree.ElementTree.ElementTree):

        for item in curmenu_tree.findall(".//item"):
            if not item.attrib["id"] in self._id_map:
                print("missing", item.attrib["id"])
                continue

            # print(self._id_map[item.attrib["id"]], item.attrib["enable"])
            if item.attrib["enable"] == "yes":
                enabled = True
            elif item.attrib["enable"] == "no":
                enabled = False
            else:
                raise RuntimeError()

            if isinstance(self._id_map[item.attrib["id"]], tuple):
                combo_box: QComboBox = self._id_map[item.attrib["id"]][0]
                idx = self._id_map[item.attrib["id"]][1]
                model: QtGui.QStandardItemModel = combo_box.model()

                i = model.item(idx)
                item_flag = i.flags()
                if enabled:
                    item_flag = item_flag | Qt.ItemFlag.ItemIsSelectable
                    item_flag = item_flag | Qt.ItemFlag.ItemIsEnabled
                else:
                    item_flag = item_flag & ~Qt.ItemFlag.ItemIsSelectable
                    item_flag = item_flag & ~Qt.ItemFlag.ItemIsEnabled

                i.setFlags(item_flag)

                # print(self._id_map[item.attrib["id"]], item_flag)

            elif hasattr(self._id_map[item.attrib["id"]], "setEnabled"):
                self._id_map[item.attrib["id"]].setEnabled(enabled)
            else:
                print(self._id_map[item.attrib["id"]], item.attrib)

            if "value" in item.attrib:
                if isinstance(self._id_map[item.attrib["id"]], tuple):
                    combo_box: QComboBox = self._id_map[item.attrib["id"]][0]
                    idx = combo_box.findText(item.attrib["value"])
                    if idx == -1:
                        tmp = [combo_box.itemText(i) for i in range(combo_box.count())]
                        print(
                            f'Could not find value {item.attrib["value"]} in {item.attrib["id"]}, but {tmp}'
                        )
                    else:
                        # TODO: setCurrentIndex triggers callback, but here it should not
                        print(f'Setting {item.attrib["id"]} to  {item.attrib["value"]}')
                        combo_box.setCurrentIndex(idx)

            if "option" in item.attrib or "option2" in item.attrib:
                print("handle attribs", item.attrib)

    @Slot(xml.etree.ElementTree.ElementTree)
    def apply_allmenu_xml(self, allmenu_tree: xml.etree.ElementTree.ElementTree):

        self._allmenu_parent_map = {c: p for p in allmenu_tree.iter() for c in p}

        tab_names = allmenu_tree.find("menuset")
        for tab_name in tab_names:
            print(tab_name.tag)
            menu = tab_name.find("menu")
            if not menu:
                continue

            w = self._parse_menu(menu)
            if not w:
                continue

            scroll = QScrollArea()
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setWidgetResizable(True)
            scroll.setWidget(w)
            self.addTab(scroll, tab_name.tag)

        pprint.pprint(self._id_map)

    def _parse_menu(self, menu: xml.etree.ElementTree.Element) -> QWidget:

        items = menu.findall("./")
        if not items:
            return None

        layout = QVBoxLayout()
        for item in items:
            func_type = item.attrib.get("func_type", "")
            grouped_items = item.findall("group/")
            if grouped_items:

                if func_type == "select" or func_type.startswith("sp_embeded"):

                    combo_box = QComboBox()
                    self._id_map[item.attrib["id"]] = combo_box
                    model = combo_box.model()
                    for idx, grouped_item in enumerate(grouped_items):
                        combo_box.addItem(self._title_id(grouped_item.attrib))
                        print("adding", grouped_item.attrib["id"])
                        # model_index = model.index(idx,0)
                        # self._id_map[grouped_item.attrib['id']] = model.itemData(model_index)
                        self._id_map[grouped_item.attrib["id"]] = (combo_box, idx)
                    combo_box.setCurrentIndex(-1)
                    val2 = [grouped_item.attrib for grouped_item in grouped_items]
                    combo_box.currentIndexChanged.connect(
                        lambda x, val=val2: self.index_changed(val, x)
                    )

                    l = QHBoxLayout()
                    l.addWidget(QLabel(self._title_id(item.attrib)))
                    l.addWidget(combo_box)
                    layout.addLayout(l)

                else:
                    raise NotImplementedError(item.attrib)

            elif func_type == "submenu":
                self._id_map[item.attrib["id"]] = layout
                w = self._parse_menu(item.find("menu"))
                if w:
                    friendly_name = self.g9ii.get_localized_setting_name(
                        item.attrib["title_id"]
                    )
                    sub_menu_layout = QHBoxLayout()
                    sub_menu_layout.addWidget(QLabel(friendly_name))
                    sub_menu_layout.addWidget(w)
                    layout.addLayout(sub_menu_layout)
            else:
                friendly_name = self.g9ii.get_localized_setting_name(
                    item.attrib["title_id"]
                )

                if item.attrib.get("cmd_mode") == "setsetting":
                    if item.attrib.get("cmd_value") == "__value__":
                        line_edit = QLineEdit()
                        line_edit.setPlaceholderText("mlbel")
                        line_edit.returnPressed.connect(
                            lambda x=item.attrib, y=line_edit: self._cam_cgi_from_lineedit(
                                x, y
                            )
                        )
                        self._id_map[item.attrib["id"]] = line_edit

                        l = QHBoxLayout()
                        l.addWidget(QLabel(friendly_name))
                        l.addWidget(line_edit)
                        layout.addLayout(l)
                    else:
                        # TODO The baroque parent_map could possible replaced by an
                        # additional parameter parent_item to _parse_menu
                        if "title_id" in self._allmenu_parent_map[menu].attrib:
                            friendly_menu_name = self.g9ii.get_localized_setting_name(
                                self._allmenu_parent_map[menu].attrib["title_id"]
                            )
                            button = QPushButton(text=friendly_name)
                            button.pressed.connect(
                                lambda: self.g9ii._cam_cgi(item.attrib)
                            )
                            self._id_map[item.attrib["id"]] = button

                            l = QHBoxLayout()
                            l.addWidget(QLabel(friendly_menu_name))
                            l.addWidget(button)
                            layout.addLayout(l)
                        else:
                            label = QLabel(str(item.attrib))
                            self._id_map[item.attrib["id"]] = label
                            layout.addWidget(label)

                else:
                    label = QLabel(str(item.attrib))
                    self._id_map[item.attrib["id"]] = label
                    layout.addWidget(label)
            # print(m.attrib, )
        w = QWidget()
        w.setLayout(layout)
        return w

    @_no_raise
    def index_changed(self, val, i):
        print("cam_cgi_dict", val[i])
        try:
            ret = self.g9ii._run_camcgi_from_dict(val[i])
        except RuntimeError as e:
            traceback.print_exception(e)
        else:
            print(ret)

    @_no_raise
    def _title_id(self, d: dict) -> str:
        if "title_id" in d:
            string = self.g9ii.get_localized_setting_name(d["title_id"])
        else:
            string = str(d)
        return string

    @_no_raise
    def _cam_cgi_from_lineedit(self, d: dict, lineedit: QLineEdit):
        x = d.copy()
        x["cmd_value"] = lineedit.text()
        print("cam_cgi_dict", x)
        self.g9ii._run_camcgi_from_dict(x)
