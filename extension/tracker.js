// بيسجّل إن المستخدم عمل تفاعل حقيقي (ضغطة ماوس / Enter / Space) في أي صفحة أو iframe.
// الـ background بيعتمد عليه عشان ميلتقطش إلا التحميلات اللي المستخدم بدأها فعلاً.
(() => {
    let last = 0;
    const notify = (e) => {
        if (!e.isTrusted) return;                 // تجاهل الأحداث اللي الصفحة بتصطنعها بالسكريبت
        const now = Date.now();
        if (now - last < 300) return;             // throttle
        last = now;
        try {
            if (!chrome.runtime?.id) return;      // الإضافة اتحدّثت والسكريبت ده قديم
            chrome.runtime.sendMessage({ action: "user_clicked", mods: { alt: !!e.altKey, ctrl: !!e.ctrlKey, shift: !!e.shiftKey } }).catch(() => {});
        } catch (_) { /* ignore */ }
    };
    const opts = { capture: true, passive: true };
    document.addEventListener("mousedown", notify, opts);
    document.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") notify(e);
    }, opts);
})();
