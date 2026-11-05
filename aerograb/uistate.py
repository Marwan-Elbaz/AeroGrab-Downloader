# -*- coding: utf-8 -*-
"""حالة الواجهة الحيّة: العناصر اللي بتتعمل وقت تشغيل main_gui وبتتشارك بين الوحدات.
بدل متغيرات global متبعثرة بنستخدم كائن واحد: gui.root, gui.tree, gui.cards ..."""
from types import SimpleNamespace

gui = SimpleNamespace(
    root=None, tree=None, quality_var=None, download_path_var=None, search_var=None,
    empty_frame=None, empty_title=None, empty_sub=None, speed_var=None, speed_menu=None,
    after_var=None, after_menu=None, cards=None, table_frame=None, strip_title=None,
    overall_cv=None, overall_font=None, stat_lbls=None, free_lbl=None,
    hist_title=None, lang_btn=None, share_btn=None,
    current_filter="All",          # التصنيف المختار في التابات
    gui_running=False,             # الواجهة اشتغلت؟ (السيرفر بيقرأها)
    tk=None, ttk=None, messagebox=None, filedialog=None, ctk=None,   # نسخ للوحدات اللي مش واجهة
)
