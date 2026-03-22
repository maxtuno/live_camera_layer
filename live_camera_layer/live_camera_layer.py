import os

from krita import DockWidget, DockWidgetFactory, DockWidgetFactoryBase, Krita
from PyQt5.QtCore import QPointF, QRectF, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QColor, QImage, QPainter, QPen, QTransform
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


class CropPreviewWidget(QWidget):
    cropChanged = pyqtSignal(int, int, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image = None
        self._crop_enabled = False
        self._crop_rect = (0, 0, 100, 100)
        self._drag_origin = None
        self._drag_current = None
        self.setMinimumHeight(180)

    def minimumSizeHint(self):
        return QSize(240, 180)

    def set_image(self, image):
        self._image = image
        self.update()

    def set_crop_enabled(self, enabled):
        self._crop_enabled = bool(enabled)
        self.update()

    def set_crop_rect(self, x, y, width, height):
        self._crop_rect = (x, y, width, height)
        self.update()

    def _image_rect(self):
        content = self.rect().adjusted(6, 6, -6, -6)
        if (
            self._image is None
            or self._image.isNull()
            or content.width() <= 0
            or content.height() <= 0
        ):
            return QRectF()

        scaled = self._image.size().scaled(content.size(), Qt.KeepAspectRatio)
        x = content.x() + (content.width() - scaled.width()) / 2.0
        y = content.y() + (content.height() - scaled.height()) / 2.0
        return QRectF(x, y, float(scaled.width()), float(scaled.height()))

    def _clamp_point_to_image(self, point, image_rect):
        x = min(max(point.x(), image_rect.left()), image_rect.right())
        y = min(max(point.y(), image_rect.top()), image_rect.bottom())
        return QPointF(x, y)

    def _selection_rect_from_points(self, image_rect, first_point, second_point):
        if first_point is None or second_point is None or image_rect.isEmpty():
            return QRectF()

        first = self._clamp_point_to_image(first_point, image_rect)
        second = self._clamp_point_to_image(second_point, image_rect)

        left = min(first.x(), second.x())
        top = min(first.y(), second.y())
        right = max(first.x(), second.x())
        bottom = max(first.y(), second.y())

        rect = QRectF(left, top, max(0.0, right - left), max(0.0, bottom - top))
        return rect.intersected(image_rect)

    def _current_selection_rect(self, image_rect):
        if self._drag_origin is not None and self._drag_current is not None:
            return self._selection_rect_from_points(
                image_rect, self._drag_origin, self._drag_current
            )

        if not self._crop_enabled or image_rect.isEmpty():
            return QRectF()

        x, y, width, height = self._crop_rect
        left = image_rect.left() + (image_rect.width() * x / 100.0)
        top = image_rect.top() + (image_rect.height() * y / 100.0)
        rect_width = image_rect.width() * width / 100.0
        rect_height = image_rect.height() * height / 100.0
        return QRectF(left, top, rect_width, rect_height).intersected(image_rect)

    def _paint_selection_overlay(self, painter, image_rect, selection_rect):
        if selection_rect.isEmpty():
            return

        shade = QColor(0, 0, 0, 110)
        top_height = max(0.0, selection_rect.top() - image_rect.top())
        bottom_height = max(0.0, image_rect.bottom() - selection_rect.bottom())
        left_width = max(0.0, selection_rect.left() - image_rect.left())
        right_width = max(0.0, image_rect.right() - selection_rect.right())

        painter.fillRect(
            QRectF(image_rect.left(), image_rect.top(), image_rect.width(), top_height),
            shade,
        )
        painter.fillRect(
            QRectF(
                image_rect.left(),
                selection_rect.bottom(),
                image_rect.width(),
                bottom_height,
            ),
            shade,
        )
        painter.fillRect(
            QRectF(
                image_rect.left(),
                selection_rect.top(),
                left_width,
                selection_rect.height(),
            ),
            shade,
        )
        painter.fillRect(
            QRectF(
                selection_rect.right(),
                selection_rect.top(),
                right_width,
                selection_rect.height(),
            ),
            shade,
        )

        painter.setPen(QPen(QColor(0, 200, 255), 2))
        painter.drawRect(selection_rect)

    def _normalized_crop_from_rect(self, rect, image_rect):
        if rect.isEmpty() or image_rect.isEmpty():
            return None

        x = int(round(((rect.left() - image_rect.left()) / image_rect.width()) * 100.0))
        y = int(round(((rect.top() - image_rect.top()) / image_rect.height()) * 100.0))
        width = int(round((rect.width() / image_rect.width()) * 100.0))
        height = int(round((rect.height() / image_rect.height()) * 100.0))

        width = max(1, width)
        height = max(1, height)
        x = max(0, min(99, x))
        y = max(0, min(99, y))
        width = min(width, 100 - x)
        height = min(height, 100 - y)

        return x, y, width, height

    def paintEvent(self, event):
        _ = event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(26, 26, 26))

        content = self.rect().adjusted(6, 6, -6, -6)
        painter.fillRect(content, QColor(42, 42, 42))
        painter.setPen(QPen(QColor(70, 70, 70), 1))
        painter.drawRect(content)

        image_rect = self._image_rect()
        if self._image is None or self._image.isNull() or image_rect.isEmpty():
            painter.setPen(QColor(185, 185, 185))
            painter.drawText(content, Qt.AlignCenter, "No frame yet")
            return

        painter.drawImage(image_rect, self._image)
        painter.setPen(QPen(QColor(225, 225, 225), 1))
        painter.drawRect(image_rect)

        selection_rect = self._current_selection_rect(image_rect)
        self._paint_selection_overlay(painter, image_rect, selection_rect)

    def mousePressEvent(self, event):
        image_rect = self._image_rect()
        if (
            event.button() != Qt.LeftButton
            or image_rect.isEmpty()
            or not image_rect.contains(event.localPos())
        ):
            super().mousePressEvent(event)
            return

        self._drag_origin = self._clamp_point_to_image(event.localPos(), image_rect)
        self._drag_current = self._drag_origin
        self.update()
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_origin is None:
            super().mouseMoveEvent(event)
            return

        image_rect = self._image_rect()
        self._drag_current = self._clamp_point_to_image(event.localPos(), image_rect)
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag_origin is None:
            super().mouseReleaseEvent(event)
            return

        image_rect = self._image_rect()
        self._drag_current = self._clamp_point_to_image(event.localPos(), image_rect)
        selection_rect = self._selection_rect_from_points(
            image_rect, self._drag_origin, self._drag_current
        )

        self._drag_origin = None
        self._drag_current = None

        if selection_rect.width() >= 8 and selection_rect.height() >= 8:
            crop_rect = self._normalized_crop_from_rect(selection_rect, image_rect)
            if crop_rect is not None:
                self.cropChanged.emit(*crop_rect)

        self.update()
        event.accept()


