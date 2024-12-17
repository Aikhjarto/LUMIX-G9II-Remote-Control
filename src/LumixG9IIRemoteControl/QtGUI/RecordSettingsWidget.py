import logging
import pprint
import traceback
import xml.etree.ElementTree
from typing import Dict, List, Literal, Tuple, Union

from qtpy import QtCore, QtGui
from qtpy.QtCore import Qt, Signal, Slot
from qtpy.QtWidgets import (
    QAbstractSlider,
    QAbstractSpinBox,
    QBoxLayout,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QGraphicsScene,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import LumixG9IIRemoteControl.LumixG9IIWiFiControl

from ..configure_logging import logger


class RecordSettingsWidget(QTabWidget):

    requestCamCgiCall = Signal(dict)

    def __init__(
        self,
        g9ii: LumixG9IIRemoteControl.LumixG9IIWiFiControl.LumixG9IIWiFiControl,
        *args,
        **kwargs,
    ):
        self.g9ii: LumixG9IIRemoteControl.LumixG9IIWiFiControl.LumixG9IIWiFiControl = (
            g9ii
        )
        self._allmenu_parent_map = {}
        self._id_map: Dict[
            str,
            Union[
                QLabel,
                QButtonGroup,
                QPushButton,
                QLineEdit,
                QCheckBox,
                QSpinBox,
                Tuple[QComboBox, int],
                Tuple[QRadioButton, int],
            ],
        ] = {}
        self._setsetting_map: Dict[
            str, Union[QComboBox, QLineEdit, QAbstractSlider, QCheckBox]
        ] = {}
        super().__init__(*args, **kwargs)

    def _no_raise(func):
        def no_raise(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.exception(e)

        return no_raise

    @Slot(xml.etree.ElementTree.ElementTree)
    def apply_curmenu_xml(
        self, curmenu_tree: xml.etree.ElementTree.ElementTree, adhere_enabeled=False
    ):
        # TODO: setting curmenu triggeres change signals
        # each change signal triggers setsetting command, which triggers curmenu.
        # Thus it requires a long time to settle
        for item in curmenu_tree.findall(".//item"):

            if item.attrib["id"].startswith("menu_item_id_recmode"):
                # 'enabled' indicated which mode is currently set and not
                # which mode is currently available
                continue

            if item.attrib.get("cmd_type") == "drivemode":
                # drive mode seems to be never enabled via curmenu
                # thus also never disable it
                continue

            instance = self._id_map.get(item.attrib["id"])
            if not instance:
                logger.debug(
                    "Cannot find %s in self._id_map. "
                    "Most likely an entry in curmenu was not in allmenu",
                    item.attrib["id"],
                )
                continue

            if item.attrib["enable"] == "yes":
                enabled = True
            elif item.attrib["enable"] == "no":
                enabled = False
            else:
                logger.error(
                    f"Field enabled of {item.attrib} must either be 'yes' or 'no'."
                )
                continue

            if isinstance(instance, tuple):
                if hasattr(instance[0], "setEnabled"):
                    if adhere_enabeled:
                        instance[0].blockSignals(True)
                        instance[0].setEnabled(enabled)
                        instance[0].blockSignals(False)

                if isinstance(instance[0], QComboBox):
                    combo_box = instance[0]
                    idx = instance[1]
                    model: QtGui.QStandardItemModel = combo_box.model()

                    if i := model.item(idx):
                        item_flag = i.flags()
                        if enabled:
                            item_flag = item_flag | Qt.ItemFlag.ItemIsSelectable
                            item_flag = item_flag | Qt.ItemFlag.ItemIsEnabled
                        else:
                            item_flag = item_flag & ~Qt.ItemFlag.ItemIsSelectable
                            item_flag = item_flag & ~Qt.ItemFlag.ItemIsEnabled

                        # print(instance, item_flag)
                        i.setFlags(item_flag)
                    else:
                        logger.error(
                            "Combobox %s has no item at index %s",
                            item.attrib["id"],
                            idx,
                        )

                else:
                    raise NotImplementedError((instance, item.attrib))

            else:
                if hasattr(instance, "setEnabled"):
                    if adhere_enabeled:
                        instance.blockSignals(True)
                        instance.setEnabled(enabled)
                        instance.blockSignals(False)

                value = item.attrib.get("value")
                if value:
                    if isinstance(instance, QAbstractSlider) or isinstance(
                        instance, QAbstractSpinBox
                    ):
                        instance.blockSignals(True)
                        instance.setValue(int(value))
                        instance.blockSignals(False)

                    elif isinstance(instance, QLineEdit):
                        instance.blockSignals(True)
                        instance.setText(value)
                        instance.blockSignals(False)

                    elif isinstance(instance, QCheckBox):
                        if item.attrib["id"] == "menu_item_id_interval_expo_leveling":
                            continue
                        checked = None
                        if value == "on":
                            checked = True
                        elif value == "off":
                            checked = False

                        if checked is None:
                            logger.error(
                                "Unknown value %s for checkbox for item %s",
                                value,
                                item.attrib,
                            )
                        else:
                            instance.blockSignals(True)
                            instance.setChecked(checked)
                            instance.blockSignals(False)

                    elif isinstance(instance, QComboBox):
                        user_data = item.attrib["value"]
                        if "value2" in item.attrib:
                            user_data = user_data + "," + item.attrib["value2"]

                        idx = instance.findData(user_data)
                        if idx == -1:
                            tmp = [
                                instance.itemData(i) for i in range(instance.count())
                            ]
                            logger.error(
                                "Could not find curmenu value %s in %s, but %s ",
                                item.attrib["value"],
                                item.attrib["id"],
                                tmp,
                            )
                        else:
                            logger.debug(
                                f'Setting {item.attrib["id"]} to {item.attrib["value"]}'
                            )
                            instance.blockSignals(True)
                            instance.setCurrentIndex(idx)
                            instance.blockSignals(False)
                    else:
                        logger.error(
                            f"Curmenu item NotImplementedError({(instance, item.attrib)}"
                        )

            s = set(item.attrib.keys())
            s.remove("id")
            s.remove("enable")
            if "value" in s:
                s.remove("value")
            if len(s) > 0:  # "option", "option2", or "active" in item.attrib:
                logger.error("handle curmenu attribs %s", item.attrib)

    @Slot(xml.etree.ElementTree.ElementTree)
    def apply_allmenu_xml(self, allmenu_tree: xml.etree.ElementTree.ElementTree):
        if self.count() > 1:
            # ignore when already initialized
            return

        self._allmenu_parent_map = {c: p for p in allmenu_tree.iter() for c in p}

        tab_names = allmenu_tree.find("menuset")
        for tab_name in tab_names:

            if tab_name.tag == "record_qmenu":
                # TODO: skip Q-menu for now since it would require double entries in self._id_map
                continue
            logger.debug(tab_name.tag)
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

        # pprint.pprint(self._id_map)

    def _add_select_item(self, item: xml.etree.ElementTree.Element, layout: QBoxLayout):
        grouped_items = item.findall("group/")
        combo_box = QComboBox()
        self._id_map[item.attrib["id"]] = combo_box
        for idx, grouped_item in enumerate(grouped_items):
            if (
                "min_val" in grouped_item.attrib
                or "max_val" in grouped_item.attrib
                or "step_val" in grouped_item.attrib
            ):
                logger.error(
                    "Notimplemented: %s appeared in select group %s",
                    grouped_item.attrib,
                    item.attrib,
                )
                continue

            user_data = grouped_item.attrib["cmd_value"]
            if "cmd_value2" in grouped_item.attrib:
                if grouped_item.attrib["cmd_type"] == "drivemode":
                    user_data = grouped_item.attrib["cmd_value2"]
                else:
                    user_data = user_data + "," + grouped_item.attrib["cmd_value2"]

            combo_box.addItem(
                self._title_id(grouped_item.attrib),
                userData=user_data,
            )
            logger.debug("adding", grouped_item.attrib["id"])
            # model_index = model.index(idx,0)
            # self._id_map[grouped_item.attrib['id']] = model.itemData(model_index)
            if grouped_item.attrib["id"] in self._id_map:
                logger.error(
                    f'Duplicate entry {grouped_item.attrib["cmd_type"]} in _id_map'
                )

            self._id_map[grouped_item.attrib["id"]] = (combo_box, idx)
            if grouped_item.attrib["cmd_mode"] == "setsetting":
                if grouped_item.attrib["cmd_type"] not in self._setsetting_map:
                    self._setsetting_map[grouped_item.attrib["cmd_type"]] = combo_box

        combo_box.setCurrentIndex(-1)
        val2 = [grouped_item.attrib for grouped_item in grouped_items]
        combo_box.currentIndexChanged.connect(
            lambda x, val=val2: self._cam_cgi_from_combobox(val, x)
        )

        sub_layout = QHBoxLayout()
        sub_layout.addWidget(QLabel(self._title_id(item.attrib)))
        sub_layout.addWidget(combo_box)
        layout.addLayout(sub_layout)

    def _add_item(self, item: xml.etree.ElementTree.Element, layout: QBoxLayout, menu):
        func_type = item.attrib.get("func_type", "")

        friendly_name = self.g9ii.get_localized_setting_name(item.attrib["title_id"])
        if func_type == "select":
            self._add_select_item(item, layout)
        elif item.attrib.get("cmd_mode") == "setsetting":
            if func_type == "on_off":
                check_box = QCheckBox()
                check_box.setText(friendly_name)
                check_box.checkStateChanged.connect(
                    lambda state, x=item.attrib, y=check_box: self._cam_cgi_from_checkbox(
                        state, x, y
                    )
                )
                self._id_map[item.attrib["id"]] = check_box
                if item.attrib.get("cmd_type") not in self._setsetting_map:
                    self._setsetting_map[item.attrib.get("cmd_type")] = check_box
                layout.addWidget(check_box)

            elif "min_val" in item.attrib:
                # TODO: menu_item_id_whitebalance_color_temp4 is inside a func_type select, thus check for min_val here does not hit

                # TODO: https://doc.qt.io/qt-5/qspinbox.html
                slider = QSpinBox()
                slider.setMinimum(int(item.attrib["min_val"]))
                slider.setMaximum(int(item.attrib["max_val"]))
                slider.setSingleStep(int(item.attrib["step_val"]))
                # TODO tick markers
                slider.valueChanged.connect(
                    lambda value, x=item.attrib: self._cam_cgi_from_slider(value, x)
                )

                self._id_map[item.attrib["id"]] = slider
                if item.attrib.get("cmd_type") not in self._setsetting_map:
                    self._setsetting_map[item.attrib.get("cmd_type")] = slider

                sub_layout = QHBoxLayout()
                sub_layout.addWidget(QLabel(friendly_name))
                sub_layout.addWidget(QLabel(item.attrib["min_val"]))
                sub_layout.addWidget(slider)
                sub_layout.addWidget(QLabel(item.attrib["max_val"]))
                layout.addLayout(sub_layout)

            elif (
                item.attrib.get("cmd_value") == "__value__"
                or item.attrib.get("cmd_value2") == "__value__"
            ):
                line_edit = QLineEdit()
                line_edit.returnPressed.connect(
                    lambda x=item.attrib, y=line_edit: self._cam_cgi_from_lineedit(x, y)
                )
                self._id_map[item.attrib["id"]] = line_edit
                if item.attrib.get("cmd_type") not in self._setsetting_map:
                    self._setsetting_map[item.attrib.get("cmd_type")] = line_edit

                sub_layout = QHBoxLayout()
                sub_layout.addWidget(QLabel(friendly_name))
                sub_layout.addWidget(line_edit)
                layout.addLayout(sub_layout)
            else:

                # TODO The baroque parent_map could possible replaced by an
                # additional parameter parent_item to _parse_menu

                button = QPushButton(text=friendly_name)
                button.pressed.connect(
                    lambda: self.g9ii.run_camcgi_from_dict(item.attrib)
                )
                self._id_map[item.attrib["id"]] = button

                if "title_id" in self._allmenu_parent_map[menu].attrib:
                    friendly_menu_name = self.g9ii.get_localized_setting_name(
                        self._allmenu_parent_map[menu].attrib["title_id"]
                    )
                    sub_layout = QHBoxLayout()
                    sub_layout.addWidget(QLabel(friendly_menu_name))
                    sub_layout.addWidget(button)
                    layout.addLayout(sub_layout)
                else:
                    layout.addWidget(button)

        elif func_type.startswith("sp_embeded_"):
            # sp_embeded_*
            #  * can have no children,
            #  * an empty group as child or a group with items as children
            # logger.info("func_type %s: %s, %s", func_type, len(item.findall("group/")), len(item.findall("group//")))

            direct_group_children = item.findall("group")
            nested_group_children = item.findall("./group//group")
            logger.debug(
                "func_type %s: %s, %s",
                func_type,
                len(direct_group_children),
                len(nested_group_children),
            )

            if len(direct_group_children) == 0:
                return
            elif len(direct_group_children) == 1:
                if len(nested_group_children) > 0:
                    group = direct_group_children[0]
                    sub_layout = QHBoxLayout()
                    # self._id_map[item.attrib["id"]] = sub_layout
                    # sub_layout.addWidget(QLabel(friendly_name))
                    logger.debug("Items of %s: %s", func_type, group)
                    sub_sub_layout = QVBoxLayout()
                    for sub_item in group.findall("item"):
                        self._add_item(sub_item, sub_sub_layout, menu)
                    sub_layout.addLayout(sub_sub_layout)

                    group_box = QGroupBox(friendly_name)
                    self._id_map[item.attrib["id"]] = group_box
                    group_box.setLayout(sub_layout)
                    layout.addWidget(group_box)
                else:
                    self._add_select_item(item, layout)
            else:
                raise NotImplementedError(len(direct_group_children))

        elif func_type == "submenu":
            self._id_map[item.attrib["id"]] = layout
            w = self._parse_menu(item.find("menu"))
            if w:
                group_box = QGroupBox(friendly_name)
                sub_menu_layout = QHBoxLayout()
                sub_menu_layout.addWidget(w)
                group_box.setLayout(sub_menu_layout)
                layout.addWidget(group_box)
        else:
            logger.error("Handle me" + str(item.attrib))
            label = QLabel("Handle me" + str(item.attrib))
            self._id_map[item.attrib["id"]] = label
            layout.addWidget(label)

    def _parse_menu(self, menu: xml.etree.ElementTree.Element) -> QWidget:

        items = menu.findall("./")
        if not items:
            return None

        layout = QVBoxLayout()
        for item in items:
            self._add_item(item, layout, menu)

            # print(m.attrib, )
        w = QWidget()
        w.setLayout(layout)
        return w

    @Slot(list)
    def apply_current_settings(
        self, data: List[Dict[Literal["type", "value", "value2"], str]]
    ):
        for item in data:
            if item["type"] in self._setsetting_map:
                widget = self._setsetting_map[item["type"]]
                if isinstance(widget, QComboBox):
                    user_data = item["value"]
                    if "value2" in item and item["type"] != "drivemode":
                        user_data = user_data + "," + item["value2"]

                    index = widget.findData(user_data)
                    if index == -1:
                        tmp = [widget.itemData(i) for i in range(widget.count())]
                        logger.error(
                            "Could not find setsetting value %s in %s, but %s ",
                            user_data,
                            item["type"],
                            tmp,
                        )
                    else:
                        widget.blockSignals(True)
                        widget.setCurrentIndex(index)
                        widget.blockSignals(False)

                elif isinstance(widget, QLineEdit):
                    widget.setText(item["value"])
                elif isinstance(widget, QAbstractSlider) or isinstance(
                    widget, QAbstractSpinBox
                ):
                    widget.setValue(int(item["value"]))
                elif isinstance(widget, QCheckBox):
                    if item["value"] == "on":
                        widget.setChecked(True)
                    elif item["value"] == "off":
                        widget.setChecked(True)
                    else:
                        raise RuntimeError(
                            f'Either "on" or "off" expected for {item} but got {item["value"]}'
                        )

                else:
                    logger.error("ERRROR")
            else:
                logger.error(f"{item}, not in _setsetting_map")

    @_no_raise
    def _cam_cgi_from_combobox(self, val, i):
        try:
            self.g9ii.run_camcgi_from_dict(val[i])
        except RuntimeError as e:
            logger.exception(e)

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
        if x["cmd_value"] == "__value__":
            x["cmd_value"] = lineedit.text()
        if x.get("cmd_value2") == "__value__":
            x["cmd_value2"] = lineedit.text()
        self.g9ii.run_camcgi_from_dict(x)

    @_no_raise
    def _cam_cgi_from_checkbox(self, state, d: dict, check_box: QCheckBox):
        if check_box.isChecked():
            value = "on"
        else:
            value = "off"
        x = d.copy()
        if x["cmd_value"] == "__value__":
            x["cmd_value"] = value
        if x.get("cmd_value2") == "__value__":
            x["cmd_value2"] = value

        self.g9ii.run_camcgi_from_dict(x)

    @_no_raise
    def _cam_cgi_from_slider(self, value, d: dict):
        x = d.copy()
        if x["cmd_value"] == "__value__":
            x["cmd_value"] = value
        if x.get("cmd_value2") == "__value__":
            x["cmd_value2"] = value
        self.g9ii.run_camcgi_from_dict(x)
