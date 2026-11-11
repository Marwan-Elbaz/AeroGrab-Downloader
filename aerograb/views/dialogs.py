# -*- coding: utf-8 -*-
"""نوافذ إضافية: تحديث رابط التحميل (Refresh link) والتحقق من سلامة الملف (Checksum)."""
import os
import threading
import customtkinter as ctk
from tkinter import messagebox
import tkinter as tk
from aerograb.checksum import ALGOS, compute, extract_hash
from aerograb.views.winutil import fit_geometry
from aerograb.fmt import fmt_bytes
from aerograb.state import tasks, tasks_lock, ui
from aerograb.uistate import gui
from aerograb.views.branding import apply_window_icon

GREEN, GREEN_H = "#2cc985", "#21a06a"
_open = {}


def _single(kind, iid):
    """نافذة واحدة بس لكل (نوع، تحميل): لو مفتوحة بنرفعها."""
    w = _open.get((kind, iid))
    try:
        if w is not None and w.winfo_exists():
            w.lift()
            w.focus_force()
            return True
    except Exception:
        pass
    return False


def _selected_one():
    ids = _selected_ids()
    if not ids:
        messagebox.showinfo("Select a download", "Select a download in the list first.", parent=gui.root)
        return None
    return ids[0]


# ============================================================================ Refresh link
def refresh_selected():
    iid = _selected_one()
    if iid:
        show_refresh_dialog(iid)


def show_refresh_dialog(iid):
    with tasks_lock:
        t = tasks.get(iid)
        if not t:
            return
        status, title, cur_url = t["status"], t.get("title") or "this download", t["url"]
    if status in ("completed", "deleted"):
        messagebox.showinfo("Refresh link", "This download is already finished.", parent=gui.root)
        return
    if _single("refresh", iid):
        return
    win = ctk.CTkToplevel(gui.root)
    apply_window_icon(win)
    _open[("refresh", iid)] = win
    win.title("Refresh download link")
    fit_geometry(win, 620, 330)
    win.resizable(False, False)
    win.attributes("-topmost", True)
    win.after(500, lambda: win.attributes("-topmost", False))
    ctk.CTkLabel(win, text="Refresh download link", font=("Segoe UI", 17, "bold")).pack(anchor="w", padx=20, pady=(16, 2))
    ctk.CTkLabel(win, text=title, font=("Segoe UI", 12), text_color="gray", anchor="w", wraplength=570, justify="left").pack(fill=tk.X, padx=20)
    ctk.CTkLabel(win, text="Links from some sites stop working after a while (error 403 or 410). Get the same file's new link "
                           "(copy it from the browser, or start the download again there) and paste it here. "
                           "The part already downloaded is kept and the download continues from where it stopped.",
                 font=("Segoe UI", 11), wraplength=570, justify="left", anchor="w").pack(fill=tk.X, padx=20, pady=(10, 8))
    ctk.CTkLabel(win, text="New link:", font=("Segoe UI", 12, "bold"), anchor="w").pack(fill=tk.X, padx=20)
    entry = ctk.CTkEntry(win, height=34, placeholder_text="https://...")
    entry.pack(fill=tk.X, padx=20, pady=(2, 4))
    try:                                    # لو الكليبورد فيه رابط جديد نملّيه أوتوماتيك
        clip = gui.root.clipboard_get().strip()
        if clip.lower().startswith(("http://", "https://")) and "\n" not in clip and clip != cur_url:
            entry.insert(0, clip)
    except Exception:
        pass
    msg = ctk.CTkLabel(win, text="", font=("Segoe UI", 11), anchor="w", text_color="#FF9800")
    msg.pack(fill=tk.X, padx=20)

    def go(event=None):
        ok, why = refresh_task_link(iid, entry.get())
        if not ok:
            msg.configure(text=why)
            return
        win.destroy()
    row = ctk.CTkFrame(win, fg_color="transparent")
    row.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=16)
    ctk.CTkButton(row, text="Refresh and resume", fg_color=GREEN, hover_color=GREEN_H, height=36, command=go).pack(side=tk.RIGHT)
    ctk.CTkButton(row, text="Cancel", fg_color="gray40", height=36, width=90, command=win.destroy).pack(side=tk.RIGHT, padx=8)
    entry.bind("<Return>", go)
    entry.focus_set()


# ============================================================================ Verify checksum
def verify_selected():
    iid = _selected_one()
    if iid:
        show_verify_dialog(iid)


