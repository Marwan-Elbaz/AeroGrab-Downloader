const API = "http://127.0.0.1:9999";
const CLICK_WINDOW_MS = 8000;
const LAUNCH_TIMEOUT_MS = 20000;

const ARCHIVE_MIMES = new Set([
    "application/zip", "application/x-zip-compressed", "application/x-rar-compressed", "application/vnd.rar",
    "application/x-7z-compressed", "application/gzip", "application/x-tar",
    "application/vnd.android.package-archive", "application/x-msdownload", "application/x-iso9660-image"
]);

// ---------- إعدادات الالتقاط: بتتقري من برنامج البايثون (تبويب Browser و File types في الإعدادات)
// ده الافتراضي لو البرنامج مقفول ومفيش نسخة محفوظة
const DEFAULT_CFG = {
    enabled: true,
    extensions: [
        "zip", "rar", "7z", "tar", "gz", "bz2", "xz", "iso", "img",
        "exe", "msi", "apk", "dmg", "pkg", "deb", "rpm",
        "mp4", "mkv", "avi", "mov", "flv", "wmv", "webm", "m4v", "mpg", "mpeg", "3gp",
        "mp3", "wav", "flac", "m4a", "aac", "ogg", "opus", "wma",
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx"
    ],
    doc_extensions: ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx"],
    min_doc_mb: 1,          // مستندات أصغر من كده يسيبها للمتصفح
    min_binary_mb: 5,       // octet-stream من غير امتداد: لازم يبقى كبير
    capture_media_mime: true,
    require_click: true,
    bypass_key: "alt",      // الضغط على المفتاح ده مع الكليك = المتصفح يحمّل بنفسه
    menu: { link: true, media: true, image: true, sel: true, page: true, all: true },
};
const CFG_TTL_MS = 30000;
let cfg = DEFAULT_CFG;
let cfgAt = 0;
let cfgLoading = null;
let extSet = new Set(DEFAULT_CFG.extensions);
let docSet = new Set(DEFAULT_CFG.doc_extensions);

function applyCfg(j) {
    cfg = { ...DEFAULT_CFG, ...(j || {}), menu: { ...DEFAULT_CFG.menu, ...((j && j.menu) || {}) } };
    extSet = new Set((cfg.extensions || []).map((x) => String(x).toLowerCase()));
    docSet = new Set((cfg.doc_extensions || []).map((x) => String(x).toLowerCase()));
}

async function restoreCached() {
    try {
        const st = await chrome.storage.local.get("cfg");
        if (st && st.cfg) applyCfg(st.cfg);
    } catch (_) {}
}
const ready = restoreCached();       // أول ما الـ service worker يصحى

async function loadConfig(force) {
    if (!force && Date.now() - cfgAt < CFG_TTL_MS) return cfg;
    if (cfgLoading) return cfgLoading;
    cfgLoading = (async () => {
        try {
            const r = await apiFetch("/get_settings", { v: chrome.runtime.getManifest().version }, 1500);
            if (r.ok) {
                const j = await r.json();
                applyCfg(j);
                try { await chrome.storage.local.set({ cfg: j }); } catch (_) {}
            }
        } catch (_) { /* البرنامج مقفول: نكمّل بآخر نسخة محفوظة */ }
        cfgAt = Date.now();
        await rebuildMenusIfChanged();
        return cfg;
    })().finally(() => { cfgLoading = null; });
    return cfgLoading;
}

// ---------- آخر تفاعل من المستخدم (محفوظ في storage.session عشان الـ service worker بيتقفل لوحده)
let lastClickMem = { t: 0, mods: {} };
const handled = new Set();

async function setLastClick(t, mods) {
    lastClickMem = { t, mods: mods || {} };
    try { await chrome.storage.session.set({ lastClick: lastClickMem }); } catch (_) {}
}
async function getLastClick() {
    let v = lastClickMem;
    try {
        const s = await chrome.storage.session.get("lastClick");
        if (s && s.lastClick && s.lastClick.t > v.t) v = s.lastClick;
    } catch (_) {}
    return v;      // { t, mods: {alt, ctrl, shift} }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------- التواصل مع برنامج البايثون
async function apiFetch(path, params = {}, timeoutMs = 4000) {
    const url = new URL(API + path);
    for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
    }
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
        return await fetch(url, { headers: { "X-IDM-Client": "extension" }, signal: ctrl.signal, cache: "no-store" });
    } finally {
        clearTimeout(timer);
    }
}

