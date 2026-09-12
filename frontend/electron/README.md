# electron/
# This directory is intentionally empty.
#
# Electron packaging (main.js, preload.js, electron-builder config) is built
# on Day 9 per Advay.md and FRONTEND.md §4.1.
#
# When built, this directory will contain:
#   main.js     — BrowserWindow lifecycle, backend health-check/spawn, no menu bar
#   preload.js  — contextBridge IPC surface (native file dialogs + drive status only)
#
# See FRONTEND.md §4.1 for the exact spec.
