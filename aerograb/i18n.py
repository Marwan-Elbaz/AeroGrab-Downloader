# -*- coding: utf-8 -*-
"""
اللغات (English / العربية).

الفكرة: النصوص في الكود بتفضل إنجليزي (علشان المنطق متتأثرش)، والترجمة بتتم على الشاشة بس:
  - tr("text")            ترجمة نص يدوياً
  - install_hooks()       بتخلّي tkinter / customtkinter يترجموا أي نص بيتعرض (أزرار، ليبلز، قوائم، تلميحات،
                          عناوين الجداول، رسائل التأكيد...) من غير ما نعدّل كل سطر في الواجهة.
لإضافة لغة أو تصحيح ترجمة: عدّل القاموس AR تحت (الإنجليزي = المفتاح). أي نص مالوش ترجمة بيظهر إنجليزي عادي.
تقدر تعرف النصوص الناقصة: شغّل البرنامج بمتغير البيئة AEROGRAB_I18N_DEBUG=1 وهيتكتب الناقص في ~/.aerograb/missing_i18n.txt
"""
import os
import re
import locale

LANGUAGES = {"en": "English", "ar": "العربية"}

_lang = {"v": "en"}
_missing = set()
_cache = {}


def detect_system_language():
    try:
        loc = (locale.getdefaultlocale()[0] or "").lower()
    except Exception:
        loc = ""
    if not loc and os.name == "nt":
        try:
            import ctypes
            lid = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
            return "ar" if lid == 0x01 else "en"
        except Exception:
            pass
    return "ar" if loc.startswith("ar") else "en"


def init_language(saved):
    """saved: 'en' | 'ar' | '' (فاضي = حسب لغة ويندوز)."""
    _lang["v"] = saved if saved in LANGUAGES else detect_system_language()
    _cache.clear()
    return _lang["v"]


def lang():
    return _lang["v"]


def is_rtl():
    return _lang["v"] == "ar"


