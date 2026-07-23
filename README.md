<p align="center">
  <img src="https://res.cloudinary.com/dpmnce5h6/image/upload/v1784829961/vtfnteev8wpilnbzjhao.png" alt="Enchanter CAD" width="480"/>
</p>

<h3 align="center">A lightweight, open-source 2D CAD application</h3>

<p align="center">
  <img src="https://res.cloudinary.com/dpmnce5h6/image/upload/v1784830109/ftnyywpaxebqer4ms06n.png" alt="Enchanter CAD Screenshot" width="780"/>
</p>

<p align="center">
  <a href="https://github.com/SID-cmd-sk/enchanter-cad/releases/tag/v1.1">
    <img src="https://img.shields.io/badge/Download-v1.1-blue?style=for-the-badge" alt="Download v1.1"/>
  </a>
  <img src="https://img.shields.io/badge/Python-3.10+-green?style=for-the-badge" alt="Python 3.10+"/>
  <img src="https://img.shields.io/badge/License-MIT-orange?style=for-the-badge" alt="MIT License"/>
</p>

---

## About

**Enchanter CAD** is a 2D computer-aided drawing application inspired by AutoCAD. Built with Python and PyQt6, it provides a familiar command-line interface, layer management, DXF/DWG import/export, and G-code generation — all in a lightweight package.

## Features

- **AutoCAD-style command line** — type commands with full A-Z alias support
- **Drawing tools** — Line, Arc, Circle, Ellipse, Polyline, Spline, Rectangle, Point, Text, Dimensions, Leaders, Hatches
- **Modify commands** — Trim, Extend, Offset, Mirror, Rotate, Scale, Move, Copy, Fillet, Array, Stretch
- **Layer system** — Create, lock, freeze, and manage drawing layers with color support
- **DXF/DWG support** — Open and save DXF files via the `ezdxf` library
- **G-code export** — Generate CNC G-code from your drawings
- **Block & Attribute support** — Create and insert blocks with attribute definitions
- **Hatch & Gradient fills** — Solid, pattern, and gradient hatch support
- **Responsive UI** — Dark theme with toolbar, ribbon, and status bar

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.10+ |
| GUI | PyQt6 |
| DXF I/O | ezdxf |
| Packaging | PyInstaller |
| Icons | Custom SVG library (200+ icons) |

## Getting Started

### Prerequisites

- Python 3.10 or later
- pip

### Installation

```bash
git clone https://github.com/SID-cmd-sk/enchanter-cad.git
cd enchanter-cad
pip install -r requirements.txt
```

### Run

```bash
python main.py
```

### Build EXE

```bash
pyinstaller pycad.spec
```

## Project Structure

```
enchanter-cad/
├── main.py            # Application entry point
├── canvas.py          # Drawing canvas (OpenGL-based viewport)
├── commands.py        # 30+ AutoCAD-style command implementations
├── command_table.py   # Command alias resolver (A-Z)
├── entities.py        # Drawing entities (Line, Arc, Circle, etc.)
├── ribbon.py          # Ribbon toolbar UI
├── io_dxf.py          # DXF import/export
├── gcode.py           # G-code generation engine
├── gcode_dialog.py    # G-code export dialog
├── testlog.py         # Test logging utilities
└── requirements.txt   # Python dependencies
```

## Screenshots

<p align="center">
  <img src="https://res.cloudinary.com/dpmnce5h6/image/upload/v1784829964/rxb5hqnqummzzumebgww.png" alt="Splash Screen" width="600"/>
</p>

## Download

Download the latest release from the [Releases page](https://github.com/SID-cmd-sk/enchanter-cad/releases/tag/v1.1).

| File | Description |
|------|-------------|
| `ENCHANTER-CAD-Installer.exe` | Full installer with start menu shortcuts |

## Contributing

Contributions are welcome! Feel free to open issues or submit pull requests.

1. Fork the repo
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

<p align="center">
  Built with Python & PyQt6
</p>
