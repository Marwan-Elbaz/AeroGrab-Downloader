# AeroGrab

Fast, private download manager for Windows with a browser extension.
الواجهة بالإنجليزي والعربي (زرار 🌐 في الشريط العلوي أو Settings ← General).

## Run
```
pip install -r requirements.txt
python main.py
```
`python main.py --background` starts it hidden and waits for the browser (this is what "Start with Windows" uses).

## Browser extension
Chrome / Edge / Brave: `chrome://extensions` → Developer mode → Load unpacked → choose the `extension` folder.
Clicking the AeroGrab button in the toolbar opens the program. Hold **Alt** while clicking a link to let the browser download it.

## Build an .exe (PyInstaller)
```
pip install pyinstaller
pyinstaller --noconsole --onedir --name AeroGrab --icon logo.ico --add-data "logo.ico;." main.py
```
Use `--onedir` (starts faster than `--onefile`).

## Upgrading from "IDM Modern Pro"
Your settings and download list are moved automatically to the new data folder on first start. The old `idmpro://` link still works.

## Languages / اللغات
English and العربية. Switch from Settings → General → Language; the program restarts to apply it.
The Arabic text lives in `aerograb/i18n.py` (dictionary `AR`). Missing strings stay English; to list them run with
`AEROGRAB_I18N_DEBUG=1` and read `~/.aerograb/missing_i18n.txt`.

## Links and icons / الروابط
Everything you need to fill after uploading is in **`aerograb/links.py`** – paste the URLs between the quotes, nothing else:

| Setting | Used by |
|---|---|
| `GITHUB_URL` | GitHub icon (Settings sidebar + About) and the Share button fallback |
| `YOUTUBE_URL` | YouTube icon |
| `FEEDBACK_URL` | message icon (contact / suggestions) |
| `COPYRIGHT_OWNER` | name shown in the © line in About |
| `SHARE_URL` | Share button (Settings → About): copies this link straight to the clipboard (empty = `GITHUB_URL`) |
| `UPDATE_REPO` | `"owner/repo"` of the GitHub repo used for automatic updates |

## Publishing on GitHub / النشر
1. Create a repo, then from this folder: `git init`, `git add .`, `git commit -m "AeroGrab"`, `git branch -M main`,
   `git remote add origin https://github.com/<you>/AeroGrab.git`, `git push -u origin main`.
2. Fill `aerograb/links.py` (`GITHUB_URL`, `UPDATE_REPO = "<you>/AeroGrab"`).
3. Release: raise `APP_VERSION`, commit, then `git tag v4.2` and `git push origin v4.2`.
   `.github/workflows/release.yml` builds Windows 64-bit (`-x64.zip`) and 32-bit (`-x86.zip`) on GitHub and attaches both to a new Release (no need to build locally).
   Installed copies update with the zip that matches their own bitness. On 32-bit Windows (no Deno build) the program downloads Node.js 22 (win-x86, SHA-256 verified) as the YouTube JavaScript engine instead.

## Installer / المثبّت
`installer.iss` (Inno Setup 6.3+) builds `AeroGrab-<ver>-x64-Setup.exe` and `-x86-Setup.exe`: per-user install (no admin), Start menu + optional desktop shortcut,
uninstaller in Apps & features (asks whether to delete settings/history, never the downloads). GitHub Actions builds it automatically next to the zips.
Locally: install Inno Setup, then `python build_release.py` builds the app, the zip and the installer.
Installed copies update silently through the matching Setup.exe; portable (zip) copies keep updating from the zip.

## Automatic updates / التحديث التلقائي
1. Set `UPDATE_REPO = "owner/repo"` in `aerograb/links.py` (once).
2. Raise `APP_VERSION` in `aerograb/config.py` (e.g. `"4.2"`).
3. `python build_release.py` → `release/AeroGrab-4.2-x64.zip` (`-x86` with 32-bit Python).
4. On GitHub create a Release with tag `v4.2` and upload that zip.

Every installed copy checks GitHub on start and every few hours (Settings → Updates → *Check for updates automatically*),
asks the user, downloads the zip, closes, swaps the files (with a backup folder `AeroGrab_old`) and starts again.
A `*Setup*.exe` / `*.msi` asset is also supported (it is launched instead). Running from source only opens the release page.
Note: the browser extension is installed manually, so it is not updated automatically (`EXTENSION_VERSION` in `config.py`).
