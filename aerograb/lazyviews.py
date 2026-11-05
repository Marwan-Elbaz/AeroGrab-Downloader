# -*- coding: utf-8 -*-
"""وسطاء كسولين لدوال الواجهة: الوحدات اللي مش واجهة (السيرفر/المحرّك) بتنادي الدوال دي
من غير ما تحمّل الواجهة وقت الإقلاع. tkinter/customtkinter بتتحمّل أول مرة الدالة تتنادى فعلاً."""


def apply_layout(*args, **kwargs):
    from aerograb.views.mainwin import apply_layout as _f
    return _f(*args, **kwargs)


def dispatch_add_item(*args, **kwargs):
    from aerograb.views.popups import dispatch_add_item as _f
    return _f(*args, **kwargs)


def filter_tasks(*args, **kwargs):
    from aerograb.views.mainwin import filter_tasks as _f
    return _f(*args, **kwargs)


def on_task_completed(*args, **kwargs):
    from aerograb.views.mainwin import on_task_completed as _f
    return _f(*args, **kwargs)


def open_path(*args, **kwargs):
    from aerograb.views.winutil import open_path as _f
    return _f(*args, **kwargs)


def reveal_in_folder(*args, **kwargs):
    from aerograb.views.winutil import reveal_in_folder as _f
    return _f(*args, **kwargs)


def show_link_grabber(*args, **kwargs):
    from aerograb.views.grabber import show_link_grabber as _f
    return _f(*args, **kwargs)


def wake_up_window(*args, **kwargs):
    from aerograb.views.winutil import wake_up_window as _f
    return _f(*args, **kwargs)