# ----------------------------------------------------------------------------- القاموس
AR = {
    # ---- الشريط العلوي والتابات
    "Add link": "إضافة رابط", "Resume all": "استئناف الكل", "Pause all": "إيقاف الكل", "Cancel all": "إلغاء الكل",
    "Clear list": "مسح القائمة", "Settings": "الإعدادات", "All": "الكل", "Videos": "فيديو", "Audio": "صوت",
    "Archives": "أرشيف", "Programs": "برامج", "Documents": "مستندات", "Other": "أخرى", "All status": "كل الحالات",
    "In progress": "قيد التنزيل", "Paused": "متوقف مؤقتاً", "Completed": "مكتمل", "Failed": "فشل",
    "Search downloads...": "ابحث في التنزيلات...", "Language": "اللغة", "Share": "مشاركة", "History": "السجل",
    "Active downloads": "التنزيلات النشطة", "Export links": "تصدير الروابط",
    "Add a new download link  (Ctrl+N or Ctrl+V)": "إضافة رابط تنزيل جديد  (Ctrl+N أو Ctrl+V)",
    "Resume every paused, failed or canceled download": "استئناف كل التنزيلات المتوقفة أو الفاشلة أو الملغاة",
    "Pause all running downloads": "إيقاف كل التنزيلات الجارية مؤقتاً",
    "Cancel all running and queued downloads": "إلغاء كل التنزيلات الجارية وفي الانتظار",
    "Remove finished downloads from the list (files stay on disk)": "إزالة التنزيلات المنتهية من القائمة (الملفات تبقى على الجهاز)",
    "Open settings: theme, save folder, speed limit, connections...": "فتح الإعدادات: المظهر، مجلد الحفظ، حد السرعة، الاتصالات...",
    "Show all downloads": "عرض كل التنزيلات", "Filter the list by status (in progress, paused, completed, failed)": "تصفية القائمة حسب الحالة",
    "Search downloads by name or link  (Ctrl+F)": "البحث في التنزيلات بالاسم أو الرابط  (Ctrl+F)",
    "Change the language of the program": "تغيير لغة البرنامج",
    "Copy the program link to share it with others": "نسخ رابط البرنامج لمشاركته مع الآخرين",
    "Export all links to a text file": "تصدير كل الروابط إلى ملف نصي",
    "Show or hide the downloads history": "إظهار أو إخفاء سجل التنزيلات",
    "Link copied to the clipboard": "تم نسخ الرابط", "Link copied ✔": "تم نسخ الرابط ✔",
    "Downloads that are running right now (or were just completed)": "التنزيلات الجارية حالياً (أو التي اكتملت للتو)",
    "Downloads running right now": "التنزيلات الجارية الآن", "Downloads waiting for a free slot": "تنزيلات تنتظر دورها",
    "Downloads that finished successfully": "تنزيلات اكتملت بنجاح",
    "Downloads that failed. Right-click a failed download and choose Resume / Retry or Re-download": "تنزيلات فشلت. انقر بزر الماوس الأيمن واختر استئناف / إعادة المحاولة أو إعادة التنزيل",
    "Active": "نشط", "Queued": "في الانتظار", "No active downloads": "لا توجد تنزيلات نشطة",
    "Running downloads will appear here": "التنزيلات الجارية ستظهر هنا",
    "What to do automatically when all downloads finish (exit, sleep, shut down...)": "ماذا يحدث تلقائياً عند انتهاء كل التنزيلات (إغلاق، سكون، إيقاف التشغيل...)",
    "Free space on the drive where downloads are saved": "المساحة الحرة في القرص الذي تُحفظ عليه التنزيلات",
    "Overall progress of all unfinished downloads (speed, size, time remaining)": "التقدم الكلي لكل التنزيلات غير المكتملة (السرعة والحجم والوقت المتبقي)",
    "When all done:": "عند الانتهاء من الكل:", "Do nothing": "لا شيء", "Exit app": "إغلاق البرنامج", "Sleep": "سكون",
    "Hibernate": "إسبات", "Shut down": "إيقاف التشغيل", "Lock screen": "قفل الشاشة",
    "All downloads completed ✔": "اكتملت كل التنزيلات ✔",
    "No downloads yet": "لا توجد تنزيلات بعد", "Nothing matches this filter": "لا شيء يطابق هذا التصفية",
    "Click  ➕ Add link,  press Ctrl+V to paste a link,\nor use the download button on YouTube / any file in your browser.": "اضغط ➕ إضافة رابط، أو Ctrl+V للصق رابط،\nأو استخدم زر التنزيل على يوتيوب / أي ملف في المتصفح.",
    "Try another file type / status, or clear the search box.": "جرّب نوع ملف / حالة أخرى، أو امسح خانة البحث.",
    # ---- رؤوس الجدول
    "Name": "الاسم", "Type": "النوع", "Size": "الحجم", "%": "%", "Speed": "السرعة", "ETA": "المتبقي", "Status": "الحالة",
    "Date": "التاريخ", "Folder": "المجلد",
    "Video": "فيديو", "Archive": "أرشيف", "Program": "برنامج", "Document": "مستند", "Unknown": "غير معروف",
    "Size unknown": "الحجم غير معروف", "File": "ملف", "Files": "ملفات", "Docs": "مستندات",
    # ---- قائمة الكليك يمين
    "Resume / Retry": "استئناف / إعادة المحاولة", "Pause": "إيقاف مؤقت", "Download this first": "نزّل هذا أولاً",
    "Move up in queue": "تحريك لأعلى في الطابور", "Move down in queue": "تحريك لأسفل في الطابور",
    "Cancel Download": "إلغاء التنزيل", "Remove from List": "إزالة من القائمة", "Open File": "فتح الملف",
    "Open Folder": "فتح المجلد", "Copy link": "نسخ الرابط", "Properties": "الخصائص",
    "Verify checksum...": "التحقق من checksum...", "Refresh link...": "تحديث الرابط...", "Re-download": "إعادة التنزيل",
    "Delete File From Device": "حذف الملف من الجهاز",
    # ---- استهلاك البيانات
    "Data usage": "استهلاك البيانات", "Daily or monthly data limit and usage counter": "حد استهلاك يومي أو شهري وعدّاد الاستهلاك",
    "Data limit": "حد الاستهلاك", "Limit my data usage": "تحديد حد لاستهلاك الإنترنت", "Period": "الفترة", "Daily": "يومي",
    "Monthly": "شهري", "Custom period": "فترة مخصصة", "Limit": "الحد", "Resets on day": "يبدأ من يوم", "of each month (1-28)": "من كل شهر (1-28)",
    "Every": "كل", "days, starting": "يوم، بدءاً من", "Apply": "تطبيق", "✔ Saved": "✔ تم الحفظ",
    "Enter the limit as a number greater than zero, for example 10.": "اكتب الحد كرقم أكبر من الصفر، مثلاً 10.",
    "The reset day must be a number from 1 to 28.": "يوم بداية الشهر لازم يكون رقماً من 1 إلى 28.",
    "Enter the number of days (1 to 366).": "اكتب عدد الأيام (من 1 إلى 366).",
    "Enter the start date as YYYY-MM-DD, for example 2026-11-01.": "اكتب تاريخ البداية بصيغة YYYY-MM-DD، مثلاً 2026-11-01.",
    "When the limit is reached, running downloads pause and new ones wait until the next period starts. You can also choose to continue anyway for the current period.":
        "عند الوصول إلى الحد تتوقف التنزيلات الشغّالة وتنتظر الجديدة حتى تبدأ الفترة التالية. ويمكنك اختيار المتابعة رغم ذلك في الفترة الحالية.",
    "Current usage": "الاستهلاك الحالي", "Continue anyway (this period)": "متابعة رغم ذلك (هذه الفترة)", "Reset counter": "تصفير العدّاد",
    "Reset the usage counter of the current period to zero?": "هل تريد تصفير عدّاد الاستهلاك للفترة الحالية؟",
    "Last 7 days": "آخر 7 أيام", "No data limit is set.": "لم يتم تحديد حد للاستهلاك.",
    "Counts the data this program downloads (files and videos). It is not your whole computer's internet usage, and small requests such as video info and thumbnails are not counted.":
        "يحسب البيانات التي ينزّلها هذا البرنامج (ملفات وفيديوهات). ليس استهلاك الإنترنت لكل الجهاز، ولا يشمل الطلبات الصغيرة مثل معلومات الفيديو والصور المصغّرة.",
    "Data usage settings…": "إعدادات استهلاك البيانات…", "Data used by this program. Click for the data limit options": "البيانات التي استهلكها هذا البرنامج. اضغط لخيارات حد الاستهلاك",
    "Data limit reached": "تم الوصول إلى حد الاستهلاك", "📊 Data limit reached": "📊 تم الوصول إلى حد الاستهلاك",
    "📊 Data limit reached: waiting for the next period": "📊 تم الوصول إلى حد الاستهلاك: في انتظار الفترة القادمة",
    "You have used 90% of your data limit for this period.": "لقد استهلكت 90% من حد الاستهلاك في هذه الفترة.",
    "You reached your data limit. Downloads are paused until the next period starts.\n\nContinue downloading anyway for this period?":
        "وصلت إلى حد الاستهلاك. التنزيلات متوقفة حتى تبدأ الفترة القادمة.\n\nهل تريد المتابعة رغم ذلك في هذه الفترة؟",
    # ---- الكروت
    "Open the folder containing the file": "فتح المجلد الذي يحتوي الملف", "Open the downloaded file": "فتح الملف المنزّل",
    "Dismiss this card from Active downloads (the file stays in the list)": "إخفاء هذا الكارت من التنزيلات النشطة (الملف يبقى في القائمة)",
    "Remove from list": "إزالة من القائمة", "Pause download": "إيقاف التنزيل مؤقتاً", "Resume download": "استئناف التنزيل",
    "Retry download": "إعادة محاولة التنزيل", "Not available": "غير متاح", "The file was moved or deleted.": "تم نقل الملف أو حذفه.",
    "Pausing…": "جارٍ الإيقاف…", "Canceling…": "جارٍ الإلغاء…", "Connecting…": "جارٍ الاتصال…",
    "Waiting in the queue…": "في انتظار الدور…", "Merging…": "جارٍ الدمج…", "Downloading": "جارٍ التنزيل",
    "Connecting": "جارٍ الاتصال", "Merging": "جارٍ الدمج", "Canceled": "ملغي", "File deleted": "تم حذف الملف",
    "Done": "تم", "Downloads": "التنزيلات",
    # ---- حالات التنزيل
    "Queued...": "في الانتظار...", "Reading video info...": "جارٍ قراءة معلومات الفيديو...", "Starting ffmpeg...": "جارٍ تشغيل ffmpeg...",
    "Downloading the selected part...": "جارٍ تنزيل الجزء المحدد...", "Cutting precisely (re-encoding)...": "جارٍ القص الدقيق (إعادة ترميز)...", "Precise cut re-encodes the part (slower). Turn it off for an instant cut at the nearest keyframe.": "القص الدقيق بيعيد ترميز الجزء (أبطأ). اقفله لقص فوري عند أقرب إطار رئيسي.", "Joining the parts...": "جارٍ دمج الأجزاء...",
    "Connecting...": "جارٍ الاتصال...", "Starting download...": "جارٍ بدء التنزيل...", "Downloading...": "جارٍ التنزيل...",
    "Merging (Video + Audio)...": "جارٍ دمج (فيديو + صوت)...", "Embedding Thumbnail...": "جارٍ تضمين الصورة المصغرة...",
    "Converting to H.264 (compatibility)...": "جارٍ التحويل إلى H.264 (للتوافق)...", "Canceled and deleted": "أُلغي وحُذف",
    "Completed successfully": "اكتمل بنجاح", "Pausing...": "جارٍ الإيقاف المؤقت...", "Canceling...": "جارٍ الإلغاء...",
    "New link saved, resuming...": "تم حفظ الرابط الجديد، جارٍ الاستئناف...", "Paused (App closed previously)": "متوقف (أُغلق البرنامج سابقاً)",
    "Unknown Error": "خطأ غير معروف", "Unknown error": "خطأ غير معروف",
    "⚠️ Failed: cutting a part needs ffmpeg and a video link (Right-click to retry)": "⚠️ فشل: قص جزء يحتاج ffmpeg ورابط فيديو (كليك يمين لإعادة المحاولة)",
    "⚠️ Unexpected error (Right-click to retry)": "⚠️ خطأ غير متوقع (كليك يمين لإعادة المحاولة)",
    "🗑️ Deleted from device": "🗑️ تم الحذف من الجهاز", "⚠️ File not found on device": "⚠️ الملف غير موجود على الجهاز",
    "YouTube wants sign-in (put cookies.txt next to the app)": "يوتيوب يطلب تسجيل الدخول (ضع ملف cookies.txt بجوار البرنامج)",
    "Age-restricted video (needs cookies.txt)": "فيديو مقيّد بالعمر (يحتاج cookies.txt)", "Private video": "فيديو خاص",
    "Video unavailable": "الفيديو غير متاح", "ffmpeg is missing or failed": "ffmpeg غير موجود أو فشل",
    "Disk is full: free some space, then Resume": "القرص ممتلئ: وفّر مساحة ثم اضغط استئناف",
    "Link expired (410): right-click > Refresh link": "انتهت صلاحية الرابط (410): كليك يمين > تحديث الرابط",
    "Access denied (403): if the link expired, right-click > Refresh link": "تم رفض الوصول (403): إن انتهت صلاحية الرابط فكليك يمين > تحديث الرابط",
    "File not found (404)": "الملف غير موجود (404)", "Too many requests (429), try later": "طلبات كثيرة (429)، حاول لاحقاً",
    "Selected quality is not available": "الجودة المختارة غير متاحة",
    "Selected quality is not available for this video (pick another quality)": "الجودة المختارة غير متاحة لهذا الفيديو (اختر جودة أخرى)",
    "Trying another method...": "جارٍ تجربة طريقة أخرى...", "Network problem": "مشكلة في الشبكة",
    "No permission to write in the save folder": "لا توجد صلاحية للكتابة في مجلد الحفظ",
    "Unlimited": "بلا حد", "Waiting for schedule": "في انتظار الجدولة",
    # ---- النوافذ المنبثقة (إضافة/تنزيل)
    "Download": "تنزيل", "Fetching video info…": "جارٍ جلب معلومات الفيديو…", "(part)": "(جزء)",
    "Check the times (e.g. 90 · 1:30 · 01:02:03)": "راجع الأوقات (مثل 90 · 1:30 · 01:02:03)", "Whole video": "الفيديو كاملاً",
    "Audio Only": "صوت فقط", "Quality": "الجودة", "✂  Download only a part of the video": "✂  تنزيل جزء فقط من الفيديو",
    "From": "من", "to": "إلى", "Precise cut": "قص دقيق",
    "ffmpeg not found — install it (winget install ffmpeg) or put ffmpeg.exe next to the program, then reopen this window to enable this.": "ffmpeg غير موجود — ثبّته (winget install ffmpeg) أو ضع ffmpeg.exe بجوار البرنامج ثم أعد فتح هذه النافذة.",
    "📚  Part of a playlist — choose videos…": "📚  جزء من قائمة تشغيل — اختر الفيديوهات…",
    "Save to": "حفظ في", "Browse": "استعراض", "Download a part": "تنزيل جزء",
    "Please check the start / end times.\nExamples: 90   1:30   01:02:03": "راجع وقت البداية / النهاية.\nأمثلة: 90   1:30   01:02:03",
    "Cancel": "إلغاء", "Start Download": "بدء التنزيل", "📁 Choose Save Directory...": "📁 اختر مجلد الحفظ...",
    "Playlist": "قائمة تشغيل", "📚  Loading playlist…": "📚  جارٍ تحميل قائمة التشغيل…",
    "⚠  No videos found in this playlist.": "⚠  لا توجد فيديوهات في قائمة التشغيل هذه.", "🔍  Filter…": "🔍  تصفية…",
    "Duration": "المدة", "Title": "العنوان", "Select all": "تحديد الكل", "Select none": "إلغاء التحديد", "Invert": "عكس التحديد",
    "Folder for this playlist": "مجلد لهذه القائمة", "Number the files (01 - …)": "ترقيم الملفات (01 - …)", "Add": "إضافة",
    "⬇  Download selected": "⬇  تنزيل المحدد", "Add Download": "إضافة تنزيل", "Enter one or more links (one per line):": "أدخل رابطاً أو أكثر (رابط في كل سطر):",
    "Tip: for a numbered series use  http://site.com/img[001-050].jpg": "نصيحة: للسلاسل المرقمة استخدم  http://site.com/img[001-050].jpg",
    "📋 Paste": "📋 لصق", "Import links": "استيراد روابط", "All files": "كل الملفات", "Text / lists": "نصوص / قوائم",
    "Import": "استيراد", "No links were found in that file.": "لم يتم العثور على روابط في هذا الملف.",
    "Pattern too large": "النمط كبير جداً", "Invalid Link": "رابط غير صالح", "No valid URL found.": "لم يتم العثور على رابط صالح.",
    "Add many downloads": "إضافة تنزيلات كثيرة", "Notice": "تنبيه", "Ignored": "تم تجاهل",
    "Paste a playlist link first.": "الصق رابط قائمة تشغيل أولاً.", "📂 Import from file…": "📂 استيراد من ملف…",
    "📚 Playlist…": "📚 قائمة تشغيل…", "⬇️ Download All": "⬇️ تنزيل الكل",
    "Invalid URL": "رابط غير صالح", "Please enter a valid URL starting with http:// or https://": "أدخل رابطاً صالحاً يبدأ بـ http:// أو https://",
    "Save folder problem": "مشكلة في مجلد الحفظ", "Already Exists": "موجود بالفعل", "This URL is already in the download queue.": "هذا الرابط موجود بالفعل في قائمة التنزيل.",
    "This video has already been downloaded before.\nDo you want to download it again?": "تم تنزيل هذا الفيديو من قبل.\nهل تريد تنزيله مرة أخرى؟",
    "⚠️ Duplicate Download": "⚠️ تنزيل مكرر", "Invalid time range": "نطاق زمني غير صالح",
    "Enter a valid link starting with http:// or https://": "أدخل رابطاً صالحاً يبدأ بـ http:// أو https://",
    "Download not found": "التنزيل غير موجود", "Pause the download first, then refresh its link": "أوقف التنزيل مؤقتاً أولاً ثم حدّث رابطه",
    "This download is already finished": "هذا التنزيل منتهٍ بالفعل",
    "Are you sure you want to cancel ALL downloads?": "هل أنت متأكد أنك تريد إلغاء كل التنزيلات؟", "Confirm Cancel All": "تأكيد إلغاء الكل",
    "Confirm Remove": "تأكيد الإزالة", "Remove the selected item(s) from the list?\n(Downloaded files are kept.)": "إزالة العناصر المحددة من القائمة؟\n(الملفات المنزّلة تبقى على الجهاز.)",
    "⚠️ Delete From Device": "⚠️ حذف من الجهاز",
    "This will PERMANENTLY delete the downloaded file(s) from your device.\nThis cannot be undone. Continue?": "سيتم حذف الملفات المنزّلة نهائياً من جهازك.\nلا يمكن التراجع. هل تريد المتابعة؟",
    "The file is not downloaded yet (or was moved/deleted).": "لم يتم تنزيل الملف بعد (أو تم نقله / حذفه).",
    "Clear the list? (Downloaded files will not be deleted)": "مسح القائمة؟ (الملفات المنزّلة لن تُحذف)",
    "There are active downloads. Cancel them and clear the list?\n(Downloaded files will not be deleted)": "هناك تنزيلات نشطة. هل تريد إلغاءها ومسح القائمة؟\n(الملفات المنزّلة لن تُحذف)",
    "Confirm": "تأكيد", "Error": "خطأ", "Not found": "غير موجود", "The file or folder no longer exists.": "الملف أو المجلد لم يعد موجوداً.",
    # ---- روابط / تحديث رابط / checksum
    "Select a download": "اختر تنزيلاً", "Select a download in the list first.": "اختر تنزيلاً من القائمة أولاً.", "this download": "هذا التنزيل",
    "Refresh link": "تحديث الرابط", "This download is already finished.": "هذا التنزيل منتهٍ بالفعل.", "Refresh download link": "تحديث رابط التنزيل",
    "New link:": "الرابط الجديد:", "Refresh and resume": "تحديث واستئناف",
    "Only a finished download whose file still exists can be verified.": "يمكن التحقق فقط من تنزيل مكتمل ملفه ما زال موجوداً.",
    "Verify checksum": "التحقق من checksum", "Verify file integrity": "التحقق من سلامة الملف",
    "Paste the checksum the publisher gives for this file (MD5, SHA-1, SHA-256 or SHA-512). If it matches, the file is exactly the one they published.": "الصق قيمة checksum التي ينشرها الناشر لهذا الملف (MD5 أو SHA-1 أو SHA-256 أو SHA-512). إذا تطابقت فالملف هو نفسه المنشور تماماً.",
    "Expected checksum (optional)": "قيمة checksum المتوقعة (اختياري)", "Algorithm:": "الخوارزمية:", "Auto": "تلقائي",
    "✔ Match: the file is intact": "✔ متطابق: الملف سليم", "✖ Does NOT match: the file is damaged or different": "✖ غير متطابق: الملف تالف أو مختلف",
    "That is not a valid MD5 / SHA-1 / SHA-256 / SHA-512 checksum.": "هذه ليست قيمة MD5 / SHA-1 / SHA-256 / SHA-512 صالحة.",
    "Checking...": "جارٍ الفحص...", "Verify": "تحقق", "Copy result": "نسخ النتيجة",
    "Link Grabber": "مُلتقط الروابط", "🔗  Link Grabber": "🔗  مُلتقط الروابط", "🔍  Filter...": "🔍  تصفية...", "Link Grabber ": "مُلتقط الروابط",
    "Select at least one link first.": "اختر رابطاً واحداً على الأقل أولاً.", "Programs ": "برامج",
    "Selected: 0": "المحدد: 0", "⬇  Download selected (0)": "⬇  تنزيل المحدد (0)",
    "Are you sure you want to close the application completely?": "هل أنت متأكد أنك تريد إغلاق البرنامج بالكامل؟", "Confirm Exit": "تأكيد الإغلاق",
    "Mon": "الاثنين", "Tue": "الثلاثاء", "Wed": "الأربعاء", "Thu": "الخميس", "Fri": "الجمعة", "Sat": "السبت", "Sun": "الأحد",
    "Music": "موسيقى", "Compressed": "مضغوطة", "General": "عام",
    # ---- الخصائص / إشعارات
    "Link": "الرابط", "Added": "أُضيف", "Saved to": "حُفظ في", "Referer": "المرجع", "Part": "جزء", "🔗 Copy link": "🔗 نسخ الرابط",
    "📁 Open folder": "📁 فتح المجلد", "Close": "إغلاق", "Open": "فتح", "✔  Download complete": "✔  اكتمل التنزيل",
    "Export": "تصدير", "The list is empty.": "القائمة فارغة.", "Text file": "ملف نصي",
    "Downloads finished": "انتهت التنزيلات", "✔  All downloads are finished": "✔  انتهت كل التنزيلات",
    "Still downloading": "ما زال التنزيل جارياً",
    "Downloads continue in the background.\nOpen the app again (or click a download in the browser) to bring this window back.": "التنزيلات تستمر في الخلفية.\nافتح البرنامج مرة أخرى (أو اضغط على تنزيل في المتصفح) لإظهار هذه النافذة.",
    "Keep running in the background?\n\nYes: keep downloading / watching the browser\nNo: exit the program completely": "هل تريد إبقاء البرنامج يعمل في الخلفية؟\n\nنعم: استمرار التنزيل ومراقبة المتصفح\nلا: إغلاق البرنامج بالكامل",
    # ---- الإعدادات: الأقسام
    "Appearance, startup, notifications and sounds": "المظهر والتشغيل والإشعارات والأصوات",
    "Speed limit, connections, retries and timeouts": "حد السرعة والاتصالات وإعادة المحاولة والمهلات",
    "Default quality and compatibility mode": "الجودة الافتراضية ووضع التوافق", "Where downloads are saved": "مكان حفظ التنزيلات",
    "Which files the browser extension sends to this program": "الملفات التي ترسلها إضافة المتصفح إلى هذا البرنامج",
    "Browser extension: capture, keys and right-click menu": "إضافة المتصفح: الالتقاط والمفاتيح وقائمة الكليك يمين",
    "Proxy, user-agent and site logins": "البروكسي وهوية المتصفح وتسجيلات دخول المواقع",
    "Download only at certain hours": "التنزيل في ساعات معينة فقط", "ffmpeg, cookies file, logs and data": "ffmpeg وملف الكوكيز والسجلات والبيانات",
    "Engine and extension versions": "إصدارات المحرك والإضافة", "About AeroGrab, privacy and credits": "عن AeroGrab والخصوصية والشكر",
    "File types": "أنواع الملفات", "Browser": "المتصفح", "Network": "الشبكة", "Schedule": "الجدولة", "Tools": "الأدوات", "Updates": "التحديثات",
    "About": "حول", "Video ": "فيديو", "Save to ": "حفظ في",
    "Close App Completely": "إغلاق البرنامج تماماً", "Exit the program completely (stops downloads and the browser connection)": "إغلاق البرنامج بالكامل (يوقف التنزيلات واتصال المتصفح)",
    "Keep running in the background": "يستمر في الخلفية", "Exit the program": "إغلاق البرنامج", "Ask me": "اسألني",
    "Automatic": "تلقائي", "15 seconds": "15 ثانية", "30 seconds": "30 ثانية", "60 seconds": "60 ثانية", "2 minutes": "دقيقتان",
    "None": "بدون",
    # ---- الإعدادات: عام
    "Appearance": "المظهر", "Dark": "داكن", "Light": "فاتح", "Startup and window": "التشغيل والنافذة",
    "Start in the background with Windows": "التشغيل في الخلفية مع ويندوز",
    "The program starts hidden and waits for downloads from the browser": "يبدأ البرنامج مخفياً وينتظر التنزيلات من المتصفح",
    "Resume downloads that were running when the program was closed": "استئناف التنزيلات التي كانت تعمل عند إغلاق البرنامج",
    "Paused downloads (App closed previously) restart by themselves when the program opens": "التنزيلات المتوقفة (أُغلق البرنامج سابقاً) تستأنف تلقائياً عند فتح البرنامج",
    "When I click the window's close button (✕):": "عند الضغط على زر إغلاق النافذة (✕):",
    "Keeping it in the background lets the browser extension keep sending downloads": "إبقاؤه في الخلفية يسمح لإضافة المتصفح بمتابعة إرسال التنزيلات",
    "Clipboard": "الحافظة", "Watch the clipboard (offer to download copied links)": "مراقبة الحافظة (اقتراح تنزيل الروابط المنسوخة)",
    "Notifications and sounds": "الإشعارات والأصوات", "Show a notification when a download finishes": "إظهار إشعار عند انتهاء التنزيل",
    "Play a sound when a download finishes": "تشغيل صوت عند انتهاء التنزيل",
    "Custom sound (.wav) — leave empty for the system sound:": "صوت مخصص (.wav) — اتركه فارغاً لصوت النظام:",
    "Test sound": "تجربة الصوت", "When a download finishes:": "عند انتهاء التنزيل:", "Open the file": "فتح الملف", "Open the folder": "فتح المجلد",
    "Confirmations": "التأكيدات", "Ask before removing items from the list": "السؤال قبل إزالة العناصر من القائمة",
    "Ask before deleting files from the device": "السؤال قبل حذف الملفات من الجهاز",
    "Turning this off makes “Delete File From Device” permanent without a question": "إيقافه يجعل «حذف الملف من الجهاز» نهائياً بدون سؤال",
    "Clear": "مسح", "Could not change the startup setting.": "تعذّر تغيير إعداد التشغيل مع ويندوز.",
    "Interface language": "لغة الواجهة", "Restart now": "إعادة التشغيل الآن",
    "The program will restart to apply the language.": "سيُعاد تشغيل البرنامج لتطبيق اللغة.",
    "Downloads that are running will be paused and can be resumed after the restart.": "التنزيلات الجارية ستتوقف مؤقتاً ويمكن استئنافها بعد إعادة التشغيل.",
    "Restart": "إعادة التشغيل",
    # ---- الإعدادات: تنزيلات
    "Speed limit": "حد السرعة", "Custom (KB/s):": "مخصص (KB/s):", "Set": "تطبيق", "Custom": "مخصص",
    "Enter a whole number of KB/s (0 = unlimited).": "أدخل رقماً صحيحاً بوحدة KB/s (0 = بلا حد).",
    "Connections": "الاتصالات", "Max concurrent downloads:": "أقصى عدد للتنزيلات المتزامنة:",
    "Connections per download (the file is split into parts):": "عدد الاتصالات لكل تنزيل (الملف يُقسّم إلى أجزاء):",
    "More connections can be faster, but some servers limit them": "اتصالات أكثر قد تعني سرعة أعلى، لكن بعض الخوادم تحدّها",
    "Reliability": "الاعتمادية", "Automatic retries after a temporary error (403, 429, dropped connection):": "إعادة المحاولة تلقائياً بعد خطأ مؤقت (403، 429، انقطاع الاتصال):",
    "Each retry uses fewer connections and a fresh link": "كل محاولة تستخدم اتصالات أقل ورابطاً جديداً", "Connection timeout:": "مهلة الاتصال:",
    "How long to wait for a server before giving up": "مدة انتظار الخادم قبل الاستسلام",
    "Unlimited ": "بلا حد", "128 KB/s": "128 KB/s",
    # ---- فيديو
    "Default video quality": "جودة الفيديو الافتراضية", "Compatibility": "التوافق",
    "Compatibility mode (H.264 video + AAC audio)": "وضع التوافق (فيديو H.264 + صوت AAC)",
    "Plays on old PCs, TVs and phones. Needs ffmpeg": "يعمل على الأجهزة القديمة والتلفزيونات والهواتف. يحتاج ffmpeg",
    "Videos in other formats are converted after the download. Turn it off for the original quality and faster finishing.": "الفيديوهات بصيغ أخرى تُحوَّل بعد التنزيل. أوقفه للحصول على الجودة الأصلية وانتهاء أسرع.",
    # ---- حفظ
    "Save folder": "مجلد الحفظ", "Change": "تغيير", "Sort downloads by type": "ترتيب التنزيلات حسب النوع",
    "Save each type in its own folder": "حفظ كل نوع في مجلد خاص",
    "Leave a box empty to use  <save folder>/<type name>.  Applies to new downloads.": "اترك الخانة فارغة لاستخدام  <مجلد الحفظ>/<اسم النوع>.  يُطبّق على التنزيلات الجديدة.",
    "Save folders": "حفظ المجلدات", "Saved.": "تم الحفظ.",
    # ---- أنواع الملفات
    "Files sent to this program": "الملفات المرسلة إلى هذا البرنامج",
    "When you click a download in the browser, the extension takes it over only if its type is in this list (separate with commas or spaces). Everything else is downloaded by the browser as usual.": "عند الضغط على تنزيل في المتصفح تلتقطه الإضافة فقط إذا كان نوعه في هذه القائمة (افصل بفواصل أو مسافات). أي شيء آخر يُنزّله المتصفح كالمعتاد.",
    "Add at least one file type (example: zip, mp4, pdf).": "أضف نوع ملف واحداً على الأقل (مثال: zip, mp4, pdf).",
    "Restored the default list.": "تمت استعادة القائمة الافتراضية.", "Save": "حفظ", "Restore defaults": "استعادة الافتراضي",
    "Size limits and detection": "حدود الحجم والكشف", "Ignore documents (PDF, Office) smaller than:": "تجاهل المستندات (PDF وOffice) الأصغر من:",
    "Never ignore": "لا تتجاهل أبداً", "Small documents are usually opened in the browser, not downloaded": "المستندات الصغيرة تُفتح غالباً في المتصفح ولا تُنزَّل",
    "Files with no known type must be at least:": "الملفات غير المعروفة النوع يجب أن تكون على الأقل:",
    "Applies to generic binary downloads (application/octet-stream)": "يُطبّق على التنزيلات الثنائية العامة (application/octet-stream)",
    "Also take over video and audio streams by their content type": "التقاط بثوث الفيديو والصوت أيضاً حسب نوع المحتوى",
    "Only take over downloads that I started with a click": "التقاط التنزيلات التي بدأتها بنقرة فقط",
    "Prevents pages from starting downloads behind your back": "يمنع الصفحات من بدء تنزيلات دون علمك",
    # ---- المتصفح
    "Browser extension": "إضافة المتصفح", "●  No contact from the extension yet since this program started.": "●  لا يوجد اتصال من الإضافة منذ تشغيل البرنامج.",
    "just now": "الآن",
    "Load the extension folder in your browser (chrome://extensions → Developer mode → Load unpacked). Changes you make in this window reach the extension within about a minute.": "حمّل مجلد الإضافة في المتصفح (chrome://extensions ← وضع المطوّر ← Load unpacked). التغييرات هنا تصل للإضافة خلال دقيقة تقريباً.",
    "Capturing downloads": "التقاط التنزيلات", "Take over downloads started in the browser": "التقاط التنزيلات التي تبدأ في المتصفح",
    "Turn off to let the browser download everything itself (right-click menu items still work)": "أوقفه ليُنزّل المتصفح كل شيء بنفسه (عناصر قائمة الكليك يمين تعمل)",
    "Hold this key while clicking a link to let the browser download it:": "اضغط هذا المفتاح أثناء النقر على رابط ليُنزّله المتصفح:",
    "Same idea as IDM's “Alt = don't take over” key": "نفس فكرة مفتاح IDM «Alt = لا تلتقط»",
    "Right-click menu in the browser": "قائمة الكليك يمين في المتصفح", "Choose which items appear when you right-click in the browser.": "اختر العناصر التي تظهر عند الكليك يمين في المتصفح.",
    # ---- الشبكة
    "Proxy": "بروكسي", "Proxy type:": "نوع البروكسي:", "Host (proxy.example.com)": "المضيف (proxy.example.com)", "Port": "المنفذ",
    "User (optional)": "المستخدم (اختياري)", "Password (optional)": "كلمة السر (اختياري)", "Proxy is off.": "البروكسي متوقف.",
    "Enter a host and a port number (for example 8080).": "أدخل المضيف ورقم المنفذ (مثل 8080).", "Turn off": "إيقاف",
    "Video sites support HTTP and SOCKS proxies. Direct file downloads support HTTP/HTTPS proxies only.": "مواقع الفيديو تدعم بروكسي HTTP وSOCKS. التنزيل المباشر للملفات يدعم HTTP/HTTPS فقط.",
    "User-Agent": "هوية المتصفح (User-Agent)", "Use default": "استخدام الافتراضي",
    "Used for video sites and for downloads where the browser did not send its own identity. Leave empty for the default.": "تُستخدم لمواقع الفيديو وللتنزيلات التي لم يرسل المتصفح هويته معها. اتركها فارغة للافتراضي.",
    "Site logins": "تسجيلات دخول المواقع", "No saved logins.": "لا توجد تسجيلات محفوظة.", "Remove": "حذف", "Username": "اسم المستخدم", "Password": "كلمة السر",
    "Enter the site and the username.": "أدخل الموقع واسم المستخدم.",
    "Username and password sent (HTTP Basic) when downloading files from a site. Stored on this PC in the settings file, not encrypted.": "اسم المستخدم وكلمة السر يُرسلان (HTTP Basic) عند تنزيل ملفات من موقع. تُحفظ على هذا الجهاز في ملف الإعدادات بدون تشفير.",
    "Login-protected downloads": "التنزيلات المحمية بتسجيل دخول",
    "Files you click in the browser are sent with your browser's cookies and user-agent, so downloads that need a login work. For age-restricted YouTube videos choose a cookies.txt file in Tools.": "الملفات التي تضغط عليها في المتصفح تُرسل مع كوكيز المتصفح وهويته، فتعمل التنزيلات التي تحتاج تسجيل دخول. لفيديوهات يوتيوب المقيّدة بالعمر اختر ملف cookies.txt من الأدوات.",
    # ---- الجدولة
    "Download schedule": "جدول التنزيل", "Only download during these hours": "التنزيل خلال هذه الساعات فقط", "Apply schedule": "تطبيق الجدول",
    "Schedule is off: downloads run any time.": "الجدولة متوقفة: التنزيل في أي وقت.", "✔ Now: downloads are allowed": "✔ الآن: التنزيل مسموح",
    "Now: waiting for the schedule": "الآن: في انتظار الجدولة", "Select at least one day.": "اختر يوماً واحداً على الأقل.",
    "Enter the start time as HH:MM, for example 02:00.": "أدخل وقت البداية بصيغة HH:MM مثل 02:00.",
    "Enter the stop time as HH:MM, for example 06:00 (or leave it empty).": "أدخل وقت التوقف بصيغة HH:MM مثل 06:00 (أو اتركه فارغاً).",
    "Downloads pause outside the window and resume by themselves. A window like 23:00 to 06:00 runs overnight. With no stop time it runs until midnight.": "تتوقف التنزيلات خارج الفترة وتستأنف تلقائياً. فترة مثل 23:00 إلى 06:00 تعمل طوال الليل. بدون وقت توقف تعمل حتى منتصف الليل.",
    # ---- أدوات
    "Cookies file": "ملف الكوكيز", "Path to ffmpeg (leave empty to detect automatically):": "مسار ffmpeg (اتركه فارغاً للكشف التلقائي):",
    "ffmpeg was not found. Merging video and cutting parts need it.": "لم يتم العثور على ffmpeg. دمج الفيديو وقص الأجزاء يحتاجانه.",
    "A cookies.txt exported from your browser lets video sites treat you as logged in (age-restricted or members-only videos).": "ملف cookies.txt المُصدَّر من متصفحك يجعل مواقع الفيديو تعتبرك مسجلاً للدخول (فيديوهات مقيّدة بالعمر أو للأعضاء).",
    "Data and logs": "البيانات والسجلات", "Open data folder": "فتح مجلد البيانات", "Open log file": "فتح ملف السجل", "Export all links": "تصدير كل الروابط",
    "Clear saved parts": "مسح الأجزاء المحفوظة", "Clear cache": "مسح الذاكرة المؤقتة",
    "Some paused downloads would restart from the beginning. Continue?": "بعض التنزيلات المتوقفة ستبدأ من البداية. هل تريد المتابعة؟",
    "Browse ": "استعراض",
    # ---- التحديثات
    "Download engine (yt-dlp)": "محرك التنزيل (yt-dlp)", "Check for engine update": "فحص تحديث المحرك", "Checking for updates...": "جارٍ البحث عن تحديثات...",
    "⚠️ Update check failed (check your internet).": "⚠️ فشل فحص التحديث (تحقق من الإنترنت).", "Versions": "الإصدارات",
    "Program updates": "تحديثات البرنامج", "Check for program update": "فحص تحديث البرنامج",
    "Check for updates automatically": "البحث عن تحديثات تلقائياً",
    "The program checks for a new version when it starts and every few hours, then asks before installing.": "يبحث البرنامج عن إصدار جديد عند التشغيل وكل بضع ساعات، ثم يسأل قبل التثبيت.",
    "Update available": "يوجد تحديث", "Update now": "حدّث الآن", "Later": "لاحقاً", "What's new": "الجديد",
    "A new version of AeroGrab is available.": "يوجد إصدار جديد من AeroGrab.", "Downloading the update...": "جارٍ تنزيل التحديث...",
    "The update is ready. AeroGrab will restart to finish installing it.": "التحديث جاهز. سيُعاد تشغيل AeroGrab لإكمال التثبيت.",
    "You have the latest version.": "لديك أحدث إصدار.", "Could not check for updates (check your internet).": "تعذّر البحث عن تحديثات (تحقق من الإنترنت).",
    "Update failed": "فشل التحديث", "Open the download page": "فتح صفحة التنزيل",
    "Update link is not set yet (see aerograb/links.py).": "رابط التحديث غير مضبوط بعد (راجع aerograb/links.py).",
    # ---- حول
    "Fast, private download manager for Windows": "مدير تنزيلات سريع وخاص لنظام ويندوز", "Your privacy": "خصوصيتك",
    "No ads, no account, no analytics. Your download list, settings and saved logins stay on this PC. The program only goes online for the downloads you start, the video thumbnails of links you add, and the engine update check when you press the button in Updates.": "بدون إعلانات، بدون حساب، بدون تحليلات. قائمة التنزيلات والإعدادات وتسجيلات الدخول تبقى على هذا الجهاز. البرنامج يتصل بالإنترنت فقط للتنزيلات التي تبدؤها، وصور الفيديوهات المصغرة للروابط التي تضيفها، وفحص تحديثات البرنامج والمحرك.",
    "What it does": "ماذا يفعل", "Credits": "الشكر", "Video support is powered by yt-dlp and ffmpeg.": "دعم الفيديو يعمل بفضل yt-dlp وffmpeg.",
    "• Splits files into parts for faster downloads, with pause, resume and automatic retries\n• Takes over downloads from your browser (Alt = let the browser handle it)\n• Downloads videos and playlists, or only a part of a video, with resume\n• Queue, schedule, speed limit, categories, link grabber and clipboard watching\n• Refresh an expired link and keep the part you already downloaded\n• Check a file's SHA-256 / SHA-1 / MD5 against the hash the publisher gives you": "• يقسّم الملفات إلى أجزاء لتنزيل أسرع مع إيقاف مؤقت واستئناف وإعادة محاولة تلقائية\n• يلتقط التنزيلات من المتصفح (Alt = اترك المتصفح يتعامل معها)\n• ينزّل الفيديوهات وقوائم التشغيل أو جزءاً من الفيديو مع الاستئناف\n• طابور وجدولة وحد سرعة وتصنيفات ومُلتقط روابط ومراقبة الحافظة\n• تحديث رابط منتهي مع الاحتفاظ بالجزء المنزّل\n• فحص SHA-256 / SHA-1 / MD5 للملف مقابل قيمة الناشر",
    "Feedback": "تواصل معنا", "Leave feedback or contact the developer": "أرسل ملاحظاتك أو تواصل مع المطوّر",
    "Open the project page on GitHub": "فتح صفحة المشروع على GitHub", "Open the YouTube channel": "فتح قناة يوتيوب",
    "Copyright and license": "حقوق النشر والترخيص", "All rights reserved.": "جميع الحقوق محفوظة.",
    "This link has not been set yet.\nOpen aerograb/links.py and paste your link there.": "لم يتم ضبط هذا الرابط بعد.\nافتح aerograb/links.py والصق رابطك هناك.",
    "How to export cookies.txt": "كيفية تصدير cookies.txt",
    "Version": "الإصدار",
    # ---- متفرقات
    "Cannot use this folder:": "لا يمكن استخدام هذا المجلد:", "Could not read the file:": "تعذّر قراءة الملف:", "Could not open:": "تعذّر الفتح:",
    "Could not save:": "تعذّر الحفظ:", "Could not start or reach AeroGrab.": "تعذّر تشغيل AeroGrab أو الوصول إليه.",
    "The save folder does not exist yet.": "مجلد الحفظ غير موجود بعد.", "WAV sound": "صوت WAV", "Open the download page?": "هل تريد فتح صفحة التنزيل؟",
    "Trying another format...": "جارٍ تجربة صيغة أخرى...", "Resumable": "قابل للاستكمال", "Not resumable": "غير قابل للاستكمال",
    "Checking the link…": "جارٍ فحص الرابط…", "Calculating…": "جارٍ الحساب…", "Show or hide the active downloads": "إظهار أو إخفاء التنزيلات النشطة",
    "All downloads, including finished ones": "كل التنزيلات بما فيها المنتهية", "Size unknown ": "الحجم غير معروف",
    "Installing the JavaScript engine (one time)...": "جارٍ تثبيت محرك JavaScript (مرة واحدة)...",
    "JavaScript engine (YouTube)": "محرك JavaScript (يوتيوب)", "Install / repair the JavaScript engine": "تثبيت / إصلاح محرك JavaScript",
    "YouTube needs a JavaScript engine (deno or Node.js). Without it videos fail with “Requested format is not available”.": "يوتيوب يحتاج محرك JavaScript (deno أو Node.js). بدونه تفشل الفيديوهات بخطأ «Requested format is not available».",
    "Downloaded once (about 30-40 MB) from the official Deno / Node.js releases and kept inside the program's data folder. 32-bit Windows uses Node.js.": "يُنزَّل مرة واحدة (حوالي 30-40 ميجا) من إصدارات Deno / Node.js الرسمية ويُحفظ في مجلد بيانات البرنامج. ويندوز 32-بت يستخدم Node.js.",
    "OK": "موافق", "Yes": "نعم", "No": "لا",
}