async function isAppUp() {
    try { return (await apiFetch("/ping", {}, 1500)).ok; } catch (_) { return false; }
}

// فتح البرنامج لو مقفول (مشاركة نفس المحاولة لو أكتر من تحميل جُم مع بعض)
let launching = null;
function ensureAppRunning() {
    if (launching) return launching;
    launching = (async () => {
        if (await isAppUp()) return true;
        let tabId = null;
        try {
            const tab = await chrome.tabs.create({ url: "aerograb://start", active: false });
            tabId = tab && tab.id;
        } catch (_) {}
        const deadline = Date.now() + LAUNCH_TIMEOUT_MS;
        let ok = false;
        while (Date.now() < deadline) {
            await sleep(700);
            if (await isAppUp()) { ok = true; break; }
        }
        if (tabId) { try { await chrome.tabs.remove(tabId); } catch (_) {} }
        return ok;
    })().finally(() => { launching = null; });
    return launching;
}

// كوكيز الموقع + User-Agent: بتتبعت للبرنامج (على نفس الجهاز بس) عشان التحميلات اللي محتاجة تسجيل دخول تشتغل
async function cookieHeader(url) {
    try {
        const list = await chrome.cookies.getAll({ url });
        return list.map((c) => `${c.name}=${c.value}`).join("; ");
    } catch (_) { return ""; }
}
const USER_AGENT = (typeof navigator !== "undefined" && navigator.userAgent) || "";

// بيبعت اللينك للبرنامج. بيرجّع { ok }
async function sendToApp(url, quality, referer, direct, cookie, extra) {
    // extra: { clip: "1" } = يفتح نافذة التنزيل وهي على "تحميل جزء"  |  { playlist: "all" | "pick" } = شاشة قايمة التشغيل
    const params = { url, quality, referer, direct: direct ? "1" : "", cookie: cookie || "", ua: USER_AGENT, ...(extra || {}) };
    try {
        const r = await apiFetch("/add", params);
        if (r.ok) return { ok: true };
    } catch (_) {}
    if (!(await ensureAppRunning())) return { ok: false, reason: "app_not_running" };
    for (let i = 0; i < 3; i++) {
        try {
            const r = await apiFetch("/add", params);
            if (r.ok) return { ok: true, launched: true };
        } catch (_) {}
        await sleep(500);
    }
    return { ok: false, reason: "add_failed" };
}

// ---------- اعتراض تحميلات المتصفح
function getExt(s) {
    const m = /\.([a-z0-9]{1,6})$/i.exec(s || "");
    return m ? m[1].toLowerCase() : "";
}

function isCapturable(item, url) {
    const name = (item.filename || "").split(/[\\/]/).pop();
    let ext = getExt(name);
    if (!extSet.has(ext)) {
        try { ext = getExt(decodeURIComponent(new URL(url).pathname)); } catch (_) { ext = ""; }
    }
    const size = item.totalBytes > 0 ? item.totalBytes : (item.fileSize > 0 ? item.fileSize : 0);
    if (extSet.has(ext)) {
        if (docSet.has(ext) && size > 0 && size < cfg.min_doc_mb * 1024 * 1024) return false;
        return true;
    }
    if (!cfg.capture_media_mime) return false;
    const mime = (item.mime || "").toLowerCase();
    if (mime.startsWith("video/") || mime.startsWith("audio/") || ARCHIVE_MIMES.has(mime)) return true;
    if (mime === "application/octet-stream" && size >= cfg.min_binary_mb * 1024 * 1024) return true;
    return false;
}

