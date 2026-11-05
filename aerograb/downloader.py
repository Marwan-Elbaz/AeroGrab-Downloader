# -*- coding: utf-8 -*-
import os
import json
import shutil
import urllib.request, urllib.parse, urllib.error
import threading
import logging, logging.handlers
import re
import subprocess
import time
import http.client
import mimetypes
from aerograb.common import log_error
from aerograb.config import IS_WINDOWS, USER_AGENT
from aerograb.files import SEG_MIN_TOTAL, get_connections
from aerograb import usage
from aerograb.limits import category_dir, rate_limiter
from aerograb.netutil import _host, _urlopen, custom_user_agent, site_auth_header
from aerograb.state import TaskAbort
from aerograb.tools import find_ffmpeg


class SegFallback(Exception):
    """التجزئة مش مناسبة للرابط ده (السيرفر مش بيدعم Range مثلاً): نرجع للتحميل العادي."""



class _NoRange(Exception):
    pass



_WIN_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def _safe_filename(name):
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name or "").strip(" .")
    if len(name) > 150:                         # نقص الاسم من غير ما نضيّع الامتداد
        stem, ext = os.path.splitext(name)
        ext = ext[:12]
        name = stem[:150 - len(ext)].rstrip(" .") + ext
    if os.path.splitext(name)[0].lower() in _WIN_RESERVED:
        name = "_" + name                       # CON / NUL / COM1 ... أسماء محجوزة في ويندوز
    return name



def _name_from_response(url, headers):
    cd = headers.get("Content-Disposition") or ""
    m = re.search(r"filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)", cd) or re.search(r'filename\s*=\s*"?([^";]+)"?', cd, re.I)
    raw = urllib.parse.unquote(m.group(1).strip()) if m else urllib.parse.unquote(os.path.basename(urllib.parse.urlparse(url).path))
    name = _safe_filename(raw) or "download"
    if not os.path.splitext(name)[1]:
        ctype = (headers.get("Content-Type") or "").split(";")[0].strip()
        name += mimetypes.guess_extension(ctype) or ""
    return name



_reserved = set()

_reserved_lock = threading.Lock()


def _release_path(path):
    with _reserved_lock:
        _reserved.discard(os.path.normcase(os.path.abspath(path)) if path else path)


def _unique_path(folder, name, prefer=None):
    """اسم ملف غير مستخدم. بنعتبر الاسم محجوز لو فيه ملف نهائي أو .part/.seg لتحميل تاني، أو تاسك شغال عليه دلوقتي
    (من غير كده تحميلين بنفس الاسم كانوا بيكتبوا على نفس الملف)."""
    with _reserved_lock:
        if prefer and os.path.dirname(os.path.abspath(prefer)) == os.path.abspath(folder) \
                and not os.path.exists(prefer) and (os.path.exists(prefer + ".part") or os.path.exists(prefer + ".part.seg")):
            _reserved.add(os.path.normcase(os.path.abspath(prefer)))
            return prefer                       # نكمّل نفس الملف الجزئي بتاع نفس التاسك
        stem, ext = os.path.splitext(name)
        i = 0
        while True:
            cand = os.path.join(folder, name if i == 0 else f"{stem} ({i}){ext}")
            key = os.path.normcase(os.path.abspath(cand))
            if key not in _reserved and not os.path.exists(cand) and not os.path.exists(cand + ".part") \
                    and not os.path.exists(cand + ".part.seg"):
                _reserved.add(key)
                return cand
            i += 1



