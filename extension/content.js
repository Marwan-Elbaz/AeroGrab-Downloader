// AeroGrab - YouTube integration (v3.3)
// زرار واحد "Download" بيفتح قائمة: الجودات + تحميل جزء من الفيديو + قوايم التشغيل.
// كل الاتصال بالبرنامج بيعدّي على background.js (مفيش fetch مباشر من الصفحة).

(() => {
    if (window.__idmModernProLoaded) return;
    window.__idmModernProLoaded = true;

    // ---------------- اللغة: بتتبع لغة البرنامج (cfg.lang اللي background.js بيخزّنها + /get_lang لما القائمة تتفتح)
    const AR = {
        'Download': 'تحميل',
        'Download video': 'تحميل الفيديو',
        'Playlist': 'قائمة التشغيل',
        '✂  Download a part…': '✂  تحميل جزء من الفيديو…',
        '📚  Whole playlist': '📚  القائمة كاملة',
        '☑  Choose videos…': '☑  اختيار فيديوهات…',
        'Audio Only': 'صوت فقط',
        '⚠️ No valid video here': '⚠️ لا يوجد فيديو صالح هنا',
        '⏳ Checking available qualities...': '⏳ جارٍ فحص الجودات المتاحة...',
        '⚠️ No qualities available for this video right now': '⚠️ لا توجد جودات متاحة لهذا الفيديو الآن',
        '⚠️ The extension was updated — refresh the page': '⚠️ تم تحديث الإضافة — أعد تحميل الصفحة',
        '✅ The program was opened and the link was sent': '✅ تم فتح البرنامج وإرسال الرابط',
        '✅ Sent to the program': '✅ تم الإرسال إلى البرنامج',
        '⚠️ Could not open the program. Make sure it is installed and start it manually': '⚠️ تعذّر فتح البرنامج. تأكد أنه مثبّت وشغّله يدويًا',
        '⚠️ No valid video to download here': '⚠️ لا يوجد فيديو صالح للتحميل هنا',
        '⏳ Sending to the program...': '⏳ جارٍ الإرسال إلى البرنامج...',
        '⚠️ No playlist here': '⚠️ لا توجد قائمة تشغيل هنا',
        '⏳ Opening the playlist in the program...': '⏳ جارٍ فتح قائمة التشغيل في البرنامج...',
    };
    let uiLang = 'en';
    const t = (s) => (uiLang === 'ar' && AR[s]) || s;
    function applyLang(code) {
        const next = code === 'ar' ? 'ar' : 'en';
        if (next === uiLang) return;
        uiLang = next;
        document.querySelectorAll('.idm-main-btn span').forEach((el) => { el.textContent = t('Download'); });
    }
    const langReady = (async () => {
        try {
            const st = await chrome.storage.local.get('cfg');
            if (st && st.cfg && st.cfg.lang) uiLang = st.cfg.lang === 'ar' ? 'ar' : 'en';
        } catch (_) { /* ignore */ }
    })();
    try {
        chrome.storage.onChanged.addListener((ch, area) => {
            if (area === 'local' && ch.cfg && ch.cfg.newValue && ch.cfg.newValue.lang) applyLang(ch.cfg.newValue.lang);
        });
    } catch (_) { /* ignore */ }
    
    const style = document.createElement('style');
    style.textContent = `
      .idm-thumb-widget, .idm-inside-widget, .idm-dropdown, .idm-toast { direction: ltr; text-align: left; }
      .idm-thumb-widget {
        position: absolute; top: 8px; left: 8px; z-index: 2147483647 !important; display: flex; opacity: 0;
        transition: opacity 0.2s ease-in-out; background: rgba(24, 26, 31, 0.96);
        border-radius: 18px; box-shadow: 0 4px 10px rgba(0,0,0,0.5);
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: white;
        border: 1px solid #3a3f49; backdrop-filter: blur(4px); pointer-events: auto !important;
      }
      /* يظهر لما الماوس يقف على الصورة المصغرة نفسها */
      ytd-thumbnail:hover .idm-thumb-widget,
      yt-thumbnail-view-model:hover .idm-thumb-widget,
      .idm-thumb-widget:hover,
      .idm-thumb-widget.idm-open { opacity: 1 !important; }
    
      ytd-thumbnail:hover, ytd-compact-video-renderer:hover, ytd-rich-item-renderer:hover, a#thumbnail:hover {
          z-index: 2147483647 !important; overflow: visible !important;
      }
    
      .idm-inside-widget {
        display: inline-flex; align-items: center; margin-right: 15px; vertical-align: top; margin-top: 8px;
        background: rgba(24, 26, 31, 0.96); border-radius: 16px; font-family: 'Segoe UI', sans-serif; color: white;
        border: 1px solid #3a3f49; height: 32px !important; position: relative; z-index: 2147483647;
      }
      .idm-main-btn {
        padding: 6px 12px !important; font-size: 12px; font-weight: 700; cursor: pointer; border-radius: 17px;
        transition: background 0.2s; white-space: nowrap; user-select: none; display: flex; align-items: center; gap: 6px;
        height: auto !important; line-height: normal !important; min-height: 0 !important;
      }
      .idm-inside-widget .idm-main-btn { font-size: 13px; line-height: 18px !important; }
      .idm-main-btn:hover, .idm-open .idm-main-btn { background: #2cc985 !important; color: #fff !important; }
    
      .idm-main-btn img { width: 16px; height: 16px; display: block; }
      .idm-main-btn svg { width: 10px; height: 10px; display: block; opacity: .85; }
      .idm-dropdown {
        position: fixed; background: #1b1d22; border: 1px solid #3a3f49; border-radius: 14px;
        box-shadow: 0 10px 28px rgba(0,0,0,0.75); display: flex; flex-direction: column; width: max-content; min-width: 210px;
        z-index: 2147483647; overflow-y: auto; padding: 6px 0; font-family: 'Segoe UI', Tahoma, sans-serif; color: white;
      }
      .idm-dropdown::-webkit-scrollbar { width: 5px; }
      .idm-dropdown::-webkit-scrollbar-track { background: transparent; }
      .idm-dropdown::-webkit-scrollbar-thumb { background: #555; border-radius: 10px; }
      .idm-dropdown::-webkit-scrollbar-thumb:hover { background: #2cc985; }
      .idm-menu-panel { display: flex; flex-direction: column; height: auto !important; }
      .idm-section {
        padding: 6px 16px 4px; font-size: 10px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: #8b93a1;
      }
      .idm-sep { height: 1px; background: #2c3038; margin: 5px 10px; }
      .idm-quality-item {
        padding: 8px 16px !important; font-size: 13px !important; cursor: pointer; transition: background 0.15s;
        display: flex; align-items: center; gap: 8px; color: #e4e7ec !important; margin: 0 6px !important; border-radius: 8px;
        white-space: nowrap; height: auto !important; min-height: 0 !important; line-height: normal !important; box-sizing: border-box !important;
      }
      .idm-quality-item:hover { background: #2cc985 !important; color: #fff !important; }
      .idm-note { padding: 8px 16px; font-size: 12px; color: #aab; max-width: 230px; white-space: normal; line-height: 1.4; }
      .idm-note.err { color: #e06666; }
      .idm-toast {
        position: fixed; left: 20px; bottom: 24px; z-index: 2147483647; max-width: 340px;
        background: rgba(28,28,28,0.97); color: #fff; border: 1px solid #444; border-left: 4px solid #2cc985;
        border-radius: 10px; padding: 10px 14px; font: 13px 'Segoe UI', Tahoma, sans-serif;
        box-shadow: 0 6px 18px rgba(0,0,0,0.6); opacity: 0; transform: translateY(8px);
        transition: opacity .2s, transform .2s; pointer-events: none;
      }
      .idm-toast.show { opacity: 1; transform: none; }
      .idm-toast.err { border-left-color: #e06666; }
    `;
    document.head.appendChild(style);
    
    const ICON_DOWNLOAD = "data:image/png;base64,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";
    let currentDefaultQuality = "1080p";
    let availableQualities = ["1080p", "720p", "480p", "360p", "240p", "144p", "Audio Only"];
    
    // ---------------- التواصل مع الخلفية
    function bg(message) {
        return new Promise((resolve) => {
            try {
                if (!chrome.runtime?.id) return resolve(null);
                chrome.runtime.sendMessage(message, (res) => {
                    if (chrome.runtime.lastError) return resolve(null);
                    resolve(res || null);
                });
            } catch (_) { resolve(null); }       // Extension context invalidated
        });
    }
    
    async function api(path, params, timeoutMs) {
        const res = await bg({ action: "api", path, params, timeoutMs });
        return res && res.ok ? res.body : null;
    }
    
    // ---------------- Toast
    let toastEl = null, toastTimer = null;
    function toast(text, isErr = false) {
        if (!toastEl) {
            toastEl = document.createElement('div');
            toastEl.className = 'idm-toast';
            document.documentElement.appendChild(toastEl);
        }
        toastEl.textContent = text;
        toastEl.style.direction = uiLang === 'ar' ? 'rtl' : 'ltr';
        toastEl.style.textAlign = uiLang === 'ar' ? 'right' : 'left';
        toastEl.classList.toggle('err', isErr);
        requestAnimationFrame(() => toastEl.classList.add('show'));
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => toastEl.classList.remove('show'), isErr ? 4500 : 2500);
    }
    
    // ---------------- الروابط: فيديو واحد نضيف و/أو قائمة تشغيل
    function normalizeVideoUrl(href) {
        try {
            const u = new URL(href, location.origin);
            if (!/(^|\.)youtube\.com$/i.test(u.hostname)) return null;
            if (u.pathname === '/watch') {
                const v = u.searchParams.get('v');
                return v ? `https://www.youtube.com/watch?v=${encodeURIComponent(v)}` : null;
            }
            const m = u.pathname.match(/^\/shorts\/([\w-]{5,})/);
            return m ? `https://www.youtube.com/shorts/${m[1]}` : null;
        } catch (_) { return null; }
    }
    
    // بيرجّع { video, playlist } — أي واحد فيهم ممكن يبقى null. قوايم الـ Mix التلقائية (RD...) بنتجاهلها.
    function classify(href) {
        const out = { video: null, playlist: null };
        try {
            const u = new URL(href, location.origin);
            if (!/(^|\.)youtube\.com$/i.test(u.hostname)) return out;
            out.video = normalizeVideoUrl(href);
            const list = u.searchParams.get('list');
            if (list && /^[\w-]{10,64}$/.test(list) && !/^RD/i.test(list)) {
                out.playlist = `https://www.youtube.com/playlist?list=${encodeURIComponent(list)}`;
            }
        } catch (_) { /* ignore */ }
        return out;
    }
    
    const LINK_SEL = 'a[href*="/watch"], a[href*="/shorts/"], a[href*="/playlist?list="]';
    const CONTAINER_SEL = 'yt-lockup-view-model, ytd-rich-item-renderer, ytd-video-renderer, ytd-compact-video-renderer, ytd-grid-video-renderer, ytd-playlist-video-renderer, ytd-playlist-renderer, ytd-grid-playlist-renderer';
    function findAnchor(thumb) {
        const ok = (a) => a && (classify(a.href).video || classify(a.href).playlist);
        const cands = [
            thumb.closest(LINK_SEL),
            thumb.querySelector(LINK_SEL),
            (thumb.closest(CONTAINER_SEL) || document.createDocumentFragment()).querySelector(LINK_SEL),
        ];
        return cands.find(ok) || null;
    }
    
    // كارت قايمة تشغيل (مش فيديو): رابطه بيشاور على أول فيديو + list=، فلازم نعامله كقايمة بس (من غير جودات أول فيديو)
    const PL_CONTAINER_SEL = 'ytd-playlist-renderer, ytd-grid-playlist-renderer, ytd-compact-playlist-renderer, ytd-playlist-panel-renderer';
    function isPlaylistCard(thumb, a) {
        try {
            const u = new URL(a.href, location.origin);
            if (u.pathname === '/playlist') return true;
            if (!u.searchParams.get('list')) return false;
            const c = thumb.closest(CONTAINER_SEL);
            if (!c) return false;
            if (c.matches(PL_CONTAINER_SEL)) return true;
            return !!c.querySelector('yt-collection-thumbnail-view-model, [class*="collection-stack"], [class*="lockup-view-model--collection"]');
        } catch (_) { return false; }
    }
    function thumbTarget(thumb) {
        const a = findAnchor(thumb);        // الـ DOM بتاع يوتيوب بيتعاد استخدامه، فنقرأ الرابط وقت الضغط
        if (!a) return { video: null, playlist: null };
        const c = classify(a.href);
        return isPlaylistCard(thumb, a) ? { video: null, playlist: c.playlist } : c;
    }

    // ---------------- الإرسال للبرنامج (كل حاجة بتعدّي على نافذة التأكيد في البرنامج)
    function sendResult(res) {
        if (!res) toast(t('⚠️ The extension was updated — refresh the page'), true);
        else if (res.ok) toast(res.launched ? t('✅ The program was opened and the link was sent') : t('✅ Sent to the program'));
        else toast(t('⚠️ Could not open the program. Make sure it is installed and start it manually'), true);
    }
    
    function sendToIDM(url, quality = currentDefaultQuality, opts = {}) {
        const clean = normalizeVideoUrl(url || '');
        if (!clean) { toast(t('⚠️ No valid video to download here'), true); return; }
        toast(t('⏳ Sending to the program...'));
        bg({ action: 'add', url: clean, quality, referer: location.href, clip: !!opts.clip }).then(sendResult);
    }
    
    function sendPlaylist(listUrl, mode) {
        if (!listUrl) { toast(t('⚠️ No playlist here'), true); return; }
        toast(t('⏳ Opening the playlist in the program...'));
        bg({ action: 'add', url: listUrl, quality: currentDefaultQuality, referer: location.href, playlist: mode }).then(sendResult);
    }
    
    // ---------------- القائمة
    function addSection(panel, text) {
        const s = document.createElement('div');
        s.className = 'idm-section';
        s.textContent = text;
        panel.appendChild(s);
    }
    function addSep(panel) {
        const s = document.createElement('div');
        s.className = 'idm-sep';
        panel.appendChild(s);
    }
    function addItem(panel, widget, label, onPick) {
        const item = document.createElement('div');
        item.className = 'idm-quality-item';
        item.textContent = label;
        item.onclick = (e) => {
            e.preventDefault(); e.stopPropagation();
            closeAllDropdowns();
            onPick();
        };
        panel.appendChild(item);
    }
    function addNote(panel, text, isErr) {
        const n = document.createElement('div');
        n.className = 'idm-note' + (isErr ? ' err' : '');
        n.textContent = text;
        panel.appendChild(n);
    }
    
    function buildMenu(panel, widget, target, qualities, note) {
        panel.textContent = '';
        if (target.video) {
            addSection(panel, t('Download video'));
            if (note) addNote(panel, note.text, note.err);
            (qualities || availableQualities).forEach((q) => addItem(panel, widget, t(q), () => sendToIDM(target.video, q)));
            addSep(panel);
            addItem(panel, widget, t('✂  Download a part…'), () => sendToIDM(target.video, currentDefaultQuality, { clip: true }));
        }
        if (target.playlist) {
            if (target.video) addSep(panel);
            addSection(panel, t('Playlist'));
            addItem(panel, widget, t('📚  Whole playlist'), () => sendPlaylist(target.playlist, 'all'));
            addItem(panel, widget, t('☑  Choose videos…'), () => sendPlaylist(target.playlist, 'pick'));
        }
        if (!target.video && !target.playlist) addNote(panel, t('⚠️ No valid video here'), true);
    }
    
    const videoQualitiesCache = new Map();
    
    async function loadMenu(widget, panel) {
        const target = widget.__idmGetTarget() || {};
        if (!target.video) { buildMenu(panel, widget, target); placeMenu(); return; }
        if (videoQualitiesCache.has(target.video)) { buildMenu(panel, widget, target, videoQualitiesCache.get(target.video)); placeMenu(); return; }
        buildMenu(panel, widget, target, [], { text: t('⏳ Checking available qualities...'), err: false });
        placeMenu();
        const body = await api('/get_video_formats', { url: target.video }, 40000);
        const stillOpen = () => openMenu && openMenu.widget === widget;
        if (!stillOpen()) return;
        if (body === null) {                // البرنامج مقفول أو مش متاح: نعرض القائمة العامة (والضغط هيفتح البرنامج)
            buildMenu(panel, widget, target, availableQualities);
            placeMenu();
            return;
        }
        let list = [];
        try { list = JSON.parse(body); } catch (_) {}
        if (Array.isArray(list) && list.length) {
            videoQualitiesCache.set(target.video, list);
            buildMenu(panel, widget, target, list);
        } else {
            buildMenu(panel, widget, target, [], { text: t('⚠️ No qualities available for this video right now'), err: true });
        }
        placeMenu();
    }
    
    async function syncFromApp() {
        const lg = await api('/get_lang', {}, 2000);
        if (lg) applyLang(lg.trim());
        const q = await api('/get_default_quality', {}, 3000);
        if (q) currentDefaultQuality = q;
        const list = await api('/get_qualities', {}, 3000);
        try {
            const arr = JSON.parse(list);
            if (Array.isArray(arr) && arr.length) availableQualities = arr;
        } catch (_) {}
    }
    
    // القائمة بتتحط في <body> (position: fixed) بدل جوه الصورة المصغرة، عشان يوتيوب بيقص أي حاجة بتطلع بره الصورة.
    let openMenu = null;      // { widget, el, panel, btn }
    
    function closeAllDropdowns() {
        if (!openMenu) return;
        openMenu.el.remove();
        openMenu.widget.classList.remove('idm-open');
        openMenu = null;
    }
    
    function placeMenu() {
        if (!openMenu) return;
        const { el, btn } = openMenu;
        const r = btn.getBoundingClientRect();
        const vw = window.innerWidth, vh = window.innerHeight, m = 8;
        el.style.maxHeight = Math.max(160, vh - 2 * m) + 'px';
        const h = el.offsetHeight, w = el.offsetWidth;
        const below = vh - r.bottom - m, above = r.top - m;
        let top;
        if (h <= below || below >= above) top = r.bottom + 6;        // تحت الزرار
        else top = r.top - h - 6;                                    // فوقه لو مفيش مكان تحت
        top = Math.max(m, Math.min(top, vh - h - m));
        let left = Math.max(m, Math.min(r.left, vw - w - m));
        el.style.top = top + 'px';
        el.style.left = left + 'px';
    }
    
    function createWidget(isInside, targetGetter) {
        const widget = document.createElement('div');
        widget.className = isInside ? 'idm-inside-widget' : 'idm-thumb-widget';
        if (isInside) widget.id = 'my-idm-inside-widget';
        widget.__idmGetTarget = targetGetter;
        widget.addEventListener('click', (e) => { e.preventDefault(); e.stopPropagation(); });
        widget.addEventListener('mousedown', (e) => { e.stopPropagation(); });
    
        const btn = document.createElement('div');
        btn.className = 'idm-main-btn';
        const ico = document.createElement('img');
        ico.src = ICON_DOWNLOAD;
        ico.alt = '';
        const label = document.createElement('span');
        label.textContent = t('Download');
        const caret = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        caret.setAttribute('viewBox', '0 0 10 6');
        const poly = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        poly.setAttribute('d', 'M1 1l4 4 4-4');
        poly.setAttribute('fill', 'none');
        poly.setAttribute('stroke', 'currentColor');
        poly.setAttribute('stroke-width', '1.8');
        poly.setAttribute('stroke-linecap', 'round');
        poly.setAttribute('stroke-linejoin', 'round');
        caret.appendChild(poly);
        btn.append(ico, label, caret);
        widget.appendChild(btn);
    
        btn.onclick = (e) => {
            e.preventDefault(); e.stopPropagation();
            const wasMine = openMenu && openMenu.widget === widget;
            closeAllDropdowns();
            if (wasMine) return;
            const el = document.createElement('div');
            el.className = 'idm-dropdown';
            if (uiLang === 'ar') { el.style.direction = 'rtl'; el.style.textAlign = 'right'; }
            el.addEventListener('click', (ev) => { ev.stopPropagation(); });
            el.addEventListener('mousedown', (ev) => { ev.stopPropagation(); });
            const panel = document.createElement('div');
            panel.className = 'idm-menu-panel';
            el.appendChild(panel);
            document.documentElement.appendChild(el);
            widget.classList.add('idm-open');
            openMenu = { widget, el, panel, btn };
            syncFromApp();
            loadMenu(widget, panel);
            placeMenu();
        };
        return widget;
    }
    
    // ---------------- فحص الصفحة (MutationObserver مع throttle)
    function scan() {
        if (document.hidden) return;
        try {
            document.querySelectorAll('ytd-thumbnail, yt-thumbnail-view-model').forEach((thumb) => {
                if (thumb.dataset.idmDone) return;
                const a = findAnchor(thumb);
                if (!a) return;
                thumb.dataset.idmDone = '1';
                const widget = createWidget(false, () => thumbTarget(thumb));
                if (getComputedStyle(thumb).position === 'static') thumb.style.position = 'relative';
                thumb.appendChild(widget);
            });
    
            const onWatch = location.pathname === '/watch' && normalizeVideoUrl(location.href);
            const existing = document.getElementById('my-idm-inside-widget');
            if (!onWatch) { existing?.remove(); return; }
            const controls = document.querySelector('.ytp-right-controls');
            if (controls && !existing) controls.prepend(createWidget(true, () => classify(location.href)));
        } catch (_) { /* ignore */ }
    }
    
    let scanTimer = null;
    function scheduleScan() {
        if (scanTimer) return;
        scanTimer = setTimeout(() => { scanTimer = null; scan(); }, 500);
    }
    
    new MutationObserver(scheduleScan).observe(document.documentElement, { childList: true, subtree: true });
    window.addEventListener('yt-navigate-finish', scheduleScan);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) { scheduleScan(); syncFromApp(); } });
    
    document.addEventListener('click', () => closeAllDropdowns());
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeAllDropdowns(); });
    window.addEventListener('scroll', (e) => {            // سكرول الصفحة بيحرّك الصور، فنقفل القائمة (إلا لو السكرول جوه القائمة نفسها)
        if (openMenu && !(e.target instanceof Node && openMenu.el.contains(e.target))) closeAllDropdowns();
    }, true);
    window.addEventListener('resize', () => closeAllDropdowns());
    
    langReady.then(() => { syncFromApp(); scan(); });
    })();