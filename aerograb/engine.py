# -*- coding: utf-8 -*-
import os
import threading
import logging, logging.handlers
import re
import shutil
import subprocess
import time
from aerograb.common import get_setting, log_error
from aerograb.clipwork import CLIP_SEG, clear as clip_clear, complete_count, concat_segments, read_meta, workdir, write_meta
from aerograb import partsdir, usage
from aerograb.config import HOME, USER_AGENT
from aerograb.downloader import convert_to_h264, native_download, probe_video_codec
from aerograb.files import _related_files, _tls, delete_task_files, get_connections, is_transient_error
from aerograb.fmt import (
    QUALITY_MAP,
    fmt_bytes,
    fmt_eta,
    fmt_pct,
    fmt_speed,
    friendly_error,
    is_direct_file_url,
    is_valid_url,
    stream_size,
)
from aerograb.lazyviews import apply_layout, filter_tasks, on_task_completed, open_path, reveal_in_folder
from aerograb.limits import (
    category_dir,
    get_default_quality_safe,
    limiter,
    schedule_allows,
    schedule_wait_text,
    speed_limit_kbps,
)
from aerograb.mediainfo import fmt_hms
from aerograb.netutil import custom_user_agent
from aerograb.rangeproxy import RangeProxy
from aerograb.state import ACTIVE_STATUSES, Run, TaskAbort, tasks, tasks_lock, ui
from aerograb.tools import _NOWIN, YT_CLIENT_FALLBACKS, base_ydl_opts, ensure_js_for, find_ffmpeg, format_for, h264_enabled, h264_encoder_args
from aerograb.ytdlp_mgr import ensure_ytdlp
from aerograb.uistate import gui


# ----------------------------------------------------------------------------- Download logic
def start_single_download(url, q_text, item_id=None, save_path=None, referer="", direct=False, cookie="", ua="", extra=None):
    """main thread فقط."""
    url = (url or "").strip()
    if item_id is None and not is_valid_url(url):
        gui.messagebox.showwarning("Invalid URL", "Please enter a valid URL starting with http:// or https://")
        return
    if q_text not in QUALITY_MAP:
        q_text = get_default_quality_safe()

    if item_id is None:
        save_path = save_path or gui.download_path_var.get() or os.path.join(HOME, "Downloads")
        try:
            os.makedirs(save_path, exist_ok=True)
            if not os.access(save_path, os.W_OK):
                raise PermissionError("folder is not writable")
        except Exception as e:
            gui.messagebox.showerror("Save folder problem", f"Cannot use this folder:\n{save_path}\n\n{e}")
            return
        extra = dict(extra or {})
        ck = (extra.get("clip_start"), extra.get("clip_end"))
        with tasks_lock:
            same = [t for t in tasks.values() if t["url"] == url and (t.get("clip_start"), t.get("clip_end")) == ck]
            dup_active = any(t["status"] in ACTIVE_STATUSES for t in same)
            is_repeat = any(t["status"] in ("completed", "deleted", "canceled", "error", "paused") for t in same)
        if dup_active:
            if not _batch["on"]:
                gui.messagebox.showinfo("Already Exists", "This URL is already in the download queue.")
            return
        if is_repeat and not _batch["on"] and not gui.messagebox.askyesno(
                "⚠️ Duplicate Download", "This video has already been downloaded before.\nDo you want to download it again?"):
            return
        t = new_task(url, q_text, save_path, is_repeat, referer, direct=direct, cookie=cookie, ua=ua, **extra)
        from aerograb.views.statusicons import tree_image
        item_id = gui.tree.insert("", "end", values=task_values(t), tags=(), image=tree_image("queued"))
        with tasks_lock:
            tasks[item_id] = t
        gui.tree.see(item_id)
        if gui.cards is not None:
            gui.cards.want_see = item_id
    else:
        with tasks_lock:
            t = tasks.get(item_id)
            if not t:
                return
            if t["status"] in ACTIVE_STATUSES:
                return
            url, q_text = t["url"], t["quality"]
            if not t.get("save_path"):
                t["save_path"] = gui.download_path_var.get() or os.path.join(HOME, "Downloads")
        try:
            os.makedirs(t["save_path"], exist_ok=True)
        except Exception as e:
            gui.messagebox.showerror("Save folder problem", f"Cannot use this folder:\n{t['save_path']}\n\n{e}")
            return

    run = Run()
    with tasks_lock:
        t = tasks[item_id]
        t["run"] = run
        t["dismissed"] = False
        t["status"] = "queued"
        t["status_text"] = "Queued..."
        t["speed"] = t["eta"] = "-"
    refresh_row(item_id)
    if not _batch["on"]:
        save_history()
        filter_tasks(gui.current_filter)
    threading.Thread(target=download_worker, args=(item_id, run, url, q_text), daemon=True).start()



def describe_formats(fmts):
    """وصف مختصر للصيغة اللي اتختارت فعلاً، مثلاً "1080p" أو "Audio · m4a"."""
    try:
        v = next((f for f in fmts if (f.get("vcodec") or "none") != "none"), None)
        if v is None:
            a = next(iter(fmts), {})
            abr = a.get("abr")
            return "Audio · " + (a.get("ext") or "") + (f" · {int(abr)}k" if abr else "")
        h = v.get("height")
        fps = v.get("fps")
        return " · ".join(x for x in (f"{h}p" if h else "", f"{int(fps)}fps" if fps and fps > 30 else "") if x)      # الجودة بس (من غير اسم الكودك)
    except Exception:
        return ""



def run_clip_download(y, url, q_text, referer, save_path, name_prefix, clip_s, clip_e, precise, tag, check_abort, on_update, ffmpeg,
                      work_key=None):
    """غلاف: بيشغّل وسيط الاتصالات المتعددة (rangeproxy) طول مدة القص ويقفله في الآخر."""
    proxy = None
    try:
        conns = get_connections()
        if conns > 1 and get_setting("clip_multi_conn", True):
            proxy = RangeProxy(conns)
    except Exception as e:
        log_error("range proxy start", e)
        proxy = None
    try:
        return _run_clip_download(y, url, q_text, referer, save_path, name_prefix, clip_s, clip_e, precise, tag, check_abort,
                                  on_update, ffmpeg, work_key, proxy)
    finally:
        if proxy is not None:
            proxy.close()



