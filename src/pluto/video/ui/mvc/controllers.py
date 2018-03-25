# -*- coding: utf-8 -*-

import os
import traceback

from PyQt5.QtCore import QDir, QUrl, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtWidgets import (QApplication, QFileDialog, QStyle, QMessageBox, QListWidgetItem)

from pluto.media.TextDetector import TextDetector
from pluto.utils import TimeUtil, ImageUtil, TempFileUtil
from pluto.video.snapshot import Snapshot
from pluto.video.ui.ListWidgetItem import ListWidgetItem
from pluto.video.ui.mvc.models import SnapshotModel, ImageModel
from pluto.video.ui.mvc.views import ImageStitchingWindow
from pluto.video.ui.qtutils import QtUtil


class MainController(object):
    def __init__(self, router, view=None):
        self.router = router
        self.view = view
        self.model = SnapshotModel()
        self.snapshot = Snapshot()

    def show(self):
        self.view.show()

    def set_view(self, view):
        self.view = view

    def on_open_file(self):
        file_name, _ = QFileDialog.getOpenFileName(self.view, "Open Video", QDir.homePath(),
                                                   filter="*.mp4;*.avi;*.mpeg;*.mpg;*.mov")
        if file_name != '':
            self.model = SnapshotModel()
            self.model.filename = file_name
            self.view.outputLineEdit.setText(self.model.output)
            self.view.mediaPlayer.setMedia(QMediaContent(QUrl.fromLocalFile(file_name)))
            self.view.playButton.setEnabled(True)
            self.view.snapshotButton.setEnabled(True)
            self.view.subtitleButton.setEnabled(True)
            self.view.startButton.setEnabled(True)
            self.view.endButton.setEnabled(True)
            self.view.outputButton.setEnabled(True)
            self.snapshot.load_video(file_name)
            if self.snapshot.srt_file:
                self.model.subtitle = self.snapshot.srt_file
                self.view.subTitleLabel.setText(self.snapshot.srt_file)
                self.view.runTaskButton.setEnabled(True)

    def on_set_output(self):
        folder = QFileDialog.getExistingDirectory(self.view, "Select image output path", self.model.output)
        if folder:
            self.model.output = folder
            self.view.outputLineEdit.setText(self.model.output)

    def on_set_subtitle(self):
        file_name, _ = QFileDialog.getOpenFileName(self.view, "Open Subtitle", QDir.homePath(),
                                                   filter="*.srt")
        if file_name != '':
            self.snapshot.load_srt(file_name)
            self.view.subTitleLabel.setText(file_name)
            self.model.subtitle = file_name
            self.view.runTaskButton.setEnabled(True)

    def on_play(self):
        if self.view.mediaPlayer.state() == QMediaPlayer.PlayingState:
            self.view.mediaPlayer.pause()
        else:
            self.view.mediaPlayer.play()
            height = self.view.frameGeometry().height() - 200
            self.view.videoWidget.setGeometry(10, 10, height * 1.778, height)

    def on_media_state_changed(self, state):
        if self.view.mediaPlayer.state() == QMediaPlayer.PlayingState:
            self.view.playButton.setIcon(
                self.view.style().standardIcon(QStyle.SP_MediaPause))
        else:
            self.view.playButton.setIcon(
                self.view.style().standardIcon(QStyle.SP_MediaPlay))

    def on_position_changed(self, position):
        self.view.positionSlider.setValue(position)
        self.view.statusLabel.setText("Progress: " + TimeUtil.format_ms(position))

    def on_duration_changed(self, duration):
        self.view.positionSlider.setRange(0, duration)
        self.model.end = duration
        self.view.endLabel.setText(TimeUtil.format_ms(duration))

    def on_set_position(self, position):
        self.view.mediaPlayer.setPosition(position)

    def on_handle_error(self, error):
        self.view.playButton.setEnabled(False)
        self.view.snapshotButton.setEnabled(False)
        self.view.startButton.setEnabled(False)
        self.view.endButton.setEnabled(False)
        self.view.outputButton.setEnabled(False)
        self.view.subtitleButton.setEnabled(False)
        self.view.runTaskButton(False)
        self.view.statusLabel.setText("Error: " + self.view.mediaPlayer.errorString())
        print(error)

    def on_snapshot(self):
        position = self.view.mediaPlayer.position()
        output_file = os.path.join(self.model.output, self.model.file + "_%d.jpg" % position)
        try:
            if self.snapshot.snapshot(position, output_file):
                self.router.notify('snapshot', output_file)
                self.view.statusLabel.setText("Saved " + output_file)
        except:
            traceback.print_exc()
            QMessageBox.warning(self.view, 'Error', 'Snapshot failed.')

    def on_set_start(self):
        self.model.start = self.view.mediaPlayer.position()
        self.view.startLabel.setText(TimeUtil.format_ms(self.model.start))

    def on_set_end(self):
        self.model.end = self.view.mediaPlayer.position()
        self.view.endLabel.setText(TimeUtil.format_ms(self.model.end))

    def on_run_snapshots(self):
        if self.view.mediaPlayer.state() == QMediaPlayer.PlayingState:
            self.on_play()

        count = self.snapshot.estimate(self.model.start, self.model.end)
        quit_msg = "Are you sure you want to run auto snapshot (start %s ~ end %s )?\n" \
                   "Image count estimation %s" % (TimeUtil.format_ms(self.model.start),
                                                  TimeUtil.format_ms(self.model.end), count)
        reply = QMessageBox.question(self.view, 'Run Auto Snapshort', quit_msg, QMessageBox.Yes,
                                     QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.lock_ui(False)
            self.model.task_progress = 0
            try:
                self.snapshot.snapshot_range(self.model.output, self.model.start, self.model.end,
                                             self.show_progress, self.show_complete)
            except:
                QMessageBox.warning(self.view, 'Error', 'Snapshot failed.')

            self.lock_ui(True)

    def show_progress(self, total, current, position, output_file, output_result):
        QApplication.processEvents()
        self.router.notify('snapshot', output_file)
        percentage = int(current * 100 / total)
        if percentage != self.model.task_progress:
            self.model.task_progress = percentage
            self.view.statusLabel.setText("Progress %s%%" % percentage)
        print("total=%s, current=%s, position=%s, output_file=%s, output_result=%s" % (
            total, current, position, output_file, output_result))

    def show_complete(self, total, success):
        self.view.statusLabel.setText("Progress 100%%, all done, %s files expected, %s files saved" % (total, success))

    def lock_ui(self, locked_status):
        self.view.playButton.setEnabled(locked_status)
        self.view.openButton.setEnabled(locked_status)
        self.view.outputButton.setEnabled(locked_status)
        self.view.subtitleButton.setEnabled(locked_status)
        self.view.snapshotButton.setEnabled(locked_status)
        self.view.startButton.setEnabled(locked_status)
        self.view.endButton.setEnabled(locked_status)
        self.view.runTaskButton.setEnabled(locked_status)
        self.view.positionSlider.setEnabled(locked_status)
        self.view.imageButton.setEnabled(locked_status)

    def on_stitch_snapshots(self):
        self.view.hide()
        self.router.go('image')


class ImageStitchingController(object):
    def __init__(self, router):
        self.router = router
        self.view = ImageStitchingWindow()
        self.current_image = None
        self.preview_image_file = None
        self.preview_mode = 0
        self.__bind(self.view)
        self.router.subscribe('snapshot', self)
        self.files = []
        self.text_detector = TextDetector()

    def __bind(self, view):
        view.goBackButton.clicked.connect(self.on_go_back)
        view.addButton.clicked.connect(self.on_add_item)
        view.autoDetectButton.clicked.connect(self.on_auto_detect)
        view.removeButton.clicked.connect(self.on_remove_item)
        view.saveButton.clicked.connect(self.on_save)
        view.imageListWidget.itemSelectionChanged.connect(self.on_item_selected)
        view.upVerticalSlider.sliderMoved.connect(self.on_up_moved)
        view.downVerticalSlider.sliderMoved.connect(self.on_down_moved)
        view.tabWidget.tabBarClicked.connect(self.on_tab_clicked)
        view.imageWidget.resizeEvent = self.on_item_preview_resize
        view.previewWidget.resizeEvent = self.on_output_preview_resize
        view.previewSelectedAction.triggered.connect(self.on_preview_selected)
        view.previewAllAction.triggered.connect(self.on_preview_all)
        view.saveSelectedAction.triggered.connect(self.on_save_selected)
        view.saveAllAction.triggered.connect(self.on_save_all)

    def show(self):
        self.view.show()
        if len(self.files) > 0:
            for image in self.files:
                self.add_image(image)
            self.files = []

    def notify(self, topic, message):
        if topic == 'snapshot':
            self.files.append(message)

    def on_go_back(self):
        self.view.hide()
        self.router.go('player')

    def on_add_item(self):
        file_names, _ = QFileDialog.getOpenFileNames(self.view, "Open Images", QDir.homePath(),
                                                     filter="*.jpg;*.jpeg;*.png")
        if file_names:
            for image in file_names:
                self.add_image(image)
            self.view.statusBar().showMessage("%s images added." % len(file_names))

    def on_remove_item(self):
        items = self.view.imageListWidget.selectedItems()
        result = QMessageBox.question(self.view, 'Run Auto Snapshort', 'Remove selected [%s] items?' % len(items),
                                      QMessageBox.Yes, QMessageBox.No)
        if result == QMessageBox.Yes:
            for item in items:
                index = self.view.imageListWidget.indexFromItem(item)
                self.view.imageListWidget.takeItem(index.row())
            self.view.imageListWidget.repaint()
            self.view.statusBar().showMessage('Removed %s images.' % len(items))
            if self.view.imageListWidget.count() == 0:
                self.view.saveButton.setEnabled(False)
                self.view.autoDetectButton.setEnabled(False)

    def add_image(self, image_file):
        try:
            image = ImageModel(image_file)
            item = ListWidgetItem()
            icon = QIcon()
            icon.addFile(image_file)
            item.setTextAlignment(1)
            item.setIcon(icon)
            item.setData(Qt.DisplayRole, str(image))
            item.setData(Qt.StatusTipRole, image_file)
            item.set_storage(image)
            self.view.imageListWidget.addItem(item)
            if not self.view.saveButton.isEnabled():
                self.view.saveButton.setEnabled(True)
                self.view.autoDetectButton.setEnabled(True)
        except:
            traceback.print_exc()

    def on_item_selected(self):
        items = self.view.imageListWidget.selectedItems()
        if len(items) == 0:
            self.view.upVerticalSlider.setValue(0)
            self.view.upVerticalSlider.setEnabled(False)
            self.view.downVerticalSlider.setEnabled(False)
            self.view.downVerticalSlider.setValue(0)
            self.view.imageLabel.hide()
            self.view.upImageLabel.hide()
            self.view.downImageLabel.hide()
            self.view.removeButton.setEnabled(False)
            self.current_image = None
            self.view.statusBar().showMessage('')
        else:
            item = items[0]
            image = item.get_storage()
            self.current_image = image
            self.view.upVerticalSlider.setRange(0, image.height)
            self.view.downVerticalSlider.setRange(0, image.height)
            self.view.upVerticalSlider.setValue(image.up)
            self.view.downVerticalSlider.setValue(image.height - image.down)

            self.render_preview()
            self.view.imageLabel.show()
            self.view.upImageLabel.show()
            self.view.downImageLabel.show()
            self.view.removeButton.setEnabled(True)
            self.view.upVerticalSlider.setEnabled(True)
            self.view.downVerticalSlider.setEnabled(True)
            self.view.statusBar().showMessage("%s images selected." % len(items))

    def render_preview(self):
        image = self.current_image
        if image is None:
            return
        QtUtil.preview_image(image.image_file, self.view.imageLabel, self.view.imageWidget)
        self.set_image_up_shade(image)
        self.set_image_down_shade(image)

    def set_image_up_shade(self, image):
        height = int(self.view.imageLabel.height() * (image.up * 1.0 / image.height))
        self.view.upImageLabel.setGeometry(self.view.imageLabel.x(), self.view.imageLabel.y(),
                                           self.view.imageLabel.width(),
                                           height)
        # print 'up x, y, width, height', self.view.upImageLabel.geometry()

    def set_image_down_shade(self, image):
        height = int(self.view.imageWidget.height() * ((image.height - image.down) * 1.0 / image.height))
        self.view.downImageLabel.setGeometry(self.view.imageLabel.x(),
                                             self.view.imageLabel.y() + self.view.imageLabel.height() - height,
                                             self.view.imageLabel.width(), height)
        # print 'down x, y, width, height', self.view.downImageLabel.geometry()

    def on_up_moved(self, position):
        updated = False
        for item in self.view.imageListWidget.selectedItems():
            image = item.get_storage()
            if position < image.down:
                image.up = position
                item.setData(0, str(image))
                if not updated:
                    updated = True
                    self.set_image_up_shade(image)

            else:
                self.view.upVerticalSlider.setValue(image.up)
                break

    def on_down_moved(self, position):
        updated = False
        for item in self.view.imageListWidget.selectedItems():
            image = item.get_storage()
            val = image.height - position
            if val > image.up:
                image.down = val
                item.setData(0, str(image))
                if not updated:
                    updated = True
                    self.set_image_down_shade(image)
            else:
                self.view.downVerticalSlider.setValue(image.height - image.down)
                break

    def on_save(self):
        filename, _ = QFileDialog.getSaveFileName(self.view, "Save Image", QDir.homePath(),
                                                  filter="*.jpg")
        if filename:
            images = self.get_images(self.preview_mode)
            ImageUtil.vertical_stitch(images, filename)
            self.view.statusBar().showMessage('Image %s saved.' % filename)
        else:
            self.view.statusBar().showMessage('Save cancelled.')

    def get_images(self, mode=0):
        images = []
        if mode == 0:
            for i in range(self.view.imageListWidget.count()):
                item = self.view.imageListWidget.item(i)
                images.append(item.get_storage())
        else:
            for item in self.view.imageListWidget.selectedItems():
                images.append(item.get_storage())

        return images

    def on_item_preview_resize(self, event):
        if self.current_image is not None:
            QtUtil.central(self.view.imageLabel, self.view.imageWidget,
                           self.current_image.width, self.current_image.height)
            self.set_image_up_shade(self.current_image)
            self.set_image_down_shade(self.current_image)

    def on_tab_clicked(self, index):
        is_preview = index == 1
        self.view.statusBar().showMessage("Preview image." if is_preview else '')
        if is_preview:
            self.render_stitching_preview()
        else:
            self.view.addButton.show()
            self.view.removeButton.show()
            self.view.autoDetectButton.show()

    def render_stitching_preview(self):
        images = self.get_images(self.preview_mode)
        if len(images) > 0:
            temp_file = TempFileUtil.get_temp_file(prefix="snapshot_preview_", suffix=".jpg")
            self.preview_image_file = ImageUtil.vertical_stitch(images, temp_file)
            QtUtil.preview_image(temp_file, self.view.previewLabel, self.view.previewWidget)
            os.remove(temp_file)
        else:
            self.preview_image_file = None
            self.view.previewLabel.clear()
        self.view.addButton.hide()
        self.view.removeButton.hide()
        self.view.autoDetectButton.hide()

    def on_output_preview_resize(self, event):
        if self.preview_image_file is not None:
            QtUtil.central(self.view.previewLabel, self.view.previewWidget,
                           self.preview_image_file.width, self.preview_image_file.height)

    def on_preview_selected(self):
        self.view.tabWidget.setCurrentIndex(1)
        self.preview_mode = 1
        self.on_tab_clicked(1)

    def on_preview_all(self):
        self.view.tabWidget.setCurrentIndex(1)
        self.preview_mode = 0
        self.on_tab_clicked(1)

    def on_save_selected(self):
        self.preview_mode = 1
        self.on_save()

    def on_save_all(self):
        self.preview_mode = 0
        self.on_save()

    def on_auto_detect(self):
        message = "Auto detect subtitle positions for "
        items = []
        skip_first = False
        if len(self.view.imageListWidget.selectedItems()) > 0:
            message += "selected images?"
            items = self.view.imageListWidget.selectedItems()
        else:
            message += "all images (except the head image)?"
            for i in range(self.view.imageListWidget.count()):
                items.append(self.view.imageListWidget.item(i))
            skip_first = True
        reply = QMessageBox.question(self.view, 'Auto detect', message, QMessageBox.Yes, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.view.setEnabled(False)
            self.do_auto_detect(items, skip_first)
            self.view.setEnabled(True)

    def do_auto_detect(self, items, skip_first=False):
        start = 1 if skip_first else 0
        for i in range(start, len(items)):
            img = items[i].get_storage()
            img.up, img.down = self.text_detector.detect_subtitle_range(img.image_file)
            #items[i].setData(0, str(img))
            self.refresh_item(items[i])

    def refresh_item(self, item):
        img = item.get_storage()
        item.setData(0, str(img))
        # thumbnail = ImageUtil.get_thumbnail(img)
        # item.setIcon(QIcon(thumbnail))
        # Remove temp file
        # os.remove(thumbnail)
