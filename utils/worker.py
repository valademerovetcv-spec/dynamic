"""
Модуль для фоновых вычислений с использованием threading.
Обеспечивает неблокирующую работу UI при выполнении тяжелых операций.
"""
import threading
from typing import Callable, Optional, Any
import tkinter as tk
from tkinter import ttk


class WorkerThread(threading.Thread):
    """Поток для выполнения тяжелых вычислений с обновлением UI."""
    
    def __init__(self, target: Callable, args: tuple = (), kwargs: dict = None,
                 on_start: Optional[Callable] = None,
                 on_complete: Optional[Callable] = None,
                 on_error: Optional[Callable] = None):
        super().__init__()
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}
        self.on_start = on_start
        self.on_complete = on_complete
        self.on_error = on_error
        self.result = None
        self.error = None
    
    def run(self):
        try:
            if self.on_start:
                self.on_start()
            self.result = self.target(*self.args, **self.kwargs)
            if self.on_complete:
                # Обновление UI должно происходить в главном потоке
                if hasattr(self.on_complete, '__self__') and isinstance(self.on_complete.__self__, tk.Widget):
                    widget = self.on_complete.__self__
                    widget.after(0, lambda: self.on_complete(self.result))
                else:
                    self.on_complete(self.result)
        except Exception as e:
            self.error = e
            if self.on_error:
                if hasattr(self.on_error, '__self__') and isinstance(self.on_error.__self__, tk.Widget):
                    widget = self.on_error.__self__
                    widget.after(0, lambda: self.on_error(e))
                else:
                    self.on_error(e)


class LoadingOverlay:
    """Оверлей с индикатором загрузки для блокировки UI во время вычислений."""
    
    def __init__(self, parent: tk.Widget, text: str = "Выполняется расчёт..."):
        self.parent = parent
        self.text = text
        self.overlay = None
        self.label = None
        self.progress = None
        
    def show(self):
        """Показать оверлей загрузки."""
        if self.overlay is not None:
            return
            
        self.overlay = tk.Toplevel(self.parent)
        self.overlay.title("Расчёт")
        self.overlay.transient(self.parent)
        self.overlay.grab_set()
        
        # Позиционирование по центру родителя
        x = self.parent.winfo_rootx() + self.parent.winfo_width() // 2 - 150
        y = self.parent.winfo_rooty() + self.parent.winfo_height() // 2 - 50
        self.overlay.geometry(f"300x100+{x}+{y}")
        self.overlay.resizable(False, False)
        self.overlay.configure(bg="#f0f2f5")
        
        # Запрет закрытия окна
        self.overlay.protocol("WM_DELETE_WINDOW", lambda: None)
        
        frame = ttk.Frame(self.overlay, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        self.label = ttk.Label(frame, text=self.text, font=("Segoe UI", 11))
        self.label.pack(pady=(0, 15))
        
        self.progress = ttk.Progressbar(frame, mode='indeterminate', length=250)
        self.progress.pack(pady=5)
        self.progress.start(10)
        
        # Принудительная отрисовка
        self.overlay.update_idletasks()
        
    def hide(self):
        """Скрыть оверлей загрузки."""
        if self.overlay is not None:
            if self.progress:
                self.progress.stop()
            self.overlay.destroy()
            self.overlay = None
            self.label = None
            self.progress = None


def run_async(func: Callable, args: tuple = (), kwargs: dict = None,
              parent: Optional[tk.Widget] = None,
              loading_text: str = "Выполняется операция...",
              on_complete: Optional[Callable] = None,
              on_error: Optional[Callable] = None):
    """
    Запустить функцию в фоновом потоке с индикатором загрузки.
    
    Args:
        func: Функция для выполнения
        args: Аргументы функции
        kwargs: Именованные аргументы функции
        parent: Родительский виджет для оверлея
        loading_text: Текст индикатора загрузки
        on_complete: Callback по завершении (вызывается в главном потоке)
        on_error: Callback при ошибке (вызывается в главном потоке)
    """
    if kwargs is None:
        kwargs = {}
    
    overlay = LoadingOverlay(parent, loading_text) if parent else None
    
    def wrapped_complete(result):
        if overlay:
            overlay.hide()
        if on_complete:
            on_complete(result)
    
    def wrapped_error(error):
        if overlay:
            overlay.hide()
        if on_error:
            on_error(error)
    
    def task_wrapper():
        return func(*args, **kwargs)
    
    thread = WorkerThread(
        target=task_wrapper,
        on_start=lambda: overlay.show() if overlay else None,
        on_complete=wrapped_complete,
        on_error=wrapped_error
    )
    thread.daemon = True
    thread.start()
    return thread