class LiveCameraLayerDocker(DockWidget):
    SOURCE_HTTP = 0
    SOURCE_FILE = 1

    STATUS_OK = "OK"
    STATUS_TIMEOUT = "Timeout"
    STATUS_DISCONNECTED = "Disconnected"
    STATUS_STOPPED = "Stopped"

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Live Camera Layer")

        self._running = False
        self._active_document = None
        self._layer_node = None
        self._last_source_image = None

        self._network_manager = QNetworkAccessManager(self)
        self._pending_reply = None
        self._reply_timeout_timer = None
        self._reply_buffer = bytearray()
        self._reply_had_frame = False
        self._reply_timed_out = False

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self._on_tick)

        self._build_ui()
        self._setup_notifier()
        self._set_status(self.STATUS_STOPPED)

    def _build_ui(self):
        root = QWidget(self)
        layout = QVBoxLayout(root)

        source_label = QLabel("Source type")
        self.source_combo = QComboBox()
        self.source_combo.addItem("HTTP snapshot URL")
        self.source_combo.addItem("Local file path")
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        layout.addWidget(source_label)
        layout.addWidget(self.source_combo)

        self.input_stack = QStackedWidget()
        self.input_stack.addWidget(self._build_http_input())
        self.input_stack.addWidget(self._build_file_input())
        layout.addWidget(self.input_stack)

        layer_name_label = QLabel("Create/Use layer name")
        self.layer_name_edit = QLineEdit("LiveCam")
        layout.addWidget(layer_name_label)
        layout.addWidget(self.layer_name_edit)

        self.fit_to_canvas_checkbox = QCheckBox("Fit to canvas")
        self.fit_to_canvas_checkbox.setChecked(True)
        self.fit_to_canvas_checkbox.toggled.connect(self._on_render_option_changed)
        layout.addWidget(self.fit_to_canvas_checkbox)

        rotate_row = QHBoxLayout()
        rotate_row.addWidget(QLabel("Rotate"))
        self.rotate_combo = QComboBox()
        self.rotate_combo.addItem("0 deg", 0)
        self.rotate_combo.addItem("90 deg", 90)
        self.rotate_combo.addItem("180 deg", 180)
        self.rotate_combo.addItem("270 deg", 270)
        self.rotate_combo.currentIndexChanged.connect(self._on_render_option_changed)
        rotate_row.addWidget(self.rotate_combo)
        layout.addLayout(rotate_row)

        flip_row = QHBoxLayout()
        self.flip_horizontal_checkbox = QCheckBox("Flip horizontal")
        self.flip_vertical_checkbox = QCheckBox("Flip vertical")
        self.flip_horizontal_checkbox.toggled.connect(self._on_render_option_changed)
        self.flip_vertical_checkbox.toggled.connect(self._on_render_option_changed)
        flip_row.addWidget(self.flip_horizontal_checkbox)
        flip_row.addWidget(self.flip_vertical_checkbox)
        layout.addLayout(flip_row)

        self._build_crop_ui(layout)

        fps_row = QHBoxLayout()
        fps_row.addWidget(QLabel("FPS"))
        self.fps_slider = QSlider(Qt.Horizontal)
        self.fps_slider.setRange(1, 30)
        self.fps_slider.setValue(10)
        self.fps_slider.valueChanged.connect(self._on_fps_changed)
        fps_row.addWidget(self.fps_slider)
        self.fps_value_label = QLabel("10")
        fps_row.addWidget(self.fps_value_label)
        layout.addLayout(fps_row)

        self.start_stop_button = QPushButton("Start")
        self.start_stop_button.clicked.connect(self._on_start_stop_clicked)
        layout.addWidget(self.start_stop_button)

        self.status_label = QLabel("Status: {}".format(self.STATUS_STOPPED))
        layout.addWidget(self.status_label)

        layout.addStretch(1)

        self.setWidget(root)
        self._on_source_changed(self.source_combo.currentIndex())

    def _build_http_input(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("URL"))
        self.url_edit = QLineEdit("http://127.0.0.1:8080/shot.jpg")
        layout.addWidget(self.url_edit)
        return page

    def _build_file_input(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("File"))
        row = QHBoxLayout()
        self.file_edit = QLineEdit("")
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._on_browse_file)
        row.addWidget(self.file_edit)
        row.addWidget(browse_button)
        layout.addLayout(row)
        return page

    def _build_crop_ui(self, parent_layout):
        crop_toggle_row = QHBoxLayout()
        self.crop_checkbox = QCheckBox("Crop source")
        self.crop_checkbox.toggled.connect(self._on_crop_toggled)
        crop_toggle_row.addWidget(self.crop_checkbox)
        crop_toggle_row.addStretch(1)

        self.reset_crop_button = QPushButton("Reset")
        self.reset_crop_button.clicked.connect(self._on_reset_crop)
        crop_toggle_row.addWidget(self.reset_crop_button)
        parent_layout.addLayout(crop_toggle_row)

        crop_hint = QLabel("Drag in the preview to keep only that area.")
        crop_hint.setWordWrap(True)
        parent_layout.addWidget(crop_hint)

        self.crop_preview = CropPreviewWidget(self)
        self.crop_preview.cropChanged.connect(self._on_crop_preview_changed)
        parent_layout.addWidget(self.crop_preview)

        crop_grid = QGridLayout()
        crop_grid.addWidget(QLabel("X"), 0, 0)
        self.crop_x_spinbox = self._create_crop_spinbox(0, 99, 0)
        crop_grid.addWidget(self.crop_x_spinbox, 0, 1)

        crop_grid.addWidget(QLabel("Y"), 0, 2)
        self.crop_y_spinbox = self._create_crop_spinbox(0, 99, 0)
        crop_grid.addWidget(self.crop_y_spinbox, 0, 3)

        crop_grid.addWidget(QLabel("Width"), 1, 0)
        self.crop_width_spinbox = self._create_crop_spinbox(1, 100, 100)
        crop_grid.addWidget(self.crop_width_spinbox, 1, 1)

        crop_grid.addWidget(QLabel("Height"), 1, 2)
        self.crop_height_spinbox = self._create_crop_spinbox(1, 100, 100)
        crop_grid.addWidget(self.crop_height_spinbox, 1, 3)
        parent_layout.addLayout(crop_grid)

        self._set_crop_values(0, 0, 100, 100)
        self._set_crop_controls_enabled(False)
        self._update_crop_preview()

    def _create_crop_spinbox(self, minimum, maximum, value):
        spinbox = QSpinBox()
        spinbox.setRange(minimum, maximum)
        spinbox.setSuffix("%")
        spinbox.setValue(value)
        spinbox.valueChanged.connect(self._on_crop_value_changed)
        return spinbox

    def _setup_notifier(self):
        self._notifier = Krita.instance().notifier()
        if not self._notifier:
            return
        self._notifier.setActive(True)
        for signal_name in ("applicationClosing", "imageClosed", "viewClosed"):
            signal = getattr(self._notifier, signal_name, None)
            if signal is not None:
                signal.connect(self._on_external_close)

    def canvasChanged(self, canvas):
        if self._running and Krita.instance().activeDocument() is None:
            self.stop_streaming(self.STATUS_STOPPED)

    def _on_external_close(self, *args):
        if self._running:
            self.stop_streaming(self.STATUS_STOPPED)

    def _on_source_changed(self, index):
        self.input_stack.setCurrentIndex(index)

    def _on_browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select image file",
            "",
            "Images (*.jpg *.jpeg *.png *.bmp *.webp);;All files (*.*)",
        )
        if path:
            self.file_edit.setText(path)

    def _on_fps_changed(self, value):
        self.fps_value_label.setText(str(value))
        if self._running:
            self._timer.start(self._interval_ms())

    def _on_render_option_changed(self, *args):
        _ = args

        if self._last_source_image is None or self._last_source_image.isNull():
            self._update_crop_preview()
            return

        if self._running:
            if self._render_cached_frame():
                self._set_status(self.STATUS_OK)
            return

        self._prepare_display_image()

    def _on_crop_toggled(self, checked):
        self._set_crop_controls_enabled(checked)
        self._update_crop_preview()
        self._on_render_option_changed()

    def _on_crop_value_changed(self, *args):
        _ = args
        self._normalize_crop_controls()
        self._update_crop_preview()
        self._on_render_option_changed()

    def _on_crop_preview_changed(self, x, y, width, height):
        self._set_crop_values(x, y, width, height)
        if not self.crop_checkbox.isChecked():
            self.crop_checkbox.setChecked(True)
            return
        self._update_crop_preview()
        self._on_render_option_changed()

    def _on_reset_crop(self):
        self._set_crop_values(0, 0, 100, 100)
        if self.crop_checkbox.isChecked():
            self.crop_checkbox.setChecked(False)
            return
        self._update_crop_preview()
        self._on_render_option_changed()

    def _on_start_stop_clicked(self):
        if self._running:
            self.stop_streaming(self.STATUS_STOPPED)
        else:
            self.start_streaming()

    def start_streaming(self):
        doc = Krita.instance().activeDocument()
        if doc is None:
            self._set_status(self.STATUS_DISCONNECTED, "No active document")
            return

        layer_name = self.layer_name_edit.text().strip() or "LiveCam"
        layer = self._ensure_layer(doc, layer_name)
        if layer is None:
            self._set_status(self.STATUS_DISCONNECTED, "Cannot create layer")
            return

        self._active_document = doc
        self._layer_node = layer
        self._layer_node.setVisible(True)

        self._running = True
        self.start_stop_button.setText("Stop")
        self._timer.start(self._interval_ms())
        self._on_tick()

    def stop_streaming(self, status=STATUS_STOPPED):
        self._running = False
        self.start_stop_button.setText("Start")
        self._timer.stop()
        self._cancel_pending_reply()
        self._set_status(status)

    def _interval_ms(self):
        fps = max(1, self.fps_slider.value())
        return int(1000 / fps)

    def _on_tick(self):
        if not self._running:
            return

        current_doc = Krita.instance().activeDocument()
        if current_doc is None:
            self.stop_streaming(self.STATUS_STOPPED)
            return

        if self._active_document is None or self._active_document != current_doc:
            self._active_document = current_doc
            self._layer_node = self._ensure_layer(
                self._active_document, self.layer_name_edit.text().strip() or "LiveCam"
            )
            if self._layer_node is None:
                self.stop_streaming(self.STATUS_DISCONNECTED)
                return
            self._layer_node.setVisible(True)

        if self.source_combo.currentIndex() == self.SOURCE_HTTP:
            self._request_http_frame()
        else:
            self._read_file_frame()

    def _request_http_frame(self):
        if self._pending_reply is not None:
            return

        url_text = self.url_edit.text().strip()
        url = QUrl(url_text)
        if not url.isValid() or not url.scheme():
            self._set_status(self.STATUS_DISCONNECTED, "Invalid URL")
            return

        request = QNetworkRequest(url)
        if hasattr(QNetworkRequest, "FollowRedirectsAttribute"):
            request.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)

        self._pending_reply = self._network_manager.get(request)
        self._reply_buffer = bytearray()
        self._reply_had_frame = False
        self._reply_timed_out = False

        self._pending_reply.readyRead.connect(self._on_reply_ready_read)
        self._pending_reply.finished.connect(self._on_reply_finished)

        if hasattr(self._pending_reply, "errorOccurred"):
            self._pending_reply.errorOccurred.connect(self._on_reply_error)

        self._reply_timeout_timer = QTimer(self)
        self._reply_timeout_timer.setSingleShot(True)
        self._reply_timeout_timer.timeout.connect(self._on_reply_timeout)
        self._reply_timeout_timer.start(1000)

    def _on_reply_error(self, error):
        # Keep finished() as the single place for final status handling.
        _ = error

    def _on_reply_timeout(self):
        if self._pending_reply is None:
            return
        self._reply_timed_out = True
        if self._pending_reply.isRunning():
            self._pending_reply.abort()

    def _on_reply_ready_read(self):
        if self._pending_reply is None:
            return

        chunk = bytes(self._pending_reply.readAll())
        if chunk:
            self._reply_buffer.extend(chunk)

        if self._reply_had_frame:
            return

        jpeg_bytes = self._extract_jpeg_frame(self._reply_buffer)
        if jpeg_bytes is None:
            return

        image = self._decode_image(jpeg_bytes)
        if image is None:
            return

        if self._apply_frame_to_layer(image):
            self._reply_had_frame = True
            self._set_status(self.STATUS_OK)
            if self._pending_reply is not None and self._pending_reply.isRunning():
                self._pending_reply.abort()

    def _on_reply_finished(self):
        reply = self._pending_reply
        if reply is None:
            return

        if self._reply_timeout_timer is not None:
            self._reply_timeout_timer.stop()
            self._reply_timeout_timer.deleteLater()
            self._reply_timeout_timer = None

        error_code = reply.error()
        had_frame = self._reply_had_frame

        remaining = bytes(reply.readAll())
        if remaining:
            self._reply_buffer.extend(remaining)

        if not had_frame and self._reply_buffer:
            image = self._decode_image(bytes(self._reply_buffer))
            if image is None:
                jpeg_bytes = self._extract_jpeg_frame(self._reply_buffer)
                if jpeg_bytes is not None:
                    image = self._decode_image(jpeg_bytes)
            if image is not None and self._apply_frame_to_layer(image):
                had_frame = True

        self._pending_reply = None
        reply.deleteLater()

        if not self._running:
            return

        if had_frame:
            self._set_status(self.STATUS_OK)
            return

        if self._reply_timed_out:
            self._set_status(self.STATUS_TIMEOUT)
            return

        if error_code != QNetworkReply.NoError:
            self._set_status(self.STATUS_DISCONNECTED)
            return

        self._set_status(self.STATUS_DISCONNECTED)

    def _cancel_pending_reply(self):
        if self._reply_timeout_timer is not None:
            self._reply_timeout_timer.stop()
            self._reply_timeout_timer.deleteLater()
            self._reply_timeout_timer = None

        if self._pending_reply is not None:
            reply = self._pending_reply
            self._pending_reply = None
            if reply.isRunning():
                reply.abort()
            reply.deleteLater()

        self._reply_buffer = bytearray()
        self._reply_had_frame = False
        self._reply_timed_out = False

    def _read_file_frame(self):
        path = self.file_edit.text().strip()
        if not path:
            self._set_status(self.STATUS_DISCONNECTED, "Empty file path")
            return
        if not os.path.isfile(path):
            self._set_status(self.STATUS_DISCONNECTED, "File not found")
            return

        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            self._set_status(self.STATUS_DISCONNECTED, "Cannot read file")
            return

        image = self._decode_image(data)
        if image is None:
            self._set_status(self.STATUS_DISCONNECTED, "Invalid image data")
            return

        if self._apply_frame_to_layer(image):
            self._set_status(self.STATUS_OK)

    def _decode_image(self, data):
        image = QImage.fromData(data)
        if image.isNull():
            return None
        return image.convertToFormat(QImage.Format_ARGB32)

    def _extract_jpeg_frame(self, raw_data):
        if not raw_data:
            return None
        start = raw_data.find(b"\xff\xd8")
        if start < 0:
            return None
        end = raw_data.find(b"\xff\xd9", start + 2)
        if end < 0:
            return None
        return bytes(raw_data[start : end + 2])

    def _prepare_display_image(self):
        if self._last_source_image is None or self._last_source_image.isNull():
            return None

        image = self._apply_transformations(self._last_source_image)
        if image is None or image.isNull():
            return None

        self.crop_preview.set_image(image)
        self._update_crop_preview()

        image = self._apply_crop(image)
        if image is None or image.isNull():
            return None

        return image

    def _render_cached_frame(self):
        if self._active_document is None:
            return False

        layer_is_valid = False
        if self._layer_node is not None:
            try:
                layer_is_valid = self._layer_node.parentNode() is not None
            except RuntimeError:
                layer_is_valid = False

        if not layer_is_valid:
            layer_name = self.layer_name_edit.text().strip() or "LiveCam"
            self._layer_node = self._ensure_layer(self._active_document, layer_name)
            if self._layer_node is None:
                return False

        try:
            canvas_w = int(self._active_document.width())
            canvas_h = int(self._active_document.height())
        except RuntimeError:
            return False

        if canvas_w <= 0 or canvas_h <= 0:
            return False

        image = self._prepare_display_image()
        if image is None or image.isNull():
            return False

        composed = QImage(canvas_w, canvas_h, QImage.Format_ARGB32)
        composed.fill(Qt.transparent)

        painter = QPainter(composed)
        if self.fit_to_canvas_checkbox.isChecked():
            scaled = image.scaled(
                canvas_w,
                canvas_h,
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            x = int((canvas_w - scaled.width()) / 2)
            y = int((canvas_h - scaled.height()) / 2)
            painter.drawImage(x, y, scaled)
        else:
            painter.drawImage(0, 0, image)
        painter.end()

        raw_bytes = self._qimage_to_bytes(composed)
        if raw_bytes is None:
            return False

        try:
            self._layer_node.setPixelData(raw_bytes, 0, 0, canvas_w, canvas_h)
            self._layer_node.setVisible(True)
            self._active_document.refreshProjection()
        except RuntimeError:
            return False

        return True

    def _apply_frame_to_layer(self, image):
        if self._active_document is None or image is None or image.isNull():
            return False

        self._last_source_image = image
        return self._render_cached_frame()

    def _qimage_to_bytes(self, image):
        # Krita integer RGBA layers expect bytes ordered as B, G, R, A.
        # QImage.Format_ARGB32 provides that byte layout on the platforms Krita
        # supports in practice, so writing the raw buffer preserves the colors.
        if image.format() != QImage.Format_ARGB32:
            image = image.convertToFormat(QImage.Format_ARGB32)
        bits = image.bits()
        bits.setsize(image.byteCount())
        return bytes(bits)

    def _apply_transformations(self, image):
        if image is None or image.isNull():
            return None

        transformed = image

        degrees = int(self.rotate_combo.currentData() or 0)
        if degrees:
            rotate_transform = QTransform()
            rotate_transform.rotate(degrees)
            transformed = transformed.transformed(rotate_transform, Qt.SmoothTransformation)

        flip_h = self.flip_horizontal_checkbox.isChecked()
        flip_v = self.flip_vertical_checkbox.isChecked()
        if flip_h or flip_v:
            transformed = transformed.mirrored(flip_h, flip_v)

        if transformed.format() != QImage.Format_ARGB32:
            transformed = transformed.convertToFormat(QImage.Format_ARGB32)

        return transformed

    def _apply_crop(self, image):
        if image is None or image.isNull() or not self.crop_checkbox.isChecked():
            return image

        image_w = image.width()
        image_h = image.height()
        if image_w <= 0 or image_h <= 0:
            return image

        x, y, width, height = self._get_crop_values()
        crop_x = min(image_w - 1, int(round(image_w * x / 100.0)))
        crop_y = min(image_h - 1, int(round(image_h * y / 100.0)))
        crop_w = max(1, int(round(image_w * width / 100.0)))
        crop_h = max(1, int(round(image_h * height / 100.0)))
        crop_w = min(image_w - crop_x, crop_w)
        crop_h = min(image_h - crop_y, crop_h)

        return image.copy(crop_x, crop_y, crop_w, crop_h)

    def _get_crop_values(self):
        return (
            self.crop_x_spinbox.value(),
            self.crop_y_spinbox.value(),
            self.crop_width_spinbox.value(),
            self.crop_height_spinbox.value(),
        )

    def _normalize_crop_values(self, x, y, width, height):
        width = max(1, min(100, width))
        height = max(1, min(100, height))
        x = max(0, min(100 - width, x))
        y = max(0, min(100 - height, y))
        width = max(1, min(100 - x, width))
        height = max(1, min(100 - y, height))
        return x, y, width, height

    def _set_crop_values(self, x, y, width, height):
        x, y, width, height = self._normalize_crop_values(x, y, width, height)
        widgets_and_values = (
            (self.crop_x_spinbox, x),
            (self.crop_y_spinbox, y),
            (self.crop_width_spinbox, width),
            (self.crop_height_spinbox, height),
        )

        for widget, value in widgets_and_values:
            widget.blockSignals(True)
            widget.setValue(value)
            widget.blockSignals(False)

        self.crop_x_spinbox.setRange(0, max(0, 100 - width))
        self.crop_y_spinbox.setRange(0, max(0, 100 - height))
        self.crop_width_spinbox.setRange(1, max(1, 100 - x))
        self.crop_height_spinbox.setRange(1, max(1, 100 - y))

    def _normalize_crop_controls(self):
        self._set_crop_values(*self._get_crop_values())

    def _set_crop_controls_enabled(self, enabled):
        self.crop_x_spinbox.setEnabled(enabled)
        self.crop_y_spinbox.setEnabled(enabled)
        self.crop_width_spinbox.setEnabled(enabled)
        self.crop_height_spinbox.setEnabled(enabled)

    def _update_crop_preview(self):
        self.crop_preview.set_crop_enabled(self.crop_checkbox.isChecked())
        self.crop_preview.set_crop_rect(*self._get_crop_values())

    def _ensure_layer(self, doc, layer_name):
        root = doc.rootNode()
        found = self._find_paint_layer(root, layer_name)
        if found is not None:
            return found

        try:
            layer = doc.createNode(layer_name, "paintlayer")
            root.addChildNode(layer, None)
            return layer
        except Exception:
            return None

    def _find_paint_layer(self, node, layer_name):
        for child in node.childNodes():
            if child.name() == layer_name and child.type() == "paintlayer":
                return child
            nested = self._find_paint_layer(child, layer_name)
            if nested is not None:
                return nested
        return None

    def _set_status(self, status, detail=None):
        if detail:
            self.status_label.setText("Status: {} ({})".format(status, detail))
        else:
            self.status_label.setText("Status: {}".format(status))


_REGISTERED = False


def register_live_camera_layer():
    global _REGISTERED
    if _REGISTERED:
        return

    instance = Krita.instance()
    factory = DockWidgetFactory(
        "live_camera_layer_docker",
        DockWidgetFactoryBase.DockRight,
        LiveCameraLayerDocker,
    )
    instance.addDockWidgetFactory(factory)
    _REGISTERED = True