def _http_probe_range(url, headers, timeout=25):
    """طلب Range صغير (بايت واحد): بيرجّع الاسم والحجم الكلي وهل السيرفر بيدعم التجزئة."""
    h = dict(headers)
    h["Range"] = "bytes=0-0"
    info = {"name": None, "total": 0, "ranged": False, "validator": "", "final_url": url}
    try:
        resp = _urlopen(urllib.request.Request(url, headers=h), timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code != 416:
            raise
        h.pop("Range")                      # ملف فاضي أو Range مش مقبول: نجرب طلب عادي
        resp = _urlopen(urllib.request.Request(url, headers=h), timeout=timeout)
    try:
        hd = resp.headers
        info["final_url"] = resp.geturl() or url
        info["name"] = _name_from_response(info["final_url"], hd)
        info["validator"] = hd.get("ETag") or hd.get("Last-Modified") or ""
        if resp.status == 206:
            tail = (hd.get("Content-Range") or "").rsplit("/", 1)[-1]
            if tail.isdigit():
                info["total"], info["ranged"] = int(tail), True
        else:
            cl = hd.get("Content-Length")
            info["total"] = int(cl) if cl and cl.isdigit() else 0
    finally:
        resp.close()
    return info



def _write_json_quiet(path, data):
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except Exception as e:
        logging.info(f"could not save segment state: {e}")



def segmented_fetch(url, headers, total, part_path, connections, on_progress, check_abort=None,
                    chunk_hint=None, validator="", orig_url=None):
    """تحميل الملف على أجزاء بعدة اتصالات متوازية (زي IDM) مع استكمال بعد الإيقاف.
    الملف بيتحجز بحجمه الكامل في part_path، وحالة كل جزء بتتحفظ في part_path + '.seg'."""
    seg_path = part_path + ".seg"
    n_conn = max(2, min(16, connections))
    chunk = max(1 << 20, min(32 << 20, total // (n_conn * 4) or 1))
    if chunk_hint:
        chunk = max(1 << 20, min(chunk, int(chunk_hint)))
    done = None
    try:
        if os.path.exists(seg_path) and os.path.exists(part_path):
            with open(seg_path, "r", encoding="utf-8") as f:
                st = json.load(f)
            v_ok = (not validator) or (not st.get("validator")) or st.get("validator") == validator
            if st.get("v") == 1 and st.get("total") == total and v_ok and os.path.getsize(part_path) == total:
                chunk = int(st["chunk"])
                done = [int(x) for x in st["done"]]
    except Exception as e:
        logging.info(f"segment state unreadable, restarting: {e}")
        done = None
    nchunks = (total + chunk - 1) // chunk
    if done is None or len(done) != nchunks:
        for f in (part_path, seg_path):
            try:
                os.remove(f)
            except OSError:
                pass
        folder = os.path.dirname(os.path.abspath(part_path))
        if shutil.disk_usage(folder).free < total + (16 << 20):
            raise OSError(28, "No space left on device")
        with open(part_path, "wb") as f:
            f.truncate(total)                 # حجز المساحة كاملة (بيمنع ملف نص-مكتوب لو الديسك اتملى)
        done = [0] * nchunks

    def clen(i):
        return min(chunk, total - i * chunk)

    lock = threading.Lock()
    abort = threading.Event()
    claimed = set()
    errors = []
    cur_url = [url]

    def pick():
        with lock:
            for i in range(nchunks):
                if i not in claimed and done[i] < clen(i):
                    claimed.add(i)
                    return i
        return None

    def fetch_chunk(f, i):
        tries = 0
        while not abort.is_set():
            start = i * chunk + done[i]
            end = i * chunk + clen(i) - 1
            if start > end:
                return
            got = 0
            try:
                h = dict(headers)
                h["Range"] = f"bytes={start}-{end}"
                if _host(cur_url[0]) != _host(orig_url or url):
                    h.pop("Cookie", None)           # الكوكيز وبيانات الدخول متتبعتش لدومين تاني (CDN بعد تحويل)
                    h.pop("Authorization", None)
                resp = _urlopen(urllib.request.Request(cur_url[0], headers=h), timeout=20)
                try:
                    if resp.status != 206:
                        raise _NoRange()
                    if not (resp.headers.get("Content-Range") or "").startswith(f"bytes {start}-"):
                        raise IOError("server returned the wrong range")
                    f.seek(start)
                    while not abort.is_set():
                        data = resp.read(262144)
                        if not data:
                            break
                        if abort.is_set():
                            return
                        rate_limiter.consume(len(data), abort.is_set)
                        if abort.is_set():
                            return
                        f.write(data)
                        got += len(data)
                        usage.add(len(data))
                        with lock:
                            done[i] += len(data)
                finally:
                    resp.close()
                if done[i] >= clen(i):
                    return
                raise IOError("connection closed early")
            except urllib.error.HTTPError as e:
                if e.code in (401, 403, 410) and orig_url and cur_url[0] != orig_url:
                    cur_url[0] = orig_url           # رابط التحويل انتهت صلاحيته: نرجع للأصلي
                    continue
                if e.code == 403 and tries < 2:
                    tries += 1
                    time.sleep(1.5 * tries)
                    continue
                if e.code in (429, 500, 502, 503, 504):
                    tries = 0 if got else tries + 1
                    if tries > 6:
                        raise
                    time.sleep(min(2 * tries, 8))
                    continue
                raise
            except _NoRange:
                raise
            except (OSError, http.client.HTTPException) as e:
                if getattr(e, "errno", None) == 28:
                    raise
                tries = 0 if got else tries + 1
                if tries > 6:
                    raise
                time.sleep(min(2 * tries, 8))

    def worker():
        f = None
        try:
            f = open(part_path, "r+b", buffering=0)
            while not abort.is_set():
                i = pick()
                if i is None:
                    return
                try:
                    fetch_chunk(f, i)
                finally:
                    with lock:
                        claimed.discard(i)
        except BaseException as e:
            with lock:
                errors.append(e)
            abort.set()
        finally:
            if f:
                f.close()

    def save_state():
        with lock:
            snap = list(done)
        _write_json_quiet(seg_path, {"v": 1, "total": total, "chunk": chunk, "validator": validator, "done": snap})

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(min(n_conn, nchunks))]
    for t in threads:
        t.start()
    last_report = last_save = time.monotonic()
    with lock:
        b_last = sum(done)
    speed = 0.0
    try:
        while True:
            if check_abort:
                check_abort()
            with lock:
                failed = bool(errors)
            if failed:
                break
            now = time.monotonic()
            if now - last_report >= 0.4:
                with lock:
                    cur = sum(done)
                inst = (cur - b_last) / (now - last_report)
                speed = inst if not speed else speed * 0.6 + inst * 0.4
                b_last, last_report = cur, now
                on_progress(cur, total, speed)
            if now - last_save >= 1.5:
                save_state()
                last_save = now
            if not any(t.is_alive() for t in threads):
                break
            time.sleep(0.15)
    except BaseException:
        abort.set()
        for t in threads:
            t.join(timeout=2)
        save_state()
        raise
    abort.set()
    for t in threads:
        t.join(timeout=5)
    with lock:
        got_total = sum(done)
        err = errors[0] if errors else None
    if err is not None:
        if got_total == 0 and isinstance(err, (urllib.error.HTTPError, _NoRange)):
            for f in (part_path, seg_path):
                try:
                    os.remove(f)
                except OSError:
                    pass
            raise SegFallback(str(err))
        save_state()
        raise err
    if got_total < total:
        save_state()
        raise IOError("Incomplete download")
    try:
        os.remove(seg_path)
    except OSError:
        pass



def _single_stream(url, headers, final, part, run, on_progress, expected=0):
    """تحميل باتصال واحد مع استكمال (للسيرفرات اللي مش بتدعم التجزئة)."""
    def open_at(start):
        h = dict(headers)
        if start:
            h["Range"] = f"bytes={start}-"
        return _urlopen(urllib.request.Request(url, headers=h), timeout=30)

    done = os.path.getsize(part) if os.path.exists(part) else 0
    total = 0
    if expected:                            # نتأكد إن في مساحة كفاية قبل ما نبدأ (بدل ما التحميل يفشل عند 99%)
        free = shutil.disk_usage(os.path.dirname(os.path.abspath(part))).free
        if free < max(0, expected - done) + (16 << 20):
            raise OSError(28, "No space left on device")
    if done:
        try:
            resp = open_at(done)
        except urllib.error.HTTPError as e:
            if e.code == 416:               # الجزء الجزئي كامل أصلاً
                os.replace(part, final)
                return final
            raise
        if resp.status == 206:
            tail = (resp.headers.get("Content-Range") or "").rsplit("/", 1)[-1]
            total = int(tail) if tail.isdigit() else (done + int(resp.headers.get("Content-Length") or 0))
        else:
            done = 0                        # السيرفر مش بيدعم الاستكمال: نبدأ من الأول
            cl = resp.headers.get("Content-Length")
            total = int(cl) if cl and cl.isdigit() else 0
    else:
        resp = open_at(0)
        cl = resp.headers.get("Content-Length")
        total = int(cl) if cl and cl.isdigit() and resp.status == 200 else 0

    retries = 0
    t_last, b_last, speed = time.monotonic(), done, 0.0
    with open(part, "ab" if done else "wb") as f:
        while True:
            try:
                if resp is None:                    # إعادة اتصال بعد انقطاع (جوه الـ try: فشل الاتصال نفسه بيتعاد برضه)
                    f.flush()
                    resp = open_at(done)
                    if done and resp.status != 206:
                        resp.close()
                        raise IOError("server does not support resuming")
                while True:
                    if run.cancel.is_set():
                        raise TaskAbort("cancel")
                    if run.stop.is_set():
                        raise TaskAbort("pause")
                    chunk = resp.read(262144)
                    if not chunk:
                        break
                    rate_limiter.consume(len(chunk), lambda: run.cancel.is_set() or run.stop.is_set())
                    f.write(chunk)
                    usage.add(len(chunk))
                    done += len(chunk)
                    retries = 0                     # وصلت بيانات: العدّاد يبدأ من جديد
                    now = time.monotonic()
                    if now - t_last >= 0.4:
                        inst = (done - b_last) / (now - t_last)
                        speed = inst if not speed else speed * 0.6 + inst * 0.4
                        t_last, b_last = now, done
                        on_progress(done, total, speed)
                if total and done < total:          # السيرفر قفل الاتصال بدري من غير خطأ: نكمّل بدل ما نفشل
                    raise IOError("connection closed early")
                break
            except TaskAbort:
                try:
                    resp.close()
                except Exception:
                    pass
                raise
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and retries < 8:
                    retries += 1
                    time.sleep(min(2 * retries, 10))
                    resp = None
                    continue
                raise
            except (OSError, http.client.HTTPException) as e:
                if getattr(e, "errno", None) == 28:
                    raise
                if isinstance(e, IOError) and str(e) == "server does not support resuming":
                    raise
                retries += 1
                if retries > 8:
                    raise
                try:
                    if resp is not None:
                        resp.close()
                except Exception:
                    pass
                resp = None
                for _ in range(int(min(2 * retries, 10) / 0.25)):      # انتظار قابل للإيقاف (Pause/Cancel)
                    if run.cancel.is_set():
                        raise TaskAbort("cancel")
                    if run.stop.is_set():
                        raise TaskAbort("pause")
                    time.sleep(0.25)
    try:
        resp.close()
    except Exception:
        pass
    if total and done < total:
        raise IOError("Incomplete download")
    os.replace(part, final)
    return final



def native_download(url, save_path, referer, run, prev_path, on_name, on_progress, cookie="", ua="", refreshed=False):
    holder = [None]
    try:
        return _native_download(url, save_path, referer, run, prev_path, on_name, on_progress, cookie, ua, refreshed, holder)
    finally:
        if holder[0]:
            _release_path(holder[0])      # الاسم المحجوز بيتحرر لما التحميل يخلص أو يقف


def _native_download(url, save_path, referer, run, prev_path, on_name, on_progress, cookie="", ua="", refreshed=False, holder=None):
    """تحميل ملف مباشر: بعدة اتصالات لو السيرفر بيدعم Range، وإلا باتصال واحد. بيرجّع المسار النهائي."""
    headers = {"User-Agent": ua or custom_user_agent() or USER_AGENT, "Accept": "*/*", "Accept-Encoding": "identity"}
    auth = site_auth_header(url)
    if auth:
        headers["Authorization"] = auth
    if referer:
        headers["Referer"] = referer
    if cookie:
        headers["Cookie"] = cookie
    probe = _http_probe_range(url, headers)
    total = probe["total"]
    if refreshed and prev_path:
        # رابط جديد لنفس الملف (Refresh link): نكمّل على نفس الاسم والمكان، ومش بنقارن الـ ETag لأن المستخدم أكّد إنه نفس الملف
        name, save_path = os.path.basename(prev_path), os.path.dirname(os.path.abspath(prev_path))
    else:
        name = probe["name"]
        save_path = category_dir(save_path, name)
    final = _unique_path(save_path, name, prev_path)
    if holder is not None:
        holder[0] = final
    part = final + ".part"
    seg = part + ".seg"
    if final != prev_path:
        for f in (part, seg):               # بقايا قديمة مش تبع التاسك ده
            try:
                os.remove(f)
            except OSError:
                pass
    conns = get_connections()
    has_part, has_seg = os.path.exists(part), os.path.exists(seg)
    eligible = probe["ranged"] and total >= SEG_MIN_TOTAL
    if has_seg and not eligible:
        for f in (part, seg):               # الملف الجزئي متجزّأ بس السيرفر مبقاش بيدعم Range: نبدأ من الأول
            try:
                os.remove(f)
            except OSError:
                pass
        has_part = has_seg = False

    def check():
        if run.cancel.is_set():
            raise TaskAbort("cancel")
        if run.stop.is_set():
            raise TaskAbort("pause")

    if eligible and (has_seg or (conns > 1 and not has_part)):
        n = max(2, conns)
        on_name(os.path.basename(final), final, total, n, probe["ranged"])
        try:
            segmented_fetch(probe["final_url"] or url, headers, total, part, n, on_progress, check,
                            validator="" if refreshed else probe["validator"], orig_url=url)
            os.replace(part, final)
            return final
        except SegFallback as e:
            logging.info(f"segmented download not possible, using single stream: {e}")
    on_name(os.path.basename(final), final, total, 1, probe["ranged"])
    return _single_stream(url, headers, final, part, run, on_progress, expected=total)



def install_segmented_downloader(y):
    """بيحل محل HttpFD في yt-dlp بنسخة بتجزّأ التحميل (يوتيوب وغيره) من غير ما يمس الدمج أو الـ thumbnails."""
    if getattr(y, "_idm_seg_installed", False):
        return
    HttpFD = y.downloader.HttpFD

    class SegFD(HttpFD):
        def real_download(self, filename, info_dict):
            try:
                if self._seg_eligible(filename, info_dict):
                    return self._seg_download(filename, info_dict)
            except SegFallback as e:
                logging.info(f"yt-dlp segmented download skipped: {e}")
                info_dict.pop("_ag_counted", None)      # yt-dlp العادي هو اللي هيحمّل: عدّاده يشتغل من الـ hook
            return super().real_download(filename, info_dict)

        def _seg_eligible(self, filename, info_dict):
            if info_dict.get("request_data") or info_dict.get("is_live") or info_dict.get("impersonate") is not None:
                return False
            if self.params.get("test") or self.params.get("nopart"):
                return False
            if (info_dict.get("http_headers") or {}).get("Range"):
                return False
            tmp = self.temp_name(filename)
            has_part, has_seg = os.path.exists(tmp), os.path.exists(tmp + ".seg")
            if has_part and not has_seg:
                return False                # ملف جزئي بتاع yt-dlp العادي: نكمّله بنفس الطريقة
            return get_connections() > 1 or has_seg

        def _seg_download(self, filename, info_dict):
            url = info_dict["url"]
            headers = {"Accept-Encoding": "identity", **(info_dict.get("http_headers") or {})}
            if not any(k.lower() == "cookie" for k in headers):
                try:                                # كوكيز yt-dlp (cookies.txt) كانت بتضيع في التحميل المجزّأ
                    ck = self.ydl.cookiejar.get_cookie_header(url)
                    if ck:
                        headers["Cookie"] = ck
                except Exception:
                    pass
            tmp = self.temp_name(filename)
            has_seg = os.path.exists(tmp + ".seg")
            info_dict["_ag_counted"] = True             # التحميل المجزّأ بيعدّ البايتات بنفسه (مش من الـ hook)
            try:
                probe = _http_probe_range(url, headers)
            except Exception as e:
                raise SegFallback(f"probe failed: {e}")
            total = probe["total"]
            if not (probe["ranged"] and total >= SEG_MIN_TOTAL):
                if has_seg:
                    for f in (tmp, tmp + ".seg"):
                        try:
                            os.remove(f)
                        except OSError:
                            pass
                raise SegFallback("server does not support ranges or file is small")
            conns = max(2, get_connections())
            hint = (info_dict.get("downloader_options") or {}).get("http_chunk_size")
            t0 = time.time()
            self.report_destination(filename)

            def on_prog(done, tot, speed):
                self._hook_progress({
                    "status": "downloading", "downloaded_bytes": done, "total_bytes": tot,
                    "tmpfilename": tmp, "filename": filename, "speed": speed,
                    "eta": (tot - done) / speed if speed else None, "elapsed": time.time() - t0,
                }, info_dict)

            segmented_fetch(probe["final_url"] or url, headers, total, tmp, conns, on_prog, None,
                            chunk_hint=hint, validator=probe["validator"], orig_url=url)
            self.try_rename(tmp, filename)
            self._hook_progress({
                "status": "finished", "downloaded_bytes": total, "total_bytes": total,
                "filename": filename, "elapsed": time.time() - t0,
                "speed": total / max(time.time() - t0, 0.001),
            }, info_dict)
            return True

    y.downloader.PROTOCOL_MAP["http"] = SegFD
    y.downloader.PROTOCOL_MAP["https"] = SegFD
    y._idm_seg_installed = True



# ----------------------------------------------------------------------------- H.264 compatibility
def probe_video_codec(path):
    """اسم ترميز الفيديو (h264 / vp9 / av1 ...) أو None لو معرفناش."""
    ff = find_ffmpeg()
    if not ff:
        return None
    try:
        flags = 0x08000000 if IS_WINDOWS else 0          # CREATE_NO_WINDOW
        r = subprocess.run([ff, "-hide_banner", "-i", path], capture_output=True, text=True,
                           errors="replace", timeout=30, creationflags=flags)
        m = re.search(r"Stream #\S+.*?Video:\s*([A-Za-z0-9_]+)", r.stderr or "")
        return m.group(1).lower() if m else None
    except Exception as e:
        log_error("probe_video_codec", e)
        return None



def convert_to_h264(src, run):
    """تحويل الفيديو لـ H.264 + AAC (MP4). بيرجّع المسار الجديد. بيتلغي لو المستخدم عمل Pause/Cancel."""
    ff = find_ffmpeg()
    if not ff:
        raise RuntimeError("ffmpeg is missing")
    base = os.path.splitext(src)[0]
    final = base + ".mp4"
    if os.path.exists(final) and os.path.abspath(final) != os.path.abspath(src):
        n = 1                               # متكتبش فوق ملف تاني موجود بنفس الاسم
        while os.path.exists(f"{base} ({n}).mp4"):
            n += 1
        final = f"{base} ({n}).mp4"
    tmp = base + ".h264.tmp.mp4"
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error", "-i", src, "-map", "0:v:0", "-map", "0:a?",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
           "-profile:v", "high", "-level", "4.1", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", tmp]
    flags = 0x08000000 if IS_WINDOWS else 0
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    try:
        while proc.poll() is None:
            if run.cancel.is_set() or run.stop.is_set():
                proc.kill()
                proc.wait()
                raise TaskAbort("cancel" if run.cancel.is_set() else "pause")
            time.sleep(0.3)
        if proc.returncode != 0 or not os.path.exists(tmp):
            raise RuntimeError("ffmpeg failed to convert the video to H.264")
        os.replace(tmp, final)
        if os.path.abspath(src) != os.path.abspath(final) and os.path.exists(src):
            os.remove(src)
        return final
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