def _run_clip_download(y, url, q_text, referer, save_path, name_prefix, clip_s, clip_e, precise, tag, check_abort, on_update, ffmpeg,
                       work_key=None, proxy=None):
    """بيقص جزء من فيديو بـ ffmpeg مباشرة من الروابط، وبيبلّغ بنسبة التقدم الحقيقية.
    check_abort() بترمي TaskAbort لو المستخدم وقّف أو لغى. بيرجّع مسار الملف النهائي.
    لما القص بيتم بإعادة ترميز (الوضع الدقيق) الجزء بيتحمّل على شرايح 10 ثواني بتتحفظ، فلو اتعمل Pause أو انقطع
    الاتصال بيكمّل من آخر شريحة مكتملة بدل ما يبدأ من الأول (work_key = مفتاح ثابت للمهمة)."""
    opts = base_ydl_opts()
    opts.update({"skip_download": True, "format": format_for(q_text, True)})
    if referer:
        opts["http_headers"] = {**(opts.get("http_headers") or {}), "Referer": referer}
    on_update(status_text="Reading video info...")
    cookie_hdr = {}
    with y.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        try:                                    # كوكيز yt-dlp (cookies.txt) للروابط اللي هنقرأها
            for f in (info.get("requested_formats") or [info]):
                ck = ydl.cookiejar.get_cookie_header(f["url"])
                if ck:
                    cookie_hdr[f["url"]] = ck
        except Exception:
            pass
    check_abort()
    fmts = info.get("requested_formats") or [info]
    dur = float(info.get("duration") or 0)
    s = float(clip_s or 0)
    e = float(clip_e) if clip_e is not None else (dur or None)
    if dur and e is not None:
        e = min(e, dur)
    if e is not None and e <= s:
        raise RuntimeError("Invalid time range")
    length = (e - s) if e is not None else None
    has_v = any((f.get("vcodec") or "none") != "none" for f in fmts)
    ext = "mp4" if has_v else "m4a"
    title = info.get("title") or "video"
    base = y.utils.sanitize_filename(f"{name_prefix}{title} {tag}".strip(), restricted=False)[:120] or "video"
    out_dir = category_dir(save_path, "x." + ext)
    os.makedirs(out_dir, exist_ok=True)

    def vok(f):
        v = f.get("vcodec") or "none"
        return v == "none" or str(v).startswith(("avc1", "h264"))

    def aok(f):
        a = f.get("acodec") or "none"
        return a == "none" or str(a).startswith("mp4a")

    reencode = bool(precise) or not all(vok(f) and aok(f) for f in fmts)
    resumable = bool(reencode and work_key)

    # ---- هل في شغل قديم نكمّل منه؟ (نفس الرابط ونفس الجزء ونفس الجودة)
    sig = {"url": url, "q": q_text, "s": s, "e": e, "ext": ext}
    done_n, out_path = 0, None
    if resumable:
        meta = read_meta(work_key)
        if meta.get("sig") == sig and meta.get("out"):
            out_path = meta["out"]
            done_n = complete_count(work_key, finished=bool(meta.get("segments_done") or meta.get("clean")))
        else:
            clip_clear(work_key)
    if not out_path:
        out_path, n = os.path.join(out_dir, f"{base}.{ext}"), 1
        while os.path.exists(out_path):
            out_path = os.path.join(out_dir, f"{base} ({n}).{ext}")
            n += 1
    if resumable:
        os.makedirs(workdir(work_key), exist_ok=True)
        write_meta(work_key, {"sig": sig, "out": out_path, "segments_done": False})

    est = 0
    for f in fmts:
        sz = f.get("filesize") or f.get("filesize_approx") or 0
        if not sz and dur and f.get("tbr"):
            sz = int(f["tbr"] * 1000 / 8 * dur)
        est += sz
    if est and dur and length:
        est = int(est * min(1.0, length / dur))
    base_t = float(done_n * CLIP_SEG) if resumable else 0.0
    if length:
        base_t = min(base_t, length)
    first_pct = min(99.0, base_t / length * 100.0) if (length and base_t) else 0.0
    on_update(file_path=out_path, title=title + (f"  ✂ {fmt_hms(s)}–{fmt_hms(e) if e is not None else 'end'}"),
              size=fmt_bytes(est) if est else "Unknown", progress=fmt_pct(first_pct), pct=first_pct,
              status_text=(f"Resuming from {fmt_hms(base_t)}..." if base_t else
                                       ("Cutting precisely (re-encoding)..." if reencode else "Starting ffmpeg...")))

    remaining = (length - base_t) if length else None
    segments_ready = bool(resumable and remaining is not None and remaining <= 0.05)
    run_target = out_path if not resumable else os.path.join(workdir(work_key), "seg_%05d.ts")

    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    maps = []
    all_proxied = True
    for i, f in enumerate(fmts):
        hdrs = dict(f.get("http_headers") or info.get("http_headers") or {})
        hdrs.pop("Accept-Encoding", None)
        src_url = f["url"]
        proxied = bool(proxy) and src_url.startswith(("http://", "https://")) and (f.get("protocol") or "https") in ("http", "https") \
            and not f.get("fragments")
        if proxied:                             # ffmpeg بيقرأ من الوسيط المحلي والوسيط هو اللي بيكلّم السيرفر بعدة اتصالات
            if f["url"] in cookie_hdr and not any(k.lower() == "cookie" for k in hdrs):
                hdrs["Cookie"] = cookie_hdr[f["url"]]
            hdrs.setdefault("User-Agent", custom_user_agent() or USER_AGENT)
            src_url = proxy.add(src_url, hdrs)
        else:
            all_proxied = False
        if not proxied and hdrs:
            cmd += ["-headers", "".join(f"{k}: {v}\r\n" for k, v in hdrs.items())]
        cmd += ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"]
        if s + base_t > 0:
            cmd += ["-ss", f"{s + base_t:.3f}"]
        cmd += ["-i", src_url]
        if (f.get("vcodec") or "none") != "none":
            maps += ["-map", f"{i}:v:0"]
        if (f.get("acodec") or "none") != "none":
            maps += ["-map", f"{i}:a:0"]
    cmd += maps
    if not has_v:
        cmd += ["-vn"]
    if reencode:
        if has_v:
            cmd += [*h264_encoder_args(ffmpeg), "-pix_fmt", "yuv420p"]
            if resumable:
                cmd += ["-force_key_frames", f"expr:gte(t,n_forced*{CLIP_SEG})"]
        cmd += ["-c:a", "aac", "-b:a", "160k"]
    else:
        cmd += ["-c", "copy", "-avoid_negative_ts", "make_zero"]
    if remaining:
        cmd += ["-t", f"{remaining:.3f}"]
    if resumable:
        cmd += ["-f", "segment", "-segment_time", str(CLIP_SEG), "-segment_time_delta", "0.05", "-segment_format", "mpegts", "-reset_timestamps", "1",
                "-segment_start_number", str(done_n)]
    else:
        cmd += ["-movflags", "+faststart"]
    cmd += ["-progress", "pipe:1", "-nostats", run_target]

    def cleanup_after_abort(exc):
        """Pause بيحتفظ بالشرايح المكتملة، واللغاء/الخطأ الغير مؤقت بيمسح كل حاجة."""
        if resumable and (not isinstance(exc, TaskAbort) or getattr(exc, "kind", "") == "pause"):
            # Pause (أو خطأ مؤقت): بنحتفظ بالشرايح المكتملة ونمسح الأخيرة الناقصة بس، ونعلّم إن الحالة نضيفة
            complete_count(work_key, finished=False)
            write_meta(work_key, {"sig": sig, "out": out_path, "segments_done": False, "clean": True})
        else:
            if resumable:
                clip_clear(work_key)
            delete_task_files(out_path)

    if not segments_ready:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True,
                                encoding="utf-8", errors="replace", creationflags=_NOWIN)
        st = {"t": 0.0, "size": 0, "speed": 0.0}
        err_tail = []

        def rd_out():
            try:
                for line in proc.stdout:
                    line = line.strip()
                    if line.startswith(("out_time_us=", "out_time_ms=")):
                        try:
                            st["t"] = max(0.0, int(line.split("=", 1)[1]) / 1e6)
                        except ValueError:
                            pass
                    elif line.startswith("total_size="):
                        try:
                            st["size"] = int(line.split("=", 1)[1])
                        except ValueError:
                            pass
                    elif line.startswith("speed="):
                        m = re.match(r"speed=\s*([\d.]+)x", line)
                        st["speed"] = float(m.group(1)) if m else st["speed"]
            except Exception:
                pass

        def rd_err():
            try:
                for line in proc.stderr:
                    err_tail.append(line.strip())
                    del err_tail[:-12]
            except Exception:
                pass

        threads = [threading.Thread(target=rd_out, daemon=True), threading.Thread(target=rd_err, daemon=True)]
        for th in threads:
            th.start()
        def out_bytes():
            """حجم اللي اتكتب فعلاً على القرص (ffmpeg بيرجّع total_size فاضي لما بيكتب شرايح، فالسرعة كانت بتفضل "-")."""
            try:
                if resumable:
                    d = workdir(work_key)
                    return sum(os.path.getsize(os.path.join(d, n)) for n in os.listdir(d) if n.startswith("seg_"))
                return os.path.getsize(out_path) if os.path.exists(out_path) else 0
            except OSError:
                return 0

        base_bytes = out_bytes()
        counted_out = [0]
        last_size, last_ts, bps = 0, time.monotonic(), 0.0
        try:
            while proc.poll() is None:
                check_abort()
                time.sleep(0.25)
                now = time.monotonic()
                st["size"] = max(st["size"], out_bytes() - base_bytes)
                if not all_proxied and st["size"] > counted_out[0]:      # من غير الوسيط مفيش عدّ مباشر: بنقرّبه بحجم اللي اتكتب
                    usage.add(st["size"] - counted_out[0])
                    counted_out[0] = st["size"]
                if now - last_ts >= 0.5:
                    inst = max(0.0, (st["size"] - last_size) / (now - last_ts))
                    bps = inst if not bps else bps * 0.6 + inst * 0.4
                    last_size, last_ts = st["size"], now
                got = base_t + st["t"]
                pct = min(99.0, got / length * 100.0) if length else 0.0
                eta = fmt_eta((length - got) / st["speed"]) if (length and st["speed"] > 0) else "-"
                on_update(status="downloading", pct=pct, progress=fmt_pct(pct), speed=fmt_speed(bps) if bps else "-", eta=eta, bps=bps,
                          size=fmt_bytes(max(est, st["size"])) if (est or st["size"]) else "Unknown",
                          status_text="Downloading the selected part...")
        except BaseException as exc:
            try:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(3)
                    except Exception:
                        proc.kill()
            finally:
                for th in threads:
                    th.join(1)
                cleanup_after_abort(exc)
            raise
        rc = proc.wait()
        for th in threads:
            th.join(2)
        if rc != 0:
            cleanup_after_abort(RuntimeError("ffmpeg"))
            if not resumable:
                delete_task_files(out_path)
            raise RuntimeError(" ".join(x for x in err_tail if x)[-300:] or f"ffmpeg failed (code {rc})")
        if not resumable and (not os.path.exists(out_path) or os.path.getsize(out_path) == 0):
            delete_task_files(out_path)
            raise RuntimeError(" ".join(x for x in err_tail if x)[-300:] or f"ffmpeg failed (code {rc})")

    if resumable:
        total = complete_count(work_key, finished=True)
        if total <= 0:
            raise RuntimeError("ffmpeg produced no data")
        write_meta(work_key, {"sig": sig, "out": out_path, "segments_done": True})
        on_update(status="merging", status_text="Joining the parts...", pct=99.0, progress=fmt_pct(99), speed="-", eta="-")
        try:
            check_abort()
            concat_segments(ffmpeg, work_key, total, out_path, has_v)
        except BaseException as exc:
            cleanup_after_abort(exc)
            raise
        clip_clear(work_key)
    return out_path


