"""Панель инструментов и меню приложения."""
import tkinter as tk
from tkinter import ttk, filedialog
from pathlib import Path


class ToolbarBuilder:
    """Строитель панели инструментов."""
    
    def __init__(self, parent, app_instance):
        self.parent = parent
        self.app = app_instance
    
    def build_menu(self):
        """Создает главное меню."""
        from ui.styles import BG
        
        menubar = tk.Menu(self.app.root, font=("Segoe UI", 10))
        file_menu = tk.Menu(menubar, tearoff=0, font=("Segoe UI", 10))
        file_menu.add_command(label="Открыть Excel...", command=self.app.load_file, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Загрузить Динамика (CSV)...", command=self.app.load_dynamics_csv)
        file_menu.add_command(label="Загрузить Динамика (XLSX)...", command=self.app.load_dynamics_xlsx)
        file_menu.add_command(label="Загрузить Тарировка (CSV)...", command=self.app.load_calibration_csv)
        file_menu.add_command(label="Загрузить Тарировка (XLSX)...", command=self.app.load_calibration_xlsx)
        file_menu.add_separator()
        file_menu.add_command(label="Загрузить Температуры (CSV)...", command=self.app.load_temperature)
        file_menu.add_separator()
        file_menu.add_command(label="Сохранить результат...", command=self.app.save_file, accelerator="Ctrl+S")
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self.app.root.quit)
        menubar.add_cascade(label="Файл", menu=file_menu)
        self.app.root.config(menu=menubar)
        self.app.root.bind("<Control-o>", lambda e: self.app.load_file())
        self.app.root.bind("<Control-s>", lambda e: self.app.save_file())
    
    def build_toolbar(self, parent):
        """Создает панель инструментов."""
        tb = ttk.Frame(parent, style="Toolbar.TFrame")
        tb.pack(fill=tk.X, padx=0, pady=0)

        ttk.Label(tb, text="  Динамика", style="Header.TLabel").pack(side=tk.LEFT, padx=(12, 20))

        ttk.Button(tb, text="Открыть Excel", style="Toolbar.TButton",
                   command=self.app.load_file).pack(side=tk.LEFT, padx=3, pady=6)
        ttk.Button(tb, text="Динамика (CSV/XLSX)", style="ToolbarCsv.TButton",
                   command=self.app.load_dynamics_csv).pack(side=tk.LEFT, padx=3, pady=6)
        ttk.Button(tb, text="Тарировка (CSV/XLSX)", style="ToolbarCsv.TButton",
                   command=self.app.load_calibration_csv).pack(side=tk.LEFT, padx=3, pady=6)
        ttk.Button(tb, text="Сохранить", style="Toolbar.TButton",
                   command=self.app.save_file).pack(side=tk.LEFT, padx=3, pady=6)

        ttk.Separator(tb, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=6)

        ttk.Button(tb, text="Температуры (CSV/XLSX)", style="ToolbarCsv.TButton",
                   command=self.app.load_temperature).pack(side=tk.LEFT, padx=3, pady=6)

        self.app.file_label = ttk.Label(tb, text="Файл не загружен", style="Header.TLabel")
        self.app.file_label.pack(side=tk.RIGHT, padx=15)
        return tb