async function handleDownload(item) {
    const url = item.finalUrl || item.url || "";
    if (!/^https?:\/\//i.test(url)) return;
    if (item.byExtensionId && item.byExtensionId !== chrome.runtime.id) return;
    await ready;
    loadConfig(false).catch(() => {});                  // تحديث الإعدادات في الخلفية (من غير ما نستنى)
    if (!cfg.enabled) return;                           // الالتقاط متوقف من إعدادات البرنامج
    if (!isCapturable(item, url)) return;
    const lc = await getLastClick();
    const recent = Date.now() - lc.t <= CLICK_WINDOW_MS;
    if (cfg.require_click && !recent) return;           // مش بدأه المستخدم
    if (cfg.bypass_key && cfg.bypass_key !== "none" && recent && lc.mods && lc.mods[cfg.bypass_key]) return;   // مفتاح التجاوز: المتصفح يحمّل بنفسه
    if (handled.has(item.id)) return;
    handled.add(item.id);

    // نوقّف تحميل المتصفح مؤقتاً. لو البرنامج استلم اللينك نلغيه، لو لأ نكمّله في المتصفح (مفيش تحميل بيضيع).
    try { await chrome.downloads.pause(item.id); } catch (_) {}
    const res = await sendToApp(url, undefined, item.referrer, true, await cookieHeader(url));
    if (res.ok) {
        try { await chrome.downloads.cancel(item.id); } catch (_) {}
        try { await chrome.downloads.erase({ id: item.id }); } catch (_) {}
    } else {
        try { await chrome.downloads.resume(item.id); } catch (_) {}
    }
}

chrome.downloads.onCreated.addListener((item) => {
    handleDownload(item).catch((e) => console.warn("AeroGrab:", e));
});

// ---------- قوايم الضغط باليمين
const MENU = {
    link: "idm-link", media: "idm-media", image: "idm-image", page: "idm-page", sel: "idm-selection", all: "idm-all",
};

const MENU_TITLES = {
    en: {
        link: "Download link with AeroGrab", media: "Download this video/audio with AeroGrab", image: "Download this image with AeroGrab",
        sel: "Download links in selection with AeroGrab", page: "Download the video on this page with AeroGrab",
        all: "Download all links on this page (Link Grabber)",
    },
    ar: {
        link: "تحميل الرابط بواسطة AeroGrab", media: "تحميل هذا الفيديو/الصوت بواسطة AeroGrab", image: "تحميل هذه الصورة بواسطة AeroGrab",
        sel: "تحميل الروابط في التحديد بواسطة AeroGrab", page: "تحميل الفيديو في هذه الصفحة بواسطة AeroGrab",
        all: "تحميل كل الروابط في هذه الصفحة (Link Grabber)",
    },
};
const menuLang = () => (cfg && cfg.lang === "ar" ? "ar" : "en");

function buildMenus() {
    chrome.contextMenus.removeAll(() => {
        const T = MENU_TITLES[menuLang()];
        const mk = (id, title, contexts, on) => { if (on !== false) chrome.contextMenus.create({ id, title, contexts }); };
        const m = cfg.menu || {};
        mk(MENU.link, T.link, ["link"], m.link);
        mk(MENU.media, T.media, ["video", "audio"], m.media);
        mk(MENU.image, T.image, ["image"], m.image);
        mk(MENU.sel, T.sel, ["selection"], m.sel);
        mk(MENU.page, T.page, ["page"], m.page);
        mk(MENU.all, T.all, ["page", "frame"], m.all);
    });
}

async function rebuildMenusIfChanged() {
    const key = JSON.stringify(cfg.menu || {}) + "|" + menuLang();
    let prev = null;
    try { prev = (await chrome.storage.local.get("menuKey")).menuKey; } catch (_) {}
    if (prev === key) return;
    buildMenus();
    try { await chrome.storage.local.set({ menuKey: key }); } catch (_) {}
}

chrome.runtime.onInstalled.addListener(async () => {
    await ready;
    buildMenus();
    try { await chrome.storage.local.set({ menuKey: JSON.stringify(cfg.menu || {}) + "|" + menuLang() }); } catch (_) {}
    loadConfig(true).catch(() => {});
});
chrome.runtime.onStartup.addListener(() => { loadConfig(true).catch(() => {}); });
ready.then(() => loadConfig(false)).catch(() => {});

const VIDEO_SITES = /(^|\.)(youtube\.com|youtu\.be)$/i;

function isDirectLink(url) {
    try { return !VIDEO_SITES.test(new URL(url).hostname); } catch (_) { return true; }
}

// بتتنفّذ جوه الصفحة (لازم تبقى مستقلة بذاتها)
function collectLinksInPage(selectionOnly) {
    const out = [], seen = new Set();
    const add = (href, text) => {
        try {
            const u = new URL(href, location.href).href;
            if (/^https?:/i.test(u) && !seen.has(u)) { seen.add(u); out.push({ url: u, text: (text || "").trim().slice(0, 120) }); }
        } catch (_) { /* ignore */ }
    };
    const fromRoot = (root) => {
        root.querySelectorAll("a[href]").forEach((a) => add(a.href, a.textContent || a.title));
        if (!selectionOnly) root.querySelectorAll("video[src], audio[src], source[src]").forEach((el) => add(el.src, el.title));
    };
    if (selectionOnly) {
        const sel = window.getSelection();
        for (let i = 0; i < sel.rangeCount; i++) fromRoot(sel.getRangeAt(i).cloneContents());
    } else {
        fromRoot(document);
    }
    return out;
}

async function collectLinks(tab, frameId, selectionOnly) {
    const res = await chrome.scripting.executeScript({
        target: { tabId: tab.id, frameIds: [frameId || 0] }, func: collectLinksInPage, args: [!!selectionOnly],
    });
    return (res && res[0] && res[0].result) || [];
}

async function postBatch(items, referer) {
    const body = JSON.stringify({ items, referer, cookie: await cookieHeader(referer), ua: USER_AGENT });
    const post = async () => {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), 15000);
        try {
            return await fetch(API + "/add_batch", {
                method: "POST", body, signal: ctrl.signal,
                headers: { "X-IDM-Client": "extension", "Content-Type": "application/json" },
            });
        } finally { clearTimeout(timer); }
    };
    try { if ((await post()).ok) return { ok: true }; } catch (_) {}
    if (!(await ensureAppRunning())) return { ok: false, reason: "app_not_running" };
    for (let i = 0; i < 3; i++) {
        try { if ((await post()).ok) return { ok: true, launched: true }; } catch (_) {}
        await sleep(500);
    }
    return { ok: false, reason: "add_failed" };
}