def _stem_of(path):
    """اسم الملف من غير امتداد ولا .part ولا .fNNN (عشان نعرف إن ملفين تبع نفس التحميل)."""
    p = re.sub(r"(\.part|\.ytdl|\.temp|\.seg)+$", "", path or "", flags=re.I)
    return re.sub(r"\.f\d[\w-]*$", "", os.path.splitext(p)[0]).lower()



def _move_out_of_temp(path, home_dir):
    """لو yt-dlp مقدرش ينقل الملف الكامل لمجلد التحميل (مثلاً فيه ملف بنفس الاسم)، بننقله إحنا باسم مش مستخدم."""
    base, ext = os.path.splitext(os.path.basename(path))
    dest, n = os.path.join(home_dir, base + ext), 1
    while os.path.exists(dest):
        dest = os.path.join(home_dir, f"{base} ({n}){ext}")
        n += 1
    os.makedirs(home_dir, exist_ok=True)
    shutil.move(path, dest)
    return dest


def _names_reserved_by_others(item_id):
    """أسماء الملفات اللي مهام تانية شغالة/متوقفة عليها. أجزاؤها بقت في مجلد مؤقت مش جنب الملف، فمش هنشوفها في مجلد التحميل."""
    with tasks_lock:
        return {_stem_of(t["file_path"]) for iid, t in tasks.items()
                if iid != item_id and t.get("file_path") and t["status"] in ACTIVE_STATUSES + ("paused", "error")}


