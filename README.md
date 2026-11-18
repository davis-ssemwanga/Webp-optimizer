# WebP Optimizer

A desktop app that batch-converts **JPG, JPEG and PNG** images to **WebP** to shrink file
sizes for faster websites. Everything runs locally; no image ever leaves your computer.

## Features

- Pick single images, many images or a whole folder (also by **drag and drop**), optionally including subfolders.
- Converted files go to a **separate output folder**, created automatically:
  `D:/Website/Gallery` → `D:/Website/Gallery_Converted_WebP` (you can change the name/location).
- Originals are **never modified, moved or deleted**. The app refuses to use the source folder as the output.
- Subfolder structure is mirrored in the output when "Include subfolders" is on.
- Lossy (quality 1–100, default 85) or lossless; compression effort 0–6.
- Optional resize to a max width/height: keeps aspect ratio, **never upscales**.
- Keeps PNG transparency, applies EXIF rotation, keeps ICC colour profiles (CMYK JPEGs are converted to sRGB).
- Filename collisions: `photo.jpg` + `photo.png` can never overwrite each other (second becomes `photo_png.webp`).
  Files already in the output folder: **rename**, **skip** or **overwrite** (your choice, with a confirmation for overwrite).
- Live progress, per-file sizes and savings, pause / resume / cancel, and a before/after preview.
- Honest reporting: images that get *larger* as WebP are flagged, not hidden.
- Report export to **CSV** or **TXT**.
- Safe writes: each file is written to a temp file and atomically moved into place, so a cancel or crash never leaves a broken `.webp`.

## Install and run (Windows / macOS / Linux)

Requires **Python 3.11 or newer** (3.14 works with the pinned minimum versions in requirements.txt).

If `pip install` times out on a slow connection: `pip install -r requirements.txt --default-timeout=120 --retries 10`.

```bash
python -m venv .venv
# Windows:   .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

### In VS Code
1. **File → Open Folder…** and choose the `webp_optimizer` folder.
2. `Ctrl+Shift+P` → **Python: Create Environment** → *Venv* → tick `requirements.txt`
   (or run the commands above in the terminal).
3. `Ctrl+Shift+P` → **Python: Select Interpreter** → choose the `.venv` one.
4. Press **F5** and pick **WebP Optimizer** (a ready-made `.vscode/launch.json` is included).

## Using the app
1. **Source:** *Select Folder…* or *Select Images…* (or drop them on the window).
2. **Settings:** check the output folder, choose lossy/lossless and quality. Click **Preview** first on a typical image to compare quality and size with your current settings.
3. **Start Conversion.** Watch progress; use Pause/Cancel if needed.
4. **Summary:** *Open Output Folder* or *Export Report…*.

Tips: quality 80–85 is a good default for photos; use **Lossless** for logos/screenshots.
If memory is tight with very large photos, set **Parallel jobs** to 1 or 2.

## Project layout
```
webp_optimizer/
├── main.py
├── core/        converter, compression (settings), folder_scanner, image_validator,
│                output_planner (names/conflicts), batch_runner (thread pool), report_generator
├── gui/         main_window, source_panel, settings_panel, progress_panel, preview_panel, styles
├── workers/     conversion_worker (QThread wrapper)
├── utils/       file_utils, size_formatter
├── tests/       test_core.py
└── assets/icons/   (optional app.ico used for the window and the .exe)
```
`core/` contains no GUI code and can be reused or tested on its own.

## Run the tests
```bash
python -m unittest discover -s tests -v
```
(27 tests: formats, transparency, EXIF, ICC, resizing, colour modes, corrupt files, duplicate names,
conflict policies, recursion, cancel/pause, report export, originals-unchanged checks.)

## Build a standalone Windows .exe
```bat
pip install pyinstaller
pyinstaller --noconfirm --clean --windowed --name WebPOptimizer --add-data "assets;assets" main.py
```
or just double-click/run **`build_exe.bat`**. The app is created in `dist\WebPOptimizer\`; distribute that whole folder
(zip it). To make a single file add `--onefile` (starts slower and is more often flagged by antivirus).
To use a custom icon, put an `app.ico` in `assets/icons/` before building.

## Make an installer (Setup.exe)
1. Run `build_exe.bat` first (creates `dist\WebPOptimizer\`).
2. Install the free **Inno Setup** (jrsoftware.org), open `installer.iss` and press **Build -> Compile**
   (or run `iscc /DAppVersion=1.0.0 installer.iss`).
3. The installer appears in `installer_output\`.

## Automatic builds on GitHub
`.github/workflows/build.yml` builds the installer and a portable zip on GitHub's servers and attaches them
to a Release whenever you push a version tag:
```bash
git tag v1.0.0
git push origin v1.0.0
```

## Notes and limitations
- EXIF metadata (camera info, GPS) is **not** copied to the WebP; rotation is applied to the pixels and the ICC profile is kept.
- Animated PNGs are converted using their first frame only.
- WebP supports at most 16,383 px per side; larger images fail with a clear message unless resizing is enabled.
- Lossless WebP of a photo is often *larger* than the original JPEG, which is expected; use lossy for photos.
- Image content is validated, not just the extension: a GIF renamed to `.jpg` is rejected and reported.
