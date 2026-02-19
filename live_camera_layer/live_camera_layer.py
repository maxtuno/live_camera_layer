import os

from krita import DockWidget, DockWidgetFactory, DockWidgetFactoryBase, Krita
from PyQt5.QtCore import Qt, QTimer, QUrl
from PyQt5.QtGui import QImage, QPainter, QTransform
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


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
        layout.addWidget(self.fit_to_canvas_checkbox)

        rotate_row = QHBoxLayout()
        rotate_row.addWidget(QLabel("Rotate"))
        self.rotate_combo = QComboBox()
        self.rotate_combo.addItem("0°", 0)
        self.rotate_combo.addItem("90°", 90)
        self.rotate_combo.addItem("180°", 180)
        self.rotate_combo.addItem("270°", 270)
        rotate_row.addWidget(self.rotate_combo)
        layout.addLayout(rotate_row)

        flip_row = QHBoxLayout()
        self.flip_horizontal_checkbox = QCheckBox("Flip horizontal")
        self.flip_vertical_checkbox = QCheckBox("Flip vertical")
        flip_row.addWidget(self.flip_horizontal_checkbox)
        flip_row.addWidget(self.flip_vertical_checkbox)
        layout.addLayout(flip_row)

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
        return image.convertToFormat(QImage.Format_RGBA8888)

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

    def _apply_frame_to_layer(self, image):
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

        image = self._apply_transformations(image)
        if image is None or image.isNull():
            return False

        composed = QImage(canvas_w, canvas_h, QImage.Format_RGBA8888)
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

    def _qimage_to_bytes(self, image):
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

        if transformed.format() != QImage.Format_RGBA8888:
            transformed = transformed.convertToFormat(QImage.Format_RGBA8888)

        return transformed

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