def show_verify_dialog(iid):
    with tasks_lock:
        t = tasks.get(iid)
        if not t:
            return
        path, status = t.get("file_path") or "", t["status"]
    if status != "completed" or not os.path.isfile(path):
        messagebox.showinfo("Verify checksum", "Only a finished download whose file still exists can be verified.", parent=gui.root)
        return
    if _single("verify", iid):
        return
    win = ctk.CTkToplevel(gui.root)
    apply_window_icon(win)
    _open[("verify", iid)] = win
    win.title("Verify file integrity")
    fit_geometry(win, 640, 470)
    win.resizable(False, False)
    win.attributes("-topmost", True)
    win.after(500, lambda: win.attributes("-topmost", False))
    stop = threading.Event()
    win.protocol("WM_DELETE_WINDOW", lambda: (stop.set(), win.destroy()))

    ctk.CTkLabel(win, text="Verify file integrity", font=("Segoe UI", 17, "bold")).pack(anchor="w", padx=20, pady=(16, 2))
    ctk.CTkLabel(win, text=f"{os.path.basename(path)}   ({fmt_bytes(os.path.getsize(path))})", font=("Segoe UI", 12),
                 text_color="gray", anchor="w", wraplength=590, justify="left").pack(fill=tk.X, padx=20)
    ctk.CTkLabel(win, text="Paste the checksum the publisher gives for this file (MD5, SHA-1, SHA-256 or SHA-512). "
                           "If it matches, the file is exactly the one they published.",
                 font=("Segoe UI", 11), wraplength=590, justify="left", anchor="w").pack(fill=tk.X, padx=20, pady=(10, 6))
    expected = ctk.CTkEntry(win, height=34, placeholder_text="Expected checksum (optional)")
    expected.pack(fill=tk.X, padx=20)
    arow = ctk.CTkFrame(win, fg_color="transparent")
    arow.pack(fill=tk.X, padx=20, pady=(10, 4))
    ctk.CTkLabel(arow, text="Algorithm:", font=("Segoe UI", 12)).pack(side=tk.LEFT)
    algo_var = ctk.StringVar(value="Auto")
    ctk.CTkOptionMenu(arow, variable=algo_var, values=["Auto"] + list(ALGOS.keys()), width=130).pack(side=tk.LEFT, padx=8)
    bar = ctk.CTkProgressBar(win)
    bar.set(0)
    bar.pack(fill=tk.X, padx=20, pady=(8, 4))
    result = ctk.CTkLabel(win, text="", font=("Segoe UI", 14, "bold"), anchor="w", wraplength=590, justify="left")
    result.pack(fill=tk.X, padx=20, pady=(4, 2))
    got = ctk.CTkEntry(win, height=30, state="readonly", font=("Consolas", 11))
    got.pack(fill=tk.X, padx=20)
    state = {"busy": False}

    def show_result(text, color, computed=""):
        result.configure(text=text, text_color=color)
        got.configure(state="normal")
        got.delete(0, tk.END)
        got.insert(0, computed)
        got.configure(state="readonly")

    def work(algo, want):
        try:
            h = compute(path, algo, lambda d, tot: ui(lambda: bar.set(d / tot if tot else 1)), stop.is_set)
        except Exception as e:
            msg = f"Could not read the file: {e}"          # لازم نحفظ الرسالة: Python بيمسح e بعد الـ except والـ lambda بتشتغل بعدها
            ui(lambda: (show_result(msg, "#e53935"), done()))
            return
        if h is None:
            return
        if want:
            ok = h == want
            ui(lambda: (show_result("✔ Match: the file is intact" if ok else "✖ Does NOT match: the file is damaged or different",
                                    GREEN if ok else "#e53935", h), done()))
        else:
            ui(lambda: (show_result(f"{algo.upper()} checksum:", "gray", h), done()))

    def done():
        state["busy"] = False
        verify_btn.configure(state="normal")

    def start():
        if state["busy"]:
            return
        want, detected = extract_hash(expected.get())
        if expected.get().strip() and not want:
            show_result("That is not a valid MD5 / SHA-1 / SHA-256 / SHA-512 checksum.", "#FF9800")
            return
        choice = algo_var.get()
        algo = detected if (choice == "Auto" and detected) else ALGOS.get(choice, "sha256")
        if want and choice != "Auto" and ALGOS.get(choice) != detected:
            show_result(f"This checksum looks like {detected.upper()}, not {choice}. Choose Auto or {detected.upper()}.", "#FF9800")
            return
        state["busy"] = True
        verify_btn.configure(state="disabled")
        bar.set(0)
        show_result("Checking...", "gray")
        threading.Thread(target=work, args=(algo, want), daemon=True).start()

    def copy_hash():
        v = got.get()
        if v:
            gui.root.clipboard_clear()
            gui.root.clipboard_append(v)

    row = ctk.CTkFrame(win, fg_color="transparent")
    row.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=16)
    verify_btn = ctk.CTkButton(row, text="Verify", fg_color=GREEN, hover_color=GREEN_H, height=36, width=110, command=start)
    verify_btn.pack(side=tk.RIGHT)
    ctk.CTkButton(row, text="Copy result", fg_color="gray40", height=36, width=110, command=copy_hash).pack(side=tk.RIGHT, padx=8)
    expected.bind("<Return>", lambda e: start())
    expected.focus_set()


# ----------------------------------------------------------------------------
# استيرادات متبادلة مع وحدات تانية (بتتحط في الآخر عشان تتفادى مشاكل الاستيراد الدائري)
from aerograb.engine import refresh_task_link  # noqa: E402
from aerograb.views.mainwin import _selected_ids  # noqa: E402