# ---- أنماط للنصوص الديناميكية (f-strings). \1 \2 ... = المجموعات (بتتترجم لو ليها ترجمة)
PATTERNS = [
    (r"^(\d+) (Active|Queued|Completed|Failed)$", "{1} {t2}"),
    (r"^Show only: (.+)$", "عرض فقط: {t1}"),
    (r"^(\W*)(\d+) failed$", "{1}{2} فشل"),
    (r"^(\d+) connections$", "{1} اتصالات"),
    (r"^Audio · (.*)$", "صوت · {1}"),
    (r"^~(.+) \(part\)$", "~{1} (جزء)"),
    (r"^Free space: (.+)$", "المساحة الحرة: {1}"),
    (r"^Usage: (.+)$", "الاستهلاك: {1}"), (r"^Today: (.+)$", "اليوم: {1}"), (r"^This month: (.+)$", "هذا الشهر: {1}"), (r"^Data cycle: (.+)$", "الدورة: {1}"),
    (r"^Used today: (.+)$", "المستهلك اليوم: {1}"), (r"^Used (.+) of (.+?)  \((\d+)%\)$", "المستهلك {1} من {2}  ({3}%)"),
    (r"^Current period: (\S+) → (\S+)   \|   Limit passed: downloads continue \(override\)$", "الفترة الحالية: {1} ← {2}   |   تجاوزت الحد: التنزيل مستمر"),
    (r"^Current period: (\S+) → (\S+)$", "الفترة الحالية: {1} ← {2}"),
    (r"^Total downloaded since the counter started: (.+)$", "إجمالي ما تم تنزيله منذ بدء العدّاد: {1}"),
    (r"^Limit: (.+)$", "الحد: {t1}"),
    (r"^Overall Progress: (.+)$", "التقدم الكلي: {1}"),
    (r"^([\d.]+ ?[KMGT]?B) of ([\d.]+ ?[KMGT]?B)$", "{1} من {2}"),
    (r"^([\d:]+) remaining$", "المتبقي {1}"),
    (r"^ETA ([\d:\-]+)$", "المتبقي {1}"),
    (r"^Paused at (.+)$", "توقف عند {1}"),
    (r"^Resuming from (.+)\.\.\.$", "الاستئناف من {1}..."),
    (r"^Downloading \((\d+) connections\)\.\.\.$", "جارٍ التنزيل ({1} اتصالات)..."),
    (r"^Downloading (video|audio) \((\d+)/(\d+)\)\.\.\.$", "جارٍ تنزيل {t1} ({2}/{3})..."),
    (r"^Retrying \((\d+)/(\d+)\) after: (.+)$", "إعادة المحاولة ({1}/{2}) بعد: {t3}"),
    (r"^(\W*)Failed: (.+) \(Right-click to retry\)$", "{1}فشل: {t2} (كليك يمين لإعادة المحاولة)"),
    (r"^(\W*)Waiting for schedule \((.*)\)$", "{1}في انتظار الجدولة ({2})"),
    (r"^Waiting for schedule \(starts (.*)\)$", "في انتظار الجدولة (يبدأ {1})"),
    (r"^Selected: (\d+) / (\d+)(.*)$", "المحدد: {1} / {2}{3}"),
    (r"^Selected: (\d+)$", "المحدد: {1}"),
    (r"^(\W*)Download selected \((\d+)\)$", "{1}تنزيل المحدد ({2})"),
    (r"^(\d+) shown\s+/\s+(\d+) found$", "{1} معروض  /  {2} موجود"),
    (r"^Add (\d+) videos to the queue\?$", "إضافة {1} فيديو إلى الطابور؟"),
    (r"^Add (\d+) downloads to the queue\?$", "إضافة {1} تنزيل إلى الطابور؟"),
    (r"^Ignored (\d+) invalid lines\.$", "تم تجاهل {1} سطر غير صالح."),
    (r"^Saved (\d+) links\.$", "تم حفظ {1} رابط."),
    (r"^Cannot use this folder:\n(.*)$", "لا يمكن استخدام هذا المجلد:\n{1}"),
    (r"^Could not read the file:\n(.*)$", "تعذّر قراءة الملف:\n{1}"),
    (r"^Could not save:\n(.*)$", "تعذّر الحفظ:\n{1}"),
    (r"^Could not open:\n?(.*)$", "تعذّر الفتح:\n{1}"),
    (r"^Current limit: (.+)$", "الحد الحالي: {t1}"),
    (r"^Current engine: yt-dlp v(.+)$", "المحرك الحالي: yt-dlp v{1}"),
    (r"^Version ([\d.]+)$", "الإصدار {1}"),
    (r"^Program: (.+)\nBrowser extension: (.+)$", "البرنامج: {1}\nإضافة المتصفح: {t2}"),
    (r"^not connected yet$", "غير متصلة بعد"),
    (r"^Saved parts of paused downloads: (.+)$", "الأجزاء المحفوظة من تنزيلات متوقفة: {1}"),
    (r"^(\W*)Using: (.+)$", "{1}المستخدم: {2}"),
    (r"^(\W*)Install failed: (.+)$", "{1}فشل التثبيت: {2}"),
    (r"^Saved: (\d+) file types\. The browser extension picks it up within a minute\.$", "تم الحفظ: {1} نوع ملف. تلتقطها إضافة المتصفح خلال دقيقة."),
    (r"^(\W*)Update downloaded \(v(.+)\), active after restart\.$", "{1}تم تنزيل التحديث (v{2})، يعمل بعد إعادة التشغيل."),
    (r"^(\W*)Already up to date \(v(.+)\)\.$", "{1}المحرك محدّث بالفعل (v{2})."),
    (r"^(\W*)Updated to v(.+), the newest your Python (.+) can run\.$", "{1}تم التحديث إلى v{2}، وهو الأحدث الذي يدعمه Python {3}."),
    (r"^(\W*)v(.+) is the newest your Python (.+) can run\.$", "{1}v{2} هو الأحدث الذي يدعمه Python {3}."),
    (r"^●  Extension connected \(version (.+)\), last contact (.+)\.(.*)$", "●  الإضافة متصلة (الإصدار {1})، آخر اتصال {t2}.{3}"),
    (r"^(\d+) seconds ago$", "منذ {1} ثانية"), (r"^(\d+) minutes ago$", "منذ {1} دقيقة"),
    (r"^  Expected extension version (.+): update the extension files\.$", "  المطلوب إصدار الإضافة {1}: حدّث ملفات الإضافة."),
    (r"^© (\d+) (.+)\.  All rights reserved\.$", "© {1} {2}.  جميع الحقوق محفوظة."),
    (r"^thumbnail unavailable \((.*)\)$", "الصورة المصغرة غير متاحة ({1})"),
    (r"^This checksum looks like (.+), not (.+)\. Choose Auto or (.+)\.$", "تبدو قيمة checksum من نوع {1} وليست {2}. اختر تلقائي أو {3}."),
    (r"^([A-Z0-9-]+) checksum:$", "checksum ({1}):"),
    (r"^Now: (.+)$", "الآن: {t1}"),
    (r"^Version (.+) is available\. You have (.+)\.$", "الإصدار {1} متوفر. لديك {2}."),
    (r"^Downloading the update\.\.\. (\d+)%$", "جارٍ تنزيل التحديث... {1}%"),
]

