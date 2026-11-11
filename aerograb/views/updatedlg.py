# -*- coding: utf-8 -*-
"""واجهة التحديث التلقائي: نافذة "يوجد تحديث" + شريط تقدم التنزيل + إعادة التشغيل."""
import os
import threading
import webbrowser
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from aerograb import updater
from aerograb.common import log_error, save_settings
from aerograb.views.winutil import fit_geometry
from aerograb.config import APP_NAME, APP_VERSION, UI_FONT
from aerograb.fmt import fmt_bytes
from aerograb.state import ui
from aerograb.uistate import gui
from aerograb.views.branding import apply_window_icon, logo_ctk

GREEN, GREEN_H = "#2cc985", "#21a06a"
_shown = set()          # الإصدارات اللي ظهرت للمستخدم في الجلسة دي (منكررش النافذة)
_win = [None]
RECHECK_MS = 3 * 3600 * 1000


def start_background_checks():
    """بتتنادى بعد فتح الواجهة: فحص بعد ثواني، وبعدين كل كام ساعة طول ما البرنامج شغّال."""
    if not updater.enabled():
        return
    gui.root.after(6000, _check_quietly)


def _check_quietly():
    try:
        updater.check_async(lambda status, info: ui(_on_quiet_result, status, info))
    finally:
        try:
            gui.root.after(RECHECK_MS, _check_quietly)
        except Exception:
            pass


def _on_quiet_result(status, info):
    if status == "new" and info and info["version"] not in _shown:
        show_update_dialog(info)


def manual_check(report):
    """report(text, ok): للإعدادات. لو في تحديث بتفتح النافذة."""
    def on_result(status, info):
        def done():
            if status == "new":
                report(f"Version {info['version']} is available. You have {APP_VERSION}.", True)
                show_update_dialog(info, force=True)
            elif status == "latest":
                report(f"You have the latest version (you: {APP_VERSION}, latest on GitHub: {info['version'] if info else APP_VERSION}).", True)
            elif status == "disabled":
                report("Update link is not set yet (see aerograb/links.py).", False)
            else:
                report("Could not check for updates (check your internet).", False)
        ui(done)
    updater.check_async(on_result, force=True)


def _restart_now():
    from aerograb.tasks import save_history
    from aerograb.server import shutdown_server
    save_history()
    try:
        shutdown_server()
    except Exception:
        pass
    os._exit(0)


def show_update_dialog(info, force=False):
    if _win[0] is not None:
        try:
            if _win[0].winfo_exists():
                _win[0].lift()
                return
        except Exception:
            pass
    _shown.add(info["version"])
    win = ctk.CTkToplevel(gui.root)
    _win[0] = win
    apply_window_icon(win)
    win.title("Update available")
    fit_geometry(win, 470, 400)
    win.resizable(False, False)
    win.attributes("-topmost", True)
    win.after(500, lambda: win.attributes("-topmost", False))

    head = ctk.CTkFrame(win, fg_color="transparent")
    head.pack(fill="x", padx=20, pady=(18, 6))
    ctk.CTkLabel(head, text="", image=logo_ctk(46)).pack(side="left")
    col = ctk.CTkFrame(head, fg_color="transparent")
    col.pack(side="left", padx=12)
    ctk.CTkLabel(col, text="A new version of AeroGrab is available.", font=(UI_FONT, 14, "bold"), anchor="w").pack(anchor="w")
    ctk.CTkLabel(col, text=f"{APP_VERSION}  →  {info['version']}", font=(UI_FONT, 13), text_color=GREEN, anchor="w").pack(anchor="w")

    ctk.CTkLabel(win, text="What's new", font=(UI_FONT, 12, "bold"), anchor="w").pack(fill="x", padx=22, pady=(8, 2))
    box = ctk.CTkTextbox(win, height=150, font=(UI_FONT, 12), wrap="word")
    box.pack(fill="x", padx=20)
    box.insert("1.0", (info.get("notes") or "-")[:1500])
    box.configure(state="disabled")

    status = ctk.CTkLabel(win, text="", font=(UI_FONT, 11), text_color="gray", anchor="w")
    status.pack(fill="x", padx=22, pady=(8, 0))
    bar = ctk.CTkProgressBar(win, progress_color=GREEN)
    bar.set(0)
    bar.pack(fill="x", padx=22, pady=(2, 6))
    bar.pack_forget()

    row = ctk.CTkFrame(win, fg_color="transparent")
    row.pack(pady=10)
    state = {"busy": False, "stop": False}

    def close():
        state["stop"] = True
        try:
            win.destroy()
        except Exception:
            pass

    def run():
        if state["busy"]:
            return
        if not info.get("asset_url"):
            webbrowser.open(info["page"])
            close()
            return
        state["busy"] = True
        now_btn.configure(state="disabled")
        bar.pack(fill="x", padx=22, pady=(2, 6), before=row)
        status.configure(text="Downloading the update...")

        def progress(done, total):
            if total:
                ui(lambda: win.winfo_exists() and (bar.set(done / total), status.configure(
                    text=f"Downloading the update... {done * 100 // total}%   ({fmt_bytes(done)} / {fmt_bytes(total)})")))

        def worker():
            try:
                path = updater.download(info, progress, lambda: state["stop"])
                mode, _ = updater.prepare_install(path)
            except Exception as e:
                if state["stop"]:
                    return
                log_error("update install", e)
                ui(fail, str(e))
                return
            ui(finish, mode)

        def fail(msg):
            if not win.winfo_exists():
                return
            state["busy"] = False
            now_btn.configure(state="normal")
            status.configure(text=f"{msg}", text_color="#e53935")
            if messagebox.askyesno("Update failed", f"{msg}\n\nOpen the download page?", parent=win):
                webbrowser.open(info["page"])

        def finish(mode):
            if mode == "browser":
                webbrowser.open(info["page"])
                close()
                return
            status.configure(text="The update is ready. AeroGrab will restart to finish installing it.", text_color=GREEN)
            win.after(1200, _restart_now)

        threading.Thread(target=worker, daemon=True, name="aerograb-update-download").start()

    now_btn = ctk.CTkButton(row, text="Update now", width=140, height=36, fg_color=GREEN, hover_color=GREEN_H, command=run)
    now_btn.pack(side="left", padx=6)
    ctk.CTkButton(row, text="Open the download page", width=170, height=36, fg_color="gray40",
                  command=lambda: webbrowser.open(info["page"])).pack(side="left", padx=6)
    ctk.CTkButton(row, text="Later", width=90, height=36, fg_color="gray30", command=close).pack(side="left", padx=6)
    win.protocol("WM_DELETE_WINDOW", close)
