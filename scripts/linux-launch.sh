#!/bin/sh
# Linux launch wrapper to avoid blue/blank QtWebEngine windows on some GPUs (e.g. Steam Deck).

if [ "${DSSB_USE_GPU:-0}" != "1" ]; then
  export QT_OPENGL="${QT_OPENGL:-software}"
  export QTWEBENGINE_DISABLE_SANDBOX="${QTWEBENGINE_DISABLE_SANDBOX:-1}"
  export QTWEBENGINE_CHROMIUM_FLAGS="${QTWEBENGINE_CHROMIUM_FLAGS:---disable-gpu --disable-gpu-compositing --disable-features=UseSkiaRenderer}"
fi

DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "$DIR/DSSbrowser" "$@"