_ICON_PREFIX = re.compile(r"^([^\w\(\[“\"'<]*)(.*)$", re.S)
_ARROWS = (" ▲", " ▼")


def _lookup(s):
    r = AR.get(s)
    if r is not None:
        return r
    if s.endswith("…"):
        r = AR.get(s[:-1] + "...")
        if r is not None:
            return r.rstrip(".") + "…"
    if s.endswith("..."):
        r = AR.get(s[:-3] + "…")
        if r is not None:
            return r.rstrip("…") + "..."
    return None


def _tr_core(s):
    r = _lookup(s)
    if r is not None:
        return r
    if "   |   " in s:                            # الشريط السفلي: أجزاء مفصولة بـ |
        return "   |   ".join(tr(p) for p in s.split("   |   "))
    for pat, tpl in _COMPILED:
        if tpl is None:
            continue
        m = pat.match(s)
        if m:
            groups = m.groups()
            vals = {}
            for i, g in enumerate(groups, 1):
                g = g or ""
                vals[str(i)] = g
                vals["t%d" % i] = tr(g) if g else g
            try:
                return re.sub(r"\{(t?\d)\}", lambda mm: vals.get(mm.group(1), ""), tpl)
            except Exception:
                return None
    m = re.match(r"^(.+?) \((\d+)\)$", s)       # "Videos (7)" / "Active downloads (3)"
    if m:
        inner = _lookup(m.group(1))
        if inner is not None:
            return f"{inner} ({m.group(2)})"
    if "\n" in s:                                 # رسالة متعددة الأسطر: نترجم كل سطر لوحده
        parts = s.split("\n")
        tp = [tr(p) if p.strip() else p for p in parts]
        if tp != parts:
            return "\n".join(tp)
    return None