def _avoid_name_clash(ydl, pre, mine_paths, reserved=frozenset()):
    """
    فيديوهين مختلفين بنفس العنوان كانوا بيطلعوا بنفس اسم الملف، فـ yt-dlp كان بيقول "already downloaded" ويعدّي التاني
    من غير ما ينزّله (أو الاتنين الشغّالين مع بعض يكتبوا على نفس .part). هنا بنشوف اسم الملف قبل التحميل،
    ولو محجوز لحاجة مش تبع المهمة دي بنضيف (1) (2) ... زي المتصفح.
    """
    try:
        if pre.get("entries"):
            return
        fn = ydl.prepare_filename(pre)
        if not fn:
            return
        mine = {_stem_of(x) for x in mine_paths if x}

        def taken(path):
            return _stem_of(path) in reserved or any(os.path.isfile(x) for x in _related_files(path))

        if _stem_of(fn) in mine or not taken(fn):
            return
        base, ext = os.path.splitext(fn)
        n = 1
        while taken(f"{base} ({n}){ext}"):
            n += 1
        tmpl = ydl.params.get("outtmpl")
        tmpl = tmpl.get("default") if isinstance(tmpl, dict) else tmpl
        suffix = ".%(ext)s"
        if tmpl and tmpl.endswith(suffix):
            ydl.params["outtmpl"] = {"default": tmpl[:-len(suffix)] + f" ({n})" + suffix}
            logging.info(f"file name already used, saving as ({n}): {fn}")
    except Exception as e:
        log_error("avoid_name_clash", e)



