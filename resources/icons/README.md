# icons

Place `voice-input.ico` here for the PyInstaller build (see `voice-input-win.spec`).

To regenerate from a PNG source:

```bash
# On Windows with Pillow installed:
py -c "from PIL import Image; Image.open('voice-input.png').save('voice-input.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
```

If no `.ico` is provided, PyInstaller defaults to its own icon; the tray still
uses the programmatically-drawn microphone glyph from `tray.py`.