class Raw(str):
    """نص مش بيتترجم أبداً (أسماء الملفات والعناوين اللي جاية من الإنترنت)."""


def tr(s):
    """ترجمة نص للغة الحالية (لو إنجليزي أو مفيش ترجمة بيرجع زي ما هو)."""
    if _lang["v"] != "ar" or not isinstance(s, str) or isinstance(s, Raw) or not s.strip():
        return s
    hit = _cache.get(s)
    if hit is not None:
        return hit
    out = None
    base, arrow = s, ""
    for a in _ARROWS:
        if s.endswith(a):
            base, arrow = s[: -len(a)], a
            break
    out = _tr_core(base)
    if out is None:
        m = _ICON_PREFIX.match(base)
        pre, core = (m.group(1), m.group(2)) if m else ("", base)
        if pre and core:
            r = _tr_core(core)
            if r is not None:
                out = pre + r
    if out is None:
        if os.environ.get("AEROGRAB_I18N_DEBUG") and re.search(r"[A-Za-z]{3,}", s) and len(s) < 300:
            _missing.add(s)
            _dump_missing()
        out = s
    else:
        out += arrow
    if len(_cache) > 4000:
        _cache.clear()
    _cache[s] = out
    return out


def _dump_missing():
    try:
        from aerograb.config import APP_DATA_DIR
        with open(os.path.join(APP_DATA_DIR, "missing_i18n.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(sorted(_missing)))
    except Exception:
        pass


_COMPILED = [(re.compile(p, re.S), t) for p, t in PATTERNS]

# أسماء الأنواع في القوائم المنسدلة تتحول للعربي بالقاموس (AR["Active"] إلخ.) ومفيش منطق بيعتمد على النص المعروض.


# ----------------------------------------------------------------------------- الربط مع tkinter / customtkinter
_installed = {"v": False}


def _tr_kw(kw, keys=("text",)):
    for k in keys:
        v = kw.get(k)
        if isinstance(v, str):
            kw[k] = tr(v)


def _wrap_class(cls, keys=("text",)):
    orig_init = cls.__init__

    def init(self, *a, **kw):
        _tr_kw(kw, keys)
        orig_init(self, *a, **kw)
    cls.__init__ = init
    orig_cfg = cls.configure

    def cfg(self, cnf=None, **kw):
        _tr_kw(kw, keys)
        if isinstance(cnf, dict):
            cnf = dict(cnf)
            _tr_kw(cnf, keys)
        return orig_cfg(self, cnf, **kw)
    cls.configure = cfg
    cls.config = cfg


def install_hooks():
    """بتتنادى مرة واحدة لو اللغة مش إنجليزي. آمنة: أي خطأ بيتتجاهل والنص بيفضل إنجليزي."""
    if _installed["v"] or _lang["v"] == "en":
        return
    _installed["v"] = True
    import tkinter as tk
    from tkinter import ttk, messagebox
    for cls in (tk.Label, tk.Button, tk.Checkbutton, tk.Radiobutton, tk.Menubutton):
        try:
            _wrap_class(cls)
        except Exception:
            pass
    try:
        _wrap_class(tk.LabelFrame)
    except Exception:
        pass
    # قوائم منسدلة (CTkOptionMenu / DropdownMenu)
    for name in ("add_command", "add_radiobutton", "add_checkbutton"):
        orig = getattr(tk.Menu, name)

        def make(o):
            def f(self, cnf={}, **kw):
                _tr_kw(kw, ("label",))
                return o(self, cnf, **kw)
            return f
        setattr(tk.Menu, name, make(orig))
    # كانفس (كروت التنزيل + الشريط الكلي)
    orig_ct = tk.Canvas.create_text

    def create_text(self, *a, **kw):
        _tr_kw(kw)
        return orig_ct(self, *a, **kw)
    tk.Canvas.create_text = create_text
    # عناوين الجداول
    orig_head = ttk.Treeview.heading

    def heading(self, column, option=None, **kw):
        _tr_kw(kw)
        return orig_head(self, column, option, **kw)
    ttk.Treeview.heading = heading
    # عنوان النوافذ
    for name in ("wm_title", "title"):
        orig_t = getattr(tk.Wm, name)

        def make_t(o):
            def f(self, string=None):
                return o(self, tr(string) if isinstance(string, str) else string)
            return f
        setattr(tk.Wm, name, make_t(orig_t))
    # رسائل التأكيد
    for name in ("showinfo", "showwarning", "showerror", "askyesno", "askokcancel", "askyesnocancel",
                 "askretrycancel", "askquestion"):
        orig_m = getattr(messagebox, name, None)
        if orig_m is None:
            continue

        def make_m(o):
            def f(title=None, message=None, **kw):
                return o(tr(title) if isinstance(title, str) else title,
                         tr(message) if isinstance(message, str) else message, **kw)
            return f
        setattr(messagebox, name, make_m(orig_m))
    # placeholder في خانات الإدخال (CTkEntry.configure مالوش cnf فبنلفّه لوحده)
    try:
        import customtkinter as ctk
        orig_e_init = ctk.CTkEntry.__init__

        def e_init(self, *a, **kw):
            _tr_kw(kw, ("placeholder_text",))
            orig_e_init(self, *a, **kw)
        ctk.CTkEntry.__init__ = e_init
        orig_e_cfg = ctk.CTkEntry.configure

        def e_cfg(self, *a, **kw):
            _tr_kw(kw, ("placeholder_text",))
            return orig_e_cfg(self, *a, **kw)
        ctk.CTkEntry.configure = e_cfg
    except Exception:
        pass
