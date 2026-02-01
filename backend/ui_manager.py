# backend/ui_manager.py
# Creates a HTML UI window with automatic JS→Python event binding
# Handles drag areas, button events, input events, etc.

import sys
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QColor
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import Qt, QObject, pyqtSlot, QUrl, QTimer, pyqtSignal
from PyQt6.QtWebEngineCore import QWebEngineSettings


class Bridge(QObject):
    def __init__(self, callbacks):
        super().__init__()
        self.callbacks = callbacks

    @pyqtSlot(str, str)
    def call(self, name, data=""):
        """JS → Python: pybridge.call('eventName', 'optionalData')"""
        if name in self.callbacks:
            self.callbacks[name](data)
        else:
            print(f"[WARN] No callback defined for event '{name}'")


class HTMLWindow(QWidget):
    run_js_signal = pyqtSignal(str)
    closed = pyqtSignal()

    def __init__(self, html_path, callbacks=None, size=(900, 600), enable_drag=True):
        # CRITICAL: Pass None as parent to make this a top-level window
        super().__init__(parent=None)

        # Set window size first
        self.resize(size[0], size[1])
        
        # Make sure Qt knows this is a top-level window
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        
        # Set window title
        self.setWindowTitle("DSSB Server Browser")

        # Frameless window
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowSystemMenuHint
        )
        # Reduce black flash during resize/maximize.
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

        self.callbacks = callbacks or {}
        # Provide sensible defaults to avoid bridge warnings.
        self.callbacks.setdefault("close", lambda _: self.close())
        self._enable_drag = enable_drag
        if self._enable_drag:
            self.callbacks.setdefault("startDrag", lambda _: None)
            self.callbacks["dragMove"] = self._handle_drag_move

        self.view = QWebEngineView(self)
        self.view.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.view.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.view.setGeometry(0, 0, size[0], size[1])

        settings = self.view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        self.view.page().setBackgroundColor(QColor(0, 0, 0, 0))

        self.website_view = QWebEngineView(self)
        self.website_view.hide()
        self._website_url = None

        # Add error handling for page load
        self.view.loadFinished.connect(self.on_load_finished)
        
        self.view.load(QUrl.fromLocalFile(html_path))

        self.channel = QWebChannel()
        self.bridge = Bridge(self.callbacks)
        self.channel.registerObject("pybridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

        self.view.page().loadFinished.connect(self.inject_handler_script)
        self.run_js_signal.connect(self._run_js)

    def _run_js(self, js):
        self.view.page().runJavaScript(js)
    
    def on_load_finished(self, success):
        """Handle page load completion."""
        if success:
            print("Page loaded successfully")
        else:
            print("ERROR: Page failed to load!")
    
    def closeEvent(self, event):
        """Override close event to debug."""
        print("Window close event triggered!")
        self.closed.emit()
        event.accept()

    def resizeEvent(self, event):
        self.view.setGeometry(0, 0, self.width(), self.height())
        if self.website_view.isVisible():
            self._update_website_geometry()
        return super().resizeEvent(event)

    def inject_handler_script(self):
        """Injects JS that auto-binds drag areas and data-event handlers."""
        js = """
        function waitForWebChannel() {
            if (typeof QWebChannel === "undefined" || typeof qt === "undefined" || !qt.webChannelTransport) {
                setTimeout(waitForWebChannel, 10);
                return;
            }

            if (window.pybridge || window._pybridgeReady) {
                return;
            }
            window._pybridgeReady = true;
            new QWebChannel(qt.webChannelTransport, function(channel) {
                window.pybridge = channel.objects.pybridge;

                // Auto-bind all elements with data-event
                document.querySelectorAll('[data-event]').forEach(el => {
                    const eventName = el.getAttribute('data-event');

                    if (el.tagName === "INPUT") {
                        el.oninput = () => window.pybridge.call(eventName, el.value);
                    } else {
                        el.onclick = () => window.pybridge.call(eventName, "");
                    }
                });
            });
        }

        waitForWebChannel();
        """
        if not self._enable_drag:
            self.view.page().runJavaScript(js)
            return

        js = """
        function waitForWebChannel() {
            if (typeof QWebChannel === "undefined" || typeof qt === "undefined" || !qt.webChannelTransport) {
                setTimeout(waitForWebChannel, 10);
                return;
            }

            if (window.pybridge || window._pybridgeReady) {
                return;
            }
            window._pybridgeReady = true;
            new QWebChannel(qt.webChannelTransport, function(channel) {
                window.pybridge = channel.objects.pybridge;

                let dragging = false;
                let lastX = 0;
                let lastY = 0;

                // Handle draggable areas
                document.querySelectorAll('.drag').forEach(el => {
                    el.onmousedown = (e) => {
                        if (e.button !== 0) return;
                        if (e.target.closest("button") || e.target.closest("[data-event]")) return;
                        dragging = true;
                        lastX = e.screenX;
                        lastY = e.screenY;
                        window.pybridge.call("startDrag", "");
                    };
                });

                document.onmouseup = () => dragging = false;

                document.onmousemove = (e) => {
                    if (!dragging) return;
                    const dx = e.screenX - lastX;
                    const dy = e.screenY - lastY;
                    lastX = e.screenX;
                    lastY = e.screenY;
                    window.pybridge.call("dragMove", dx + "," + dy);
                };

                // Auto-bind all elements with data-event
                document.querySelectorAll('[data-event]').forEach(el => {
                    const eventName = el.getAttribute('data-event');

                    if (el.tagName === "INPUT") {
                        el.oninput = () => window.pybridge.call(eventName, el.value);
                    } else {
                        el.onclick = () => window.pybridge.call(eventName, "");
                    }
                });
            });
        }

        waitForWebChannel();
        """
        self.view.page().runJavaScript(js)

    # Python-side drag handling
    def _handle_drag_move(self, data):
        dx, dy = map(int, data.split(","))
        self.move(self.x() + dx, self.y() + dy)

    def show_website(self, url):
        if not url:
            self.hide_website()
            return
        self._website_url = url
        QTimer.singleShot(0, self._update_website_geometry)

    def hide_website(self):
        self.website_view.hide()
        self.website_view.setUrl(QUrl())
        self._website_url = None

    def _update_website_geometry(self):
        def apply_rect(rect):
            if not rect:
                return
            x = int(rect.get("x", 0))
            y = int(rect.get("y", 0))
            w = int(rect.get("width", 0))
            h = int(rect.get("height", 0))
            if w <= 0 or h <= 0:
                return
            self.website_view.setGeometry(x, y, w, h)
            if self._website_url:
                self.website_view.setUrl(QUrl(self._website_url))
                self.website_view.show()
                self.website_view.raise_()

        js = """
        (() => {
            const el = document.getElementById('content');
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {x: r.x, y: r.y, width: r.width, height: r.height};
        })()
        """
        self.view.page().runJavaScript(js, apply_rect)
