# AeroGrab — code layout

```
main.py                 entry point (arguments, protocol, startup)
logo.ico / logo.png     app icon
extension/              browser extension (reads its settings from the program)
aerograb/
  config.py             constants, paths, app name/version
  common.py             log, JSON settings, system messages
  netutil.py            network, SSL, proxy, timeouts, site logins
  ytdlp_mgr.py          yt-dlp download and update
  state.py              shared state (tasks, events, UI queue)
  fmt.py                number/error formatting
  tools.py              ffmpeg / JS runtime / yt-dlp options
  limits.py             speed limit, schedule
  files.py              file names and paths
  downloader.py         segmented downloader (resume, refresh link)
  mediainfo.py          video / playlist info
  system.py             Windows startup, aerograb:// protocol
  capture.py            settings the extension reads (/get_settings)
  clipwork.py           resumable "download part of a video"
  checksum.py           MD5 / SHA-1 / SHA-256 / SHA-512 verification
  tasks.py              task model + history
  server.py             local server (127.0.0.1:9999) used by the extension
  engine.py             download engine and task actions
  i18n.py               English/Arabic (dictionary + hooks that translate tkinter text on screen)
  links.py              GitHub / YouTube / feedback / share / update-repo URLs (edit only this)
  updater.py            automatic update (GitHub Releases): check, download, swap files, restart
  icons_extra.py        extra embedded icons (search, language, export, cookie, github, youtube, ...)
  uistate.py            live UI objects (gui.root, gui.tree ...)
  lazyviews.py          lazy bridges so background mode stays light
  logo_data.py          embedded logo
  icons_data.py         embedded icons
  views/                GUI (loaded only when the window opens)
    window  mainwin  cards  popups  grabber  settings  dialogs
    stats  thumbs  icons  winutil  tooltip  branding  linkutil  updatedlg
```
Rules: core modules never import `views`; non-view modules reach the GUI through `lazyviews`;
live widgets are read from `gui.<name>`; mutual imports between GUI modules sit at the bottom of each file.
