# -*- coding: utf-8 -*-
import ssl
import urllib.request, urllib.parse, urllib.error
import logging, logging.handlers
import socket as _socket_mod
from aerograb.common import get_setting


def _make_certifi_context():
    """شهادات certifi كخطة بديلة (ويندوز القديم بتبقى شهادات الجذر فيه ناقصة)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None



_CERTIFI_CTX = _make_certifi_context()



_opener_cache = {}

_LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")



def net_timeout():
    """مهلة الاتصال اللي اختارها المستخدم بالثواني (0 = تلقائي)."""
    try:
        return max(0, int(get_setting("net_timeout", 0) or 0))
    except (TypeError, ValueError):
        return 0


def custom_user_agent():
    return (get_setting("user_agent", "") or "").strip()


def site_auth_header(url):
    """هيدر Basic Auth للمواقع اللي المستخدم سجّل لها اسم مستخدم وكلمة سر (تسجيل دخول الموقع)."""
    try:
        logins = get_setting("site_logins", {}) or {}
        host = _host(url)
        for h, cred in logins.items():
            h = (h or "").strip().lower()
            if h and (host == h or host.endswith("." + h)) and isinstance(cred, dict) and cred.get("u"):
                import base64
                raw = f"{cred.get('u', '')}:{cred.get('p', '')}".encode("utf-8")
                return "Basic " + base64.b64encode(raw).decode("ascii")
    except Exception:
        pass
    return ""


def _proxy_url():
    return (get_setting("proxy", "") or "").strip()



def _host(url):
    try:
        return (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return ""



class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    """لو التحويل راح لدومين تاني بنشيل Cookie/Authorization (كوكيز موقع ما تتسربش لموقع تاني، زي المتصفح)."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and _host(req.full_url) != _host(newurl):
            for h in ("Cookie", "Authorization"):
                for d in (new.headers, new.unredirected_hdrs):
                    for k in [k for k in d if k.lower() == h.lower()]:
                        d.pop(k, None)
        return new



def _opener(mode, ctx):
    """mode: None = إعدادات النظام ، 'direct' = من غير بروكسي ، أو رابط بروكسي."""
    key = (mode, id(ctx))
    op = _opener_cache.get(key)
    if op is None:
        handlers = [_SafeRedirect()]
        if mode == "direct":
            handlers.append(urllib.request.ProxyHandler({}))
        elif mode:
            handlers.append(urllib.request.ProxyHandler({"http": mode, "https": mode}))
        if ctx is not None:
            handlers.append(urllib.request.HTTPSHandler(context=ctx))
        op = urllib.request.build_opener(*handlers)
        _opener_cache[key] = op
    return op



def _open_once(req, ctx, kw):
    """بيفتح الطلب: عن طريق البروكسي (لو مفعّل وهو HTTP). العناوين المحلية (البرنامج بيكلم نفسه) عمرها ما بتعدّي على بروكسي."""
    full = req if isinstance(req, str) else req.full_url
    host = _host(full)
    proxy = _proxy_url()
    if host in _LOCAL_HOSTS or host.startswith("127."):
        mode = "direct"
    elif proxy and urllib.parse.urlparse(proxy).scheme in ("http", "https"):
        mode = proxy
    else:
        mode = None
    to = kw.get("timeout", _socket_mod._GLOBAL_DEFAULT_TIMEOUT)
    custom = net_timeout()
    if custom and (to is _socket_mod._GLOBAL_DEFAULT_TIMEOUT or to >= 15):      # المهل القصيرة (فحوصات سريعة) متتغيّرش
        to = custom
    return _opener(mode, ctx).open(req, timeout=to)



def _urlopen(req, **kw):
    """بنجرّب مخزن شهادات النظام الأول (بيشمل شهادات برامج الحماية والشبكات)، ولو فشل بسبب الشهادة بنجرّب certifi."""
    if "context" in kw:
        return urllib.request.urlopen(req, **kw)
    try:
        return _open_once(req, None, kw)
    except (urllib.error.URLError, ssl.SSLError) as e:
        reason = getattr(e, "reason", e)
        if _CERTIFI_CTX is not None and isinstance(reason, ssl.SSLCertVerificationError):
            logging.info("system certificates rejected the server, retrying with certifi bundle")
            return _open_once(req, _CERTIFI_CTX, kw)
        raise