async function handleMenu(info, tab) {
    const referer = info.pageUrl || (tab && tab.url) || "";
    const one = async (url, direct) => {
        if (!/^https?:\/\//i.test(url || "")) return { ok: false, reason: "unsupported_url" };
        return sendToApp(url, undefined, referer, direct, await cookieHeader(url));
    };
    switch (info.menuItemId) {
        case MENU.link: return one(info.linkUrl, isDirectLink(info.linkUrl));
        case MENU.image: return one(info.srcUrl, true);
        case MENU.media:       // blob: مينفعش يتحمّل مباشرة، فبنبعت الصفحة نفسها لـ yt-dlp
            return /^https?:/i.test(info.srcUrl || "") ? one(info.srcUrl, true) : one(referer, false);
        case MENU.page: return one(info.pageUrl || referer, false);
        case MENU.sel:
        case MENU.all: {
            if (!tab || tab.id === undefined) return { ok: false, reason: "no_tab" };
            const items = await collectLinks(tab, info.frameId, info.menuItemId === MENU.sel);
            if (!items.length) return { ok: false, reason: "no_links" };
            return postBatch(items, referer);
        }
    }
}

chrome.contextMenus.onClicked.addListener((info, tab) => {
    handleMenu(info, tab).catch((e) => console.warn("AeroGrab:", e));
});

// ---------- رسائل من content.js / tracker.js
const API_PATHS = new Set(["/ping", "/get_default_quality", "/get_qualities", "/get_video_formats", "/get_lang"]);

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (!message || sender.id !== chrome.runtime.id) return;

    if (message.action === "user_clicked") {
        setLastClick(Date.now(), message.mods);
        return;
    }

    const fromYouTube = /^https:\/\/([\w-]+\.)*youtube\.com\//i.test(sender.url || "");
    if (!fromYouTube) return;

    if (message.action === "api" && API_PATHS.has(message.path)) {
        (async () => {
            try {
                const r = await apiFetch(message.path, message.params || {}, Math.min(message.timeoutMs || 4000, 40000));
                sendResponse({ ok: r.ok, status: r.status, body: await r.text() });
            } catch (e) {
                sendResponse({ ok: false, status: 0, body: "" });
            }
        })();
        return true;      // رد غير متزامن
    }

    if (message.action === "add" && typeof message.url === "string") {
        const extra = {
            clip: message.clip ? "1" : "",
            playlist: message.playlist === "all" || message.playlist === "pick" ? message.playlist : "",
        };
        sendToApp(message.url, message.quality, message.referer, false, "", extra).then(sendResponse);
        return true;
    }
});

// ---------- ضغطة على أيقونة الإضافة في شريط المتصفح = افتح AeroGrab (أو اظهره لو شغال)
chrome.action.onClicked.addListener(async () => {
    try {
        const tab = await chrome.tabs.create({ url: "aerograb://start", active: false });
        await sleep(2500);
        if (tab && tab.id) { try { await chrome.tabs.remove(tab.id); } catch (_) {} }
    } catch (_) {}
});
