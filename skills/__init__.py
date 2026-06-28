"""Installable package data root. Each subpackage holds the resources for one
installable artifact (the slash command, future tray/web extensions, etc.).
Kept as a Python package so importlib.resources can locate the bundled
non-Python files inside an installed wheel."""