def download_worker(item_id, run, url, q_text):
    acquired = False

    def current():
        with tasks_lock:
            t = tasks.get(item_id)
            return t is not None and t.get("run") is run

    def aborted():
        return run.stop.is_set() or run.cancel.is_set() or not current()

    def check_abort():
        if run.cancel.is_set() or not current():
            raise TaskAbort("cancel")
        if run.stop.is_set():
            raise TaskAbort("pause")

    try:
        with tasks_lock:
            t = tasks.get(item_id)
            if not t:
                return
            save_path, is_repeat, referer = t["save_path"], t["is_repeat"], t.get("referer", "")
            t_direct = bool(t.get("direct"))
            prev_path = t.get("file_path")
            cookie, ua = t.get("cookie", ""), t.get("ua", "")
            clip_s, clip_e = t.get("clip_start"), t.get("clip_end")
            clip_precise, name_prefix = bool(t.get("clip_precise", True)), t.get("name_prefix") or ""
            clip_key = t.get("clip_key")
            part_key = t.get("part_key")
            lower_ok = bool(t.get("lower_ok"))
            refreshed = bool(t.pop("link_refreshed", False))
        has_clip = clip_s is not None or clip_e is not None
        clip_suffix = f"  ✂ {fmt_hms(clip_s or 0)}–{fmt_hms(clip_e) if clip_e is not None else 'end'}" if has_clip else ""

        def prio_key():
            with tasks_lock:
                tt = tasks.get(item_id)
                return tt.get("prio", 0) if tt else 0

        if not schedule_allows():
            update_task(item_id, status_text=schedule_wait_text())
        elif not usage.allows():
            update_task(item_id, status_text="📊 Data limit reached: waiting for the next period")
        if not limiter.acquire(aborted, prio_key):
            return
        acquired = True
        if aborted():
            return
        update_task(item_id, status="starting", status_text="Connecting...", speed="-", eta="-")

        y = ensure_ytdlp()
        have_ffmpeg = bool(find_ffmpeg())
        direct = t_direct or is_direct_file_url(url)
        if has_clip and (direct or not have_ffmpeg):
            update_task(item_id, status="error", speed="-", eta="-",
                        status_text="⚠️ Failed: cutting a part needs ffmpeg and a video link (Right-click to retry)")
            save_history()
            return
        stream_sizes, acc = {}, [0]
        n_streams, done_streams, best_pct = [1], [0], [0.0]
        partials = set()
        if prev_path:
            partials.add(prev_path)
        home_dir = category_dir(save_path, "x.m4a" if q_text == "Audio Only" else "x.mp4")
        # الأجزاء غير المكتملة (.part / .fNNN) بتتحط في مجلد مؤقت تابع للبرنامج مش جنب الملف النهائي، فمتتمسحش بالغلط.
        # تحميل اتبدأ بنسخة قديمة وأجزاؤه لسه في مجلد التحميل بيكمّل هناك عشان ميبدأش من الصفر.
        temp_dir = partsdir.workdir(part_key) if (part_key and not partsdir.has_legacy_parts(prev_path)) else None

        def in_temp(path):
            try:
                return bool(temp_dir) and os.path.commonpath([os.path.abspath(path), os.path.abspath(temp_dir)]) == os.path.abspath(temp_dir)
            except ValueError:
                return False
        last_ui = [0.0]
        last_fp = [prev_path]
        final_holder = [None]

        def plan_streams(i):
            """بنحسب حجم الفيديو + الصوت مع بعض قبل ما التحميل يبدأ، عشان الشريط يبقى واحد متصل."""
            if i.get("entries"):
                return
            fmts = i.get("requested_formats") or [i]
            dur = i.get("duration") or 0
            stream_sizes.clear()
            for f in fmts:
                fid = str(f.get("format_id") or "default")
                size, _exact = stream_size(f, dur)
                if not size and dur and f.get("vcodec") == "none":
                    size = int(128 * 1000 / 8 * dur)          # تقدير للصوت لو الحجم مش معروف
                stream_sizes[fid] = size
            if has_clip and dur:
                end_s = min(float(clip_e), float(dur)) if clip_e is not None else float(dur)
                ratio = max(0.0, min(1.0, (end_s - float(clip_s or 0)) / float(dur)))
                for k in stream_sizes:
                    stream_sizes[k] = int(stream_sizes[k] * ratio)
            n_streams[0] = len(fmts)
            total = sum(stream_sizes.values())
            fields = {"resumable": True, "conns": 0, "fmt_desc": describe_formats(fmts)}      # yt-dlp بيكمّل من ملف .part
            th = i.get("thumbnail")
            if th and is_valid_url(th):
                fields["thumb"] = th if "ytimg.com" not in th else (youtube_thumb_url(url) or th)
            update_task(item_id, title=(i.get("title") or url) + clip_suffix, size=fmt_bytes(total) if total > 0 else "Unknown",
                        status_text="Starting download...", **fields)

        counted = {}                         # آخر downloaded_bytes لكل ستريم (لعدّاد الاستهلاك)

        def my_hook(d):
            if run.cancel.is_set() or not current():
                raise TaskAbort("cancel")
            if run.stop.is_set():
                raise TaskAbort("pause")
            status = d.get("status")
            fn = d.get("filename")
            if fn and in_temp(fn):
                fn = os.path.join(home_dir, os.path.basename(fn))          # للمستخدم: مكان الملف النهائي مش المجلد المؤقت
            if fn:
                partials.add(fn)
                if d.get("tmpfilename"):
                    partials.add(d["tmpfilename"])
                if fn != last_fp[0]:
                    last_fp[0] = fn
                    update_task(item_id, file_path=fn)
            info = d.get("info_dict") or {}
            fmt_key = str(info.get("format_id") or fn or "default")
            if not info.get("_ag_counted") and status in ("downloading", "finished"):
                cur_b = d.get("downloaded_bytes") or 0
                prev_b = counted.get(fmt_key)
                if prev_b is not None and cur_b > prev_b:
                    usage.add(cur_b - prev_b)             # أول قراءة بنعتبرها خط البداية (ممكن تبقى جزء متكمّل)
                counted[fmt_key] = cur_b
            if status == "downloading":
                live_total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                if live_total:
                    stream_sizes[fmt_key] = live_total
                now = time.monotonic()
                if now - last_ui[0] < 0.3:
                    return
                last_ui[0] = now
                t_size = sum(stream_sizes.values())
                cur = d.get("downloaded_bytes") or 0
                if t_size > 0:
                    pct = min((acc[0] + cur) / t_size * 100, 100.0)
                elif d.get("fragment_count"):
                    pct = min((d.get("fragment_index") or 0) / d["fragment_count"] * 100, 100.0)
                else:
                    pct = 0.0
                pct = max(pct, best_pct[0])          # الشريط عمره ما يرجع لورا
                best_pct[0] = pct
                is_audio = info.get("vcodec") == "none" and info.get("acodec") not in (None, "none")
                kind = "audio" if is_audio else "video"
                if has_clip:
                    text = "Downloading the selected part..."
                elif n_streams[0] > 1:
                    text = f"Downloading {kind} ({done_streams[0] + 1}/{n_streams[0]})..."
                else:
                    text = "Downloading..."
                update_task(item_id, status="downloading", title=(info.get("title") or url) + clip_suffix,
                            size=fmt_bytes(t_size) if t_size > 0 else "Unknown",
                            speed=fmt_speed(d.get("speed")), eta=fmt_eta(d.get("eta")), bps=d.get("speed") or 0,
                            progress=fmt_pct(pct), pct=pct, status_text=text)
            elif status == "finished":
                file_bytes = d.get("total_bytes") or d.get("total_bytes_estimate") or d.get("downloaded_bytes") or 0
                if file_bytes:
                    stream_sizes[fmt_key] = file_bytes
                acc[0] += file_bytes
                done_streams[0] += 1

        def pp_hook(d):
            pp = d.get("postprocessor")
            if d.get("status") == "started":
                if pp == "Merger":
                    update_task(item_id, status="merging", speed="-", eta="-", progress=fmt_pct(100), pct=100.0,
                                status_text="Merging (Video + Audio)...")
                elif pp == "EmbedThumbnail":
                    update_task(item_id, speed="-", eta="-", progress=fmt_pct(100), pct=100.0,
                                status_text="Embedding Thumbnail...")
            elif d.get("status") == "finished":
                fp = (d.get("info_dict") or {}).get("filepath")
                if fp:
                    final_holder[0] = fp

        tag = ""
        if has_clip:
            tag += "[" + fmt_hms(clip_s or 0).replace(":", ".") + "-" + (fmt_hms(clip_e).replace(":", ".") if clip_e is not None else "end") + "]"
        if is_repeat:
            safe_q = re.sub(r'[\\/:*?"<>|]', "_", q_text or "")
            tag += f"[{safe_q}]"
        prefix = re.sub(r"[^\w .()\-]", "", name_prefix).replace("%", "")
        outtmpl = f"{prefix}%(title)s{(' ' + tag) if tag else ''}.%(ext)s"

        fmt_state = {"client": 0}          # مجموعة عملاء يوتيوب البديلة (لو الصيغ ماجتش) - الجودة ثابتة دايماً

        def build_opts(use_thumb):
            o = base_ydl_opts()
            o.update({
                "format": "best" if direct else format_for(q_text, have_ffmpeg, lower_ok=lower_ok),
                "paths": {"home": home_dir, **({"temp": temp_dir} if temp_dir else {})},
                "outtmpl": outtmpl,
                "merge_output_format": "mp4",
                "continuedl": True, "ignoreerrors": False,
                "progress_hooks": [my_hook], "postprocessor_hooks": [pp_hook],
                "retries": 15, "fragment_retries": 15, "socket_timeout": 30,
                "concurrent_fragment_downloads": max(4, min(16, get_connections())), "trim_file_name": 120,      # أجزاء HLS/DASH بالتوازي (حسب عدد الاتصالات في الإعدادات)
            })
            if find_ffmpeg():
                o["ffmpeg_location"] = find_ffmpeg()
            clients = YT_CLIENT_FALLBACKS[fmt_state["client"]]
            if clients and not direct:
                ea = dict(o.get("extractor_args") or {})
                ea["youtube"] = dict(ea.get("youtube") or {}, player_client=list(clients))
                o["extractor_args"] = ea
            if referer:
                o["http_headers"] = {**(o.get("http_headers") or {}), "Referer": referer}      # الكوكيز والـ User-Agent للتحميل المباشر بس (yt-dlp بيدير بتوعه بنفسه)
            if speed_limit_kbps():
                o["ratelimit"] = speed_limit_kbps() * 1024      # لما بيشتغل downloader بتاع yt-dlp العادي (HLS مثلاً)
            if use_thumb:
                o["writethumbnail"] = True
                o["postprocessors"] = [{"key": "FFmpegThumbnailsConvertor", "format": "jpg"}, {"key": "EmbedThumbnail"}]
            return o

        use_thumb_first = have_ffmpeg and not direct
        if not direct:
            ensure_js_for(url, lambda txt: update_task(item_id, status="starting", status_text=txt))     # يوتيوب محتاج مشغّل JavaScript
        MAX_AUTO_RETRIES = max(0, min(10, int(get_setting("auto_retries", 2))))
        attempt = 0
        while True:
            outcome = ("error", "Unknown Error")
            raw_msg = ""
            try:
                if direct:
                    def on_name(title, final_path, total, conns, ranged=None):
                        update_task(item_id, title=title, file_path=final_path, resumable=bool(ranged), conns=int(conns),
                                    size=fmt_bytes(total) if total else "Unknown", status="downloading",
                                    status_text=f"Downloading ({conns} connections)..." if conns > 1 else "Downloading...")

                    def on_progress(done, total, speed):
                        pct = min(done / total * 100, 100.0) if total else 0.0
                        eta = fmt_eta((total - done) / speed) if (total and speed) else "-"
                        update_task(item_id, status="downloading", speed=fmt_speed(speed), eta=eta, bps=speed,
                                    progress=fmt_pct(pct), pct=pct,
                                    size=fmt_bytes(total) if total else fmt_bytes(done))

                    final = native_download(url, save_path, referer, run, prev_path, on_name, on_progress, cookie=cookie, ua=ua, refreshed=refreshed)
                    outcome = ("completed", final)
                elif has_clip:
                    final = run_clip_download(y, url, q_text, referer, save_path, prefix, clip_s, clip_e, clip_precise, tag,
                                              check_abort, lambda **kw: update_task(item_id, **kw), find_ffmpeg(), work_key=clip_key)
                    outcome = ("completed", final)
                else:
                    info = None
                    for use_thumb in ([True, False] if use_thumb_first else [False]):
                        try:
                            acc[0] = 0
                            done_streams[0] = 0
                            update_task(item_id, status_text="Reading video info...")
                            with y.YoutubeDL(build_opts(use_thumb)) as ydl:
                                pre = ydl.extract_info(url, download=False)      # تحليل أول (بنعرف حجم الفيديو والصوت)
                                if run.cancel.is_set() or not current():
                                    raise TaskAbort("cancel")
                                if run.stop.is_set():
                                    raise TaskAbort("pause")
                                plan_streams(pre)
                                _avoid_name_clash(ydl, pre, set(partials) | {prev_path, last_fp[0]}, _names_reserved_by_others(item_id))
                                info = ydl.process_ie_result(pre, download=True)
                            break
                        except Exception as ex:
                            # لو زرع الصورة المصغرة فشل نعيد المحاولة من غيره (الملفات اتحمّلت فعلاً فالإعادة سريعة)
                            if use_thumb and "Postprocessing" in str(ex) and not isinstance(ex, TaskAbort):
                                logging.info(f"thumbnail postprocess failed, retrying without: {ex}")
                                continue
                            raise
                    final = None

                    def pick(i):
                        if not i:
                            return None
                        for e in (i.get("entries") or []):
                            p = pick(e)
                            if p:
                                return p
                        for r in (i.get("requested_downloads") or []):
                            if r.get("filepath"):
                                return r["filepath"]
                        return i.get("filepath")

                    final = pick(info) or final_holder[0]
                    if not (final and os.path.exists(final)) and final_holder[0] and os.path.exists(final_holder[0]):
                        final = final_holder[0]
                    if final and os.path.exists(final) and in_temp(final):
                        final = _move_out_of_temp(final, home_dir)         # الملف الكامل ميفضلش في المجلد المؤقت أبداً
                    if not (final and os.path.exists(final)):
                        raise RuntimeError("Download finished but the file was not found in the save folder")
                    if (h264_enabled() and q_text != "Audio Only" and final and os.path.exists(final) and find_ffmpeg()):
                        codec = probe_video_codec(final)
                        if codec and codec != "h264":
                            logging.info(f"video codec is {codec}, converting to H.264: {final}")
                            update_task(item_id, status="merging", speed="-", eta="-", progress=fmt_pct(100), pct=100.0,
                                        status_text="Converting to H.264 (compatibility)...")
                            final = convert_to_h264(final, run)
                    outcome = ("completed", final)
            except TaskAbort as ab:
                outcome = (ab.kind, None)
            except Exception as ex:
                msg = str(ex)
                raw_msg = msg
                if "USER_CANCELED" in msg:
                    outcome = ("cancel", None)
                elif "USER_PAUSED" in msg:
                    outcome = ("pause", None)
                else:
                    log_error(f"download_worker url={url}", ex)
                    outcome = ("error", friendly_error(msg))

            # "الجودة غير متاحة": ممكن تكون ناقصة بسبب عميل يوتيوب الحالي، فنجرّب عملاء بديلين بنفس الجودة بالظبط (من غير تغيير الجودة أبداً)
            if (outcome[0] == "error" and not direct and not aborted() and "requested format is not available" in raw_msg.lower()
                    and fmt_state["client"] < len(YT_CLIENT_FALLBACKS) - 1):
                fmt_state["client"] += 1
                logging.info(f"format not available for {url}: retrying with client set {fmt_state['client']} (same quality)")
                update_task(item_id, status="starting", speed="-", eta="-", status_text="Trying another method...")
                continue

            # أخطاء مؤقتة (403 / 429 / انقطاع): نعيد المحاولة تلقائياً برابط جديد وبعدد اتصالات أقل ونكمّل من اللي اتحمّل
            if outcome[0] == "error" and attempt < MAX_AUTO_RETRIES and is_transient_error(raw_msg) and not aborted():
                attempt += 1
                base_conns = max(2, int(get_setting("connections", 8)))
                _tls.conn_override = max(2, base_conns // (2 ** attempt))
                logging.info(f"auto-retry {attempt}/{MAX_AUTO_RETRIES} for {url} ({friendly_error(raw_msg)}), "
                             f"connections={_tls.conn_override}")
                update_task(item_id, status="starting", speed="-", eta="-",
                            status_text=f"Retrying ({attempt}/{MAX_AUTO_RETRIES}) after: {friendly_error(raw_msg)}")
                for _ in range(int(3 * attempt / 0.25)):
                    if aborted():
                        break
                    time.sleep(0.25)
                if aborted():
                    break
                continue
            break

        if not current():
            return          # محاولة أحدث خدت مكاننا
        kind, extra = outcome
        if kind != "completed":
            if run.cancel.is_set():
                kind = "cancel"
            elif run.stop.is_set() and kind != "error":
                kind = "pause"

        if kind == "cancel":
            with tasks_lock:
                fp = tasks[item_id].get("file_path") if item_id in tasks else None
            delete_task_files(fp, *partials)
            partsdir.clear(part_key)
            update_task(item_id, status="canceled", status_text="Canceled and deleted", speed="-", eta="-")
        elif kind == "pause":
            update_task(item_id, status="paused", status_text="Paused", speed="-", eta="-")
        elif kind == "completed":
            fields = {"status": "completed", "status_text": "Completed successfully", "progress": fmt_pct(100),
                      "pct": 100.0, "speed": "-", "eta": "-"}
            if extra and os.path.exists(extra):
                fields["file_path"] = extra
                fields["size"] = fmt_bytes(os.path.getsize(extra))
            update_task(item_id, **fields)
            partsdir.clear(part_key)
            ui(on_task_completed, item_id)
        else:
            update_task(item_id, status="error", speed="-", eta="-",
                        status_text=f"⚠️ Failed: {extra} (Right-click to retry)")
        save_history()
    except Exception as outer:
        log_error(f"download_worker outer url={url}", outer)
        if current():
            update_task(item_id, status="error", speed="-", eta="-",
                        status_text="⚠️ Unexpected error (Right-click to retry)")
            save_history()
    finally:
        _tls.conn_override = None
        if acquired:
            limiter.release()



# ---- أوامر التحكم
def _selected_ids():
    from aerograb.views.mainwin import _sel_src   # استيراد كسول: الواجهة متتحمّلش إلا لما تتفتح
    if _sel_src["v"] == "cards" and gui.cards is not None:
        ids = [i for i in gui.cards.selected() if i in tasks]
        if ids:
            return ids
    return [i for i in gui.tree.selection() if i in tasks]



def set_selected(ids):
    from aerograb.views.mainwin import _sel_src   # استيراد كسول: الواجهة متتحمّلش إلا لما تتفتح
    if _sel_src["v"] == "cards" and gui.cards is not None:
        gui.cards.select(ids)
    else:
        gui.tree.selection_set([i for i in ids if gui.tree.exists(i)])



def pause_task(iid):
    with tasks_lock:
        t = tasks.get(iid)
        if not t or t["status"] not in ACTIVE_STATUSES or not t.get("run"):
            return
        t["run"].stop.set()
        was_queued = t["status"] == "queued"
    if was_queued:
        update_task(iid, status="paused", status_text="Paused", speed="-", eta="-")
    else:
        update_task(iid, status_text="Pausing...")



def cancel_task(iid):
    with tasks_lock:
        t = tasks.get(iid)
        if not t or t["status"] not in ACTIVE_STATUSES + ("paused", "error"):
            return
        status = t["status"]
        run = t.get("run")
        fp = t.get("file_path")
        ck = t.get("clip_key")
        pk = t.get("part_key")
    if run and status in ACTIVE_STATUSES:
        run.cancel.set()
    if status in ("starting", "downloading", "merging"):
        update_task(iid, status="canceled", status_text="Canceling...", speed="-", eta="-")   # الـ worker هو اللي يمسح الملفات ويخلّص
    else:
        delete_task_files(fp)
        clip_clear(ck)                      # شرايح الاستكمال المحفوظة بتتمسح مع الإلغاء
        partsdir.clear(pk)                  # وأجزاء الفيديو المؤقتة كمان
        update_task(iid, status="canceled", status_text="Canceled and deleted", speed="-", eta="-")



def resume_task(iid, include_canceled=False):
    with tasks_lock:
        t = tasks.get(iid)
        ok = t and (t["status"] in ("paused", "error") or (include_canceled and t["status"] == "canceled"))
    if ok:
        start_single_download(None, None, item_id=iid)



def pause_all_tasks():
    for iid in list(tasks):
        pause_task(iid)



def refresh_task_link(iid, new_url):
    """يبدّل رابط تحميل (انتهت صلاحيته مثلاً) ويكمّل من الجزء اللي اتحمّل. بيرجّع (True, "") أو (False, سبب)."""
    new_url = (new_url or "").strip()
    if not is_valid_url(new_url):
        return False, "Enter a valid link starting with http:// or https://"
    with tasks_lock:
        t = tasks.get(iid)
        if not t:
            return False, "Download not found"
        if t["status"] in ACTIVE_STATUSES:
            return False, "Pause the download first, then refresh its link"
        if t["status"] in ("completed", "deleted"):
            return False, "This download is already finished"
        t["url"] = new_url
        t["link_refreshed"] = True
    update_task(iid, status_text="New link saved, resuming...")
    save_history()
    start_single_download(None, None, item_id=iid)
    return True, ""


def resume_all_tasks():
    for iid in list(tasks):
        resume_task(iid)



def cancel_all_tasks():
    if not gui.messagebox.askyesno("Confirm Cancel All", "Are you sure you want to cancel ALL downloads?"):
        return
    for iid in list(tasks):
        cancel_task(iid)
    save_history()



def pause_selected():
    for iid in _selected_ids():
        pause_task(iid)



def resume_selected():
    for iid in _selected_ids():
        resume_task(iid, include_canceled=True)



def cancel_selected():
    for iid in _selected_ids():
        cancel_task(iid)
    save_history()



def remove_selected():
    remove_tasks(_selected_ids())



def remove_tasks(ids):
    if not ids:
        return
    if get_setting("confirm_remove", True) and not gui.messagebox.askyesno(
            "Confirm Remove", "Remove the selected item(s) from the list?\n(Downloaded files are kept.)"):
        return
    for iid in ids:
        with tasks_lock:
            t = tasks.get(iid)
            run, status, fp = (t.get("run"), t["status"], t.get("file_path")) if t else (None, None, None)
            ck = t.get("clip_key") if t else None
            pk = t.get("part_key") if t else None
        if status in ACTIVE_STATUSES and run:
            run.cancel.set()
        if status in ACTIVE_STATUSES + ("paused", "error"):
            delete_task_files(fp)
            clip_clear(ck)
            partsdir.clear(pk)
        with tasks_lock:
            tasks.pop(iid, None)
        if gui.tree.exists(iid):
            gui.tree.delete(iid)
    save_history()
    apply_layout()



def delete_file_from_disk_selected():
    ids = _selected_ids()
    if not ids:
        return
    if get_setting("confirm_delete_file", True) and not gui.messagebox.askyesno(
            "⚠️ Delete From Device",
            "This will PERMANENTLY delete the downloaded file(s) from your device.\nThis cannot be undone. Continue?"):
        return
    for iid in ids:
        with tasks_lock:
            t = tasks.get(iid)
            if not t:
                continue
            status, fp, run = t["status"], t.get("file_path"), t.get("run")
        if status in ACTIVE_STATUSES:
            cancel_task(iid)        # الـ worker بيمسح ملفاته بنفسه
            continue
        deleted = delete_task_files(fp) if fp else False
        update_task(iid, status="deleted", speed="-", eta="-",
                    status_text="🗑️ Deleted from device" if deleted else "⚠️ File not found on device")
    save_history()



def open_selected_file():
    for iid in _selected_ids()[:1]:
        fp = tasks[iid].get("file_path")
        if tasks[iid]["status"] == "completed" and fp and os.path.exists(fp):
            open_path(fp)
        else:
            gui.messagebox.showinfo("Not available", "The file is not downloaded yet (or was moved/deleted).")



def open_selected_folder():
    for iid in _selected_ids()[:1]:
        reveal_in_folder(tasks[iid].get("file_path"), tasks[iid].get("save_path"))



def clear_list():
    with tasks_lock:
        active = [i for i, t in tasks.items() if t["status"] in ACTIVE_STATUSES]
    msg = "Clear the list? (Downloaded files will not be deleted)"
    if active:
        msg = "There are active downloads. Cancel them and clear the list?\n(Downloaded files will not be deleted)"
    if not gui.messagebox.askyesno("Confirm", msg):
        return
    for iid in active:
        cancel_task(iid)
    for i in gui.tree.get_children(""):
        gui.tree.delete(i)
    with tasks_lock:
        tasks.clear()
    save_history()
    apply_layout(force=True)


# ----------------------------------------------------------------------------
# استيرادات متبادلة مع وحدات تانية (بتتحط في الآخر عشان تتفادى مشاكل الاستيراد الدائري)
from aerograb.tasks import (
    _batch,
    new_task,
    refresh_row,
    save_history,
    task_values,
    update_task,
    youtube_thumb_url,
)  # noqa: E402
