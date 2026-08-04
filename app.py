import sys
import os
from datetime import datetime
import numpy as np
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd
import openpyxl
import windnd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib import rcParams
import matplotlib.dates as mdates
from pathlib import Path
import threading

from calc import DataLoader
from core.calculator import Calculator
from core.deformation_analyzer import DeformationAnalyzer, SPEED_KMH_DEFAULT, THRESHOLD_SIGMA_DEFAULT

BG = "#f0f2f5"
FG = "#1a1a2e"
ACCENT = "#2563eb"
ACCENT_HOVER = "#1d4ed8"
PANEL_BG = "#ffffff"
HEADER_BG = "#e8eaf0"
GRID_COLOR = "#d1d5db"
CHART_BG = "#fafbfc"

CHANNEL_COLORS = ["#4CAF50", "#2196F3", "#FF9800", "#E91E63", "#9C27B0", "#00BCD4", "#FF5722"]


def _style_app():
    style = ttk.Style()
    style.theme_use("clam")

    style.configure(".", background=BG, foreground=FG, font=("Segoe UI", 10))
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=FG, font=("Segoe UI", 10))
    style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=(12, 6))
    style.map("TButton",
              background=[("active", ACCENT_HOVER), ("!active", ACCENT)],
              foreground=[("active", "#ffffff"), ("!active", "#ffffff")])

    style.configure("Toolbar.TFrame", background="#1a1a2e")
    style.configure("Toolbar.TButton", background="#2563eb", foreground="#ffffff",
                     font=("Segoe UI", 10, "bold"), padding=(14, 7))
    style.map("Toolbar.TButton",
              background=[("active", "#3b82f6"), ("!active", "#2563eb")],
              foreground=[("active", "#ffffff"), ("!active", "#ffffff")])

    style.configure("ToolbarCsv.TButton", background="#16a34a", foreground="#ffffff",
                     font=("Segoe UI", 10, "bold"), padding=(14, 7))
    style.map("ToolbarCsv.TButton",
              background=[("active", "#22c55e"), ("!active", "#16a34a")],
              foreground=[("active", "#ffffff"), ("!active", "#ffffff")])

    style.configure("Header.TLabel", background="#1a1a2e", foreground="#ffffff",
                     font=("Segoe UI", 11, "bold"))
    style.configure("Status.TLabel", background="#e2e8f0", foreground="#475569",
                     font=("Segoe UI", 9), padding=(10, 4))
    style.configure("Info.TLabel", background=BG, foreground="#64748b",
                     font=("Segoe UI", 9))

    style.configure("TLabelframe", background=PANEL_BG, foreground=FG,
                     font=("Segoe UI", 10, "bold"), relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=PANEL_BG, foreground=ACCENT,
                     font=("Segoe UI", 10, "bold"))

    style.configure("Treeview", background=PANEL_BG, foreground=FG,
                     fieldbackground=PANEL_BG, font=("Consolas", 10), rowheight=24)
    style.configure("Treeview.Heading", background=HEADER_BG, foreground=FG,
                     font=("Segoe UI", 10, "bold"), relief="flat")
    style.map("Treeview", background=[("selected", ACCENT)],
              foreground=[("selected", "#ffffff")])
    style.map("Treeview.Heading", background=[("active", "#d1d5db")])

    style.configure("TPanedwindow", background=BG)
    style.configure("Sash", sashthickness=6, background=GRID_COLOR)

    rcParams["font.family"] = "Segoe UI"
    rcParams["axes.facecolor"] = CHART_BG
    rcParams["figure.facecolor"] = CHART_BG
    rcParams["axes.edgecolor"] = GRID_COLOR
    rcParams["axes.labelcolor"] = FG
    rcParams["xtick.color"] = "#64748b"
    rcParams["ytick.color"] = "#64748b"


class DinamikaApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Обработка данных динамики")
        self.root.geometry("1500x850")
        self.root.minsize(1000, 600)
        self.root.state("zoomed")
        self.root.configure(bg=BG)

        self.loader = DataLoader()
        self.calculator = Calculator(self.loader)
        self.deformation_analyzer = None
        self._file_path = None
        self._channel_visibility = {}
        self._dynamics_file_path = None
        self._calibration_file_path = None
        self._selected_source_layer = None
        self._calib_sel_widgets = {}  # {layer: {sensor_var, left_var, right_var, ...}}
        self._calib_range_selection_active = False
        self._calib_range_selection_start = None
        self._calib_range_selection_rect = None
        self._calib_range_press_id = None
        self._calib_range_release_id = None
        self._calib_range_target = None
        self._calib_range_highlights = {}  # {layer: (left, right)}
        self._peak_range = None
        self._calculating = False
        self._deformation_zones = []
        self._current_deformation_zone = 0

        _style_app()
        self._build_ui()

    def _build_ui(self):
        self._build_menu()

        outer = ttk.Frame(self.root)
        outer.pack(fill=tk.BOTH, expand=True)

        self._build_toolbar(outer)
        self._build_content(outer)
        self._build_statusbar()

        self.root.protocol("WM_DELETE_WINDOW", lambda: self.root.destroy())

    def _build_menu(self):
        menubar = tk.Menu(self.root, font=("Segoe UI", 10))
        file_menu = tk.Menu(menubar, tearoff=0, font=("Segoe UI", 10))
        file_menu.add_command(label="Открыть Excel...", command=self.load_file, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Загрузить Динамика (CSV)...", command=self.load_dynamics_csv)
        file_menu.add_command(label="Загрузить Динамика (XLSX)...", command=self.load_dynamics_xlsx)
        file_menu.add_command(label="Загрузить Тарировка (CSV)...", command=self.load_calibration_csv)
        file_menu.add_command(label="Загрузить Тарировка (XLSX)...", command=self.load_calibration_xlsx)
        file_menu.add_separator()
        file_menu.add_command(label="Загрузить Температуры (CSV)...", command=self.load_temperature)
        file_menu.add_separator()
        file_menu.add_command(label="Сохранить результат...", command=self.save_file, accelerator="Ctrl+S")
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self.root.quit)
        menubar.add_cascade(label="Файл", menu=file_menu)
        self.root.config(menu=menubar)
        self.root.bind("<Control-o>", lambda e: self.load_file())
        self.root.bind("<Control-s>", lambda e: self.save_file())

    def _build_toolbar(self, parent):
        tb = ttk.Frame(parent, style="Toolbar.TFrame")
        tb.pack(fill=tk.X, padx=0, pady=0)

        ttk.Label(tb, text="  Динамика", style="Header.TLabel").pack(side=tk.LEFT, padx=(12, 20))

        ttk.Button(tb, text="Открыть Excel", style="Toolbar.TButton",
                   command=self.load_file).pack(side=tk.LEFT, padx=3, pady=6)
        ttk.Button(tb, text="Динамика (CSV/XLSX)", style="ToolbarCsv.TButton",
                   command=self.load_dynamics_csv).pack(side=tk.LEFT, padx=3, pady=6)
        ttk.Button(tb, text="Тарировка (CSV/XLSX)", style="ToolbarCsv.TButton",
                   command=self.load_calibration_csv).pack(side=tk.LEFT, padx=3, pady=6)
        ttk.Button(tb, text="Сохранить", style="Toolbar.TButton",
                   command=self.save_file).pack(side=tk.LEFT, padx=3, pady=6)

        ttk.Separator(tb, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=6)

        ttk.Button(tb, text="Температуры (CSV/XLSX)", style="ToolbarCsv.TButton",
                   command=self.load_temperature).pack(side=tk.LEFT, padx=3, pady=6)

        ttk.Separator(tb, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=6)

        self.analyze_deform_btn = ttk.Button(tb, text="🔍 Анализ деформаций", style="Toolbar.TButton",
                                              command=self._analyze_deformations)
        self.analyze_deform_btn.pack(side=tk.LEFT, padx=3, pady=6)

        self.file_label = ttk.Label(tb, text="Файл не загружен", style="Header.TLabel")
        self.file_label.pack(side=tk.RIGHT, padx=15)

    def _build_content(self, parent):
        self.global_notebook = ttk.Notebook(parent)
        self.global_notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 0))

        self.tab_deform = ttk.Frame(self.global_notebook)
        self.global_notebook.add(self.tab_deform, text="  Деформации  ")

        self.tab_temp = ttk.Frame(self.global_notebook)
        self.global_notebook.add(self.tab_temp, text="  Температуры  ")

        # Новая вкладка для анализа деформаций
        self.tab_analysis = ttk.Frame(self.global_notebook)
        self.global_notebook.add(self.tab_analysis, text="  Анализ деформаций  ")

        self._build_deform_tab(self.tab_deform)
        self._build_temp_tab(self.tab_temp)
        
        # Добавляем панель анализа деформаций в отдельную вкладку
        self._build_deformation_panel(self.tab_analysis)

    def _build_deform_tab(self, parent):
        main_paned = ttk.PanedWindow(parent, orient=tk.VERTICAL)
        main_paned.pack(fill=tk.BOTH, expand=True)

        top_paned = ttk.PanedWindow(main_paned, orient=tk.HORIZONTAL)
        main_paned.add(top_paned, weight=1)

        left_frame = ttk.LabelFrame(top_paned, text=" Динамика — Исходные данные (Drop CSV/XLSX)")
        top_paned.add(left_frame, weight=3)
        src_btn_frame = ttk.Frame(left_frame)
        src_btn_frame.pack(fill=tk.X, padx=4, pady=(4, 0))
        ttk.Button(src_btn_frame, text="Сброс", style="ToolbarCsv.TButton",
                   command=self._reset_dynamics).pack(side=tk.RIGHT, padx=2)
        self.source_notebook = ttk.Notebook(left_frame)
        self.source_notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._source_tabs = {}
        self.source_notebook.bind("<<NotebookTabChanged>>", self._on_source_tab_changed)

        right_frame = ttk.LabelFrame(top_paned, text=" Тарировка — Калибровочная кривая (Drop CSV/XLSX)")
        top_paned.add(right_frame, weight=2)
        cal_btn_frame = ttk.Frame(right_frame)
        cal_btn_frame.pack(fill=tk.X, padx=4, pady=(4, 0))
        ttk.Button(cal_btn_frame, text="Сброс", style="ToolbarCsv.TButton",
                   command=self._reset_calibration).pack(side=tk.RIGHT, padx=2)
        self.calib_notebook = ttk.Notebook(right_frame)
        self.calib_notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._calib_tabs = {}

        # Drag-and-drop — hook root window, determine zone by mouse position
        windnd.hook_dropfiles(self.root, func=self._on_drop_root)

        raw_chart_frame = ttk.LabelFrame(top_paned, text=" Данные динамики ")
        top_paned.add(raw_chart_frame, weight=3)

        # Pack toolbar and toggle frames first (at bottom)
        self.channel_toggle_frame = ttk.Frame(raw_chart_frame)
        self.channel_toggle_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=(0, 2))

        raw_tb = ttk.Frame(raw_chart_frame)
        raw_tb.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=(0, 4))
        self.raw_toolbar_frame = raw_tb

        # Create notebook and tabs
        self.raw_notebook = ttk.Notebook(raw_chart_frame)

        self.tab_time = ttk.Frame(self.raw_notebook)
        self.raw_notebook.add(self.tab_time, text="  Динамика  ")

        self.tab_disp = ttk.Frame(self.raw_notebook)
        self.raw_notebook.add(self.tab_disp, text="  Тарировка  ")

        self.tab_magnet = ttk.Frame(self.raw_notebook)
        self.raw_notebook.add(self.tab_magnet, text="  Положение магнита  ")

        self.raw_fig = Figure(figsize=(5, 3), dpi=100)
        self.raw_ax = self.raw_fig.add_subplot(111)
        self.raw_canvas = FigureCanvasTkAgg(self.raw_fig, master=self.tab_time)
        self.raw_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.disp_fig = Figure(figsize=(5, 3), dpi=100)
        self.disp_ax = self.disp_fig.add_subplot(111)
        self.disp_canvas = FigureCanvasTkAgg(self.disp_fig, master=self.tab_disp)
        self.disp_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.magnet_fig = Figure(figsize=(5, 3), dpi=100)
        self.magnet_ax = self.magnet_fig.add_subplot(111)
        self.magnet_canvas = FigureCanvasTkAgg(self.magnet_fig, master=self.tab_magnet)
        self.magnet_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Pack notebook last (fills remaining space above toolbar/toggles)
        self.raw_notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.raw_toolbar = NavigationToolbar2Tk(self.raw_canvas, raw_tb)
        self.raw_toolbar.update()
        self.disp_toolbar = NavigationToolbar2Tk(self.disp_canvas, raw_tb)
        self.disp_toolbar.pack_forget()
        self.magnet_toolbar = NavigationToolbar2Tk(self.magnet_canvas, raw_tb)
        self.magnet_toolbar.pack_forget()

        self.raw_notebook.bind("<<NotebookTabChanged>>", self._on_raw_tab_changed)

        calib_sel_frame = ttk.LabelFrame(top_paned, text=" Выбор тарировки ")
        top_paned.add(calib_sel_frame, weight=2)

        calib_sel_btn_frame = ttk.Frame(calib_sel_frame)
        calib_sel_btn_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=(0, 4))
        ttk.Button(calib_sel_btn_frame, text="Применить", style="ToolbarCsv.TButton",
                   command=self._apply_calib_selection).pack(side=tk.LEFT, padx=2)
        ttk.Button(calib_sel_btn_frame, text="Сбросить вручную", style="ToolbarCsv.TButton",
                   command=self._reset_calib_manual).pack(side=tk.LEFT, padx=2)
        self.calib_sel_info_label = ttk.Label(calib_sel_btn_frame, text="", style="Info.TLabel")
        self.calib_sel_info_label.pack(side=tk.LEFT, padx=8)

        calib_sel_container = ttk.Frame(calib_sel_frame)
        calib_sel_container.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.calib_sel_canvas = tk.Canvas(calib_sel_container, bg=PANEL_BG, highlightthickness=0)
        calib_sel_vsb = ttk.Scrollbar(calib_sel_container, orient=tk.VERTICAL,
                                       command=self.calib_sel_canvas.yview)
        self.calib_sel_inner = ttk.Frame(self.calib_sel_canvas)
        self.calib_sel_inner.bind(
            "<Configure>",
            lambda e: self.calib_sel_canvas.configure(scrollregion=self.calib_sel_canvas.bbox("all"))
        )
        self.calib_sel_canvas.create_window((0, 0), window=self.calib_sel_inner, anchor="nw")
        self.calib_sel_canvas.configure(yscrollcommand=calib_sel_vsb.set)
        self.calib_sel_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        calib_sel_vsb.pack(side=tk.RIGHT, fill=tk.Y)

        bot_paned = ttk.PanedWindow(main_paned, orient=tk.HORIZONTAL)
        main_paned.add(bot_paned, weight=3)

        res = ttk.LabelFrame(bot_paned, text=" Результат расчёта ")
        bot_paned.add(res, weight=2)
        self.tree_result = self._make_tree(res)

        chart = ttk.LabelFrame(bot_paned, text=" График: Перемещение от времени ")
        bot_paned.add(chart, weight=3)

        self.result_fig = Figure(figsize=(7, 4), dpi=100)
        self.result_ax = self.result_fig.add_subplot(111)

        # Pack toggle frame and toolbar first (at bottom)
        self.result_toggle_frame = ttk.Frame(chart)
        self.result_toggle_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=(0, 2))

        tb_frame = ttk.Frame(chart)
        tb_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=(0, 4))

        # Create and pack canvas last (fills remaining space)
        self.result_canvas = FigureCanvasTkAgg(self.result_fig, master=chart)
        self.result_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.result_canvas.mpl_connect('motion_notify_event', self._on_result_motion)
        self.result_canvas.mpl_connect('axes_leave_event', self._on_result_leave)

        self.result_toolbar = NavigationToolbar2Tk(self.result_canvas, tb_frame)
        self.result_toolbar.update()

    def _build_deformation_panel(self, parent):
        """Создание панели анализа деформаций в отдельном окне."""
        # Основной фрейм с прокруткой
        self.deform_main_frame = ttk.LabelFrame(parent, text=" Анализ деформаций ")
        self.deform_main_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 0))
        
        # Контейнер для скролла
        deform_container = ttk.Frame(self.deform_main_frame)
        deform_container.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        
        self.deform_canvas = tk.Canvas(deform_container, bg=PANEL_BG, highlightthickness=0)
        deform_vsb = ttk.Scrollbar(deform_container, orient=tk.VERTICAL, command=self.deform_canvas.yview)
        self.deform_inner = ttk.Frame(self.deform_canvas)
        
        self.deform_inner.bind(
            "<Configure>",
            lambda e: self.deform_canvas.configure(scrollregion=self.deform_canvas.bbox("all"))
        )
        
        self.deform_canvas.create_window((0, 0), window=self.deform_inner, anchor="nw")
        self.deform_canvas.configure(yscrollcommand=deform_vsb.set)
        
        self.deform_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        deform_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Панель управления анализом деформаций (скрыта, кнопка вынесена в toolbar)
        deform_ctrl_frame = ttk.Frame(self.deform_inner)
        deform_ctrl_frame.pack(side=tk.TOP, fill=tk.X, padx=4, pady=(4, 0))
        
        ttk.Label(deform_ctrl_frame, text="Скорость, км/ч:").pack(side=tk.LEFT, padx=(15, 5))
        self.deform_speed_var = tk.StringVar(value=str(SPEED_KMH_DEFAULT))
        self.deform_speed_entry = ttk.Entry(deform_ctrl_frame, textvariable=self.deform_speed_var, width=8)
        self.deform_speed_entry.pack(side=tk.LEFT)
        
        ttk.Label(deform_ctrl_frame, text="Порог, σ:").pack(side=tk.LEFT, padx=(15, 5))
        self.deform_threshold_var = tk.StringVar(value=str(THRESHOLD_SIGMA_DEFAULT))
        self.deform_threshold_entry = ttk.Entry(deform_ctrl_frame, textvariable=self.deform_threshold_var, width=8)
        self.deform_threshold_entry.pack(side=tk.LEFT)
        
        self.deform_status_label = ttk.Label(deform_ctrl_frame, text="", style="Info.TLabel")
        self.deform_status_label.pack(side=tk.LEFT, padx=15)
        
        # Notebook для вкладок участков деформаций
        self.deformation_notebook = ttk.Notebook(self.deform_inner)
        self.deformation_notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._deformation_tabs = {}
        self.deformation_notebook.bind("<<NotebookTabChanged>>", self._on_deformation_tab_changed)
        
        # Инициализация пустой вкладки
        default_frame = ttk.Frame(self.deformation_notebook)
        self.deformation_notebook.add(default_frame, text="  Нет данных  ")
        lbl = ttk.Label(default_frame, text="Нажмите кнопку 'Анализировать деформации' для начала анализа",
                       background=PANEL_BG, foreground="#94a3b8",
                       font=("Segoe UI", 10, "italic"))
        lbl.pack(expand=True, pady=20)
        self._deformation_tabs["Нет данных"] = default_frame

    def _build_temp_tab(self, parent):
        self._temp_file_path = None
        self._temp_channel_vars = {}

        main_paned = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.LabelFrame(main_paned, text=" Температуры — Исходные данные ")
        main_paned.add(left_frame, weight=2)
        self.temp_tree_frame = ttk.Frame(left_frame)
        self.temp_tree_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.temp_tree = self._make_tree(self.temp_tree_frame)

        right_paned = ttk.PanedWindow(main_paned, orient=tk.VERTICAL)
        main_paned.add(right_paned, weight=3)

        chart_frame = ttk.LabelFrame(right_paned, text=" Температура ")
        right_paned.add(chart_frame, weight=3)

        # Pack toggle frame and toolbar first (at bottom)
        self.temp_toggle_frame = ttk.Frame(chart_frame)
        self.temp_toggle_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=(0, 2))

        temp_tb = ttk.Frame(chart_frame)
        temp_tb.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=(0, 4))

        # Create and pack canvas last (fills remaining space)
        self.temp_fig = Figure(figsize=(7, 4), dpi=100)
        self.temp_ax = self.temp_fig.add_subplot(111)
        self.temp_canvas = FigureCanvasTkAgg(self.temp_fig, master=chart_frame)
        self.temp_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.temp_canvas.mpl_connect('motion_notify_event', self._on_temp_motion)
        self.temp_canvas.mpl_connect('axes_leave_event', self._on_temp_leave)

        self.temp_toolbar = NavigationToolbar2Tk(self.temp_canvas, temp_tb)
        self.temp_toolbar.update()

        stats_frame = ttk.LabelFrame(right_paned, text=" Статистика ")
        right_paned.add(stats_frame, weight=1)

        self.temp_stats_text = tk.Text(stats_frame, wrap=tk.WORD, font=("Consolas", 10),
                                        bg=PANEL_BG, fg=FG, borderwidth=0, highlightthickness=0)
        self.temp_stats_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    def _on_temp_motion(self, event):
        tk_canvas = self.temp_canvas.get_tk_widget()
        tk_canvas.delete("crosshair")
        if event.inaxes != self.temp_ax or event.xdata is None:
            return
        x, y = event.xdata, event.ydata
        px = event.x
        py = self.temp_fig.bbox.height - event.y
        w = tk_canvas.winfo_width()
        h = tk_canvas.winfo_height()

        # Vertical line
        tk_canvas.create_line(px, 0, px, h, fill='#aaaaaa', dash=(4, 4), tags="crosshair")

        # X value label at top
        dt = mdates.num2date(x)
        text = dt.strftime("%d.%m.%Y %H:%M")
        text_w = len(text) * 5 + 10
        tk_canvas.create_rectangle(px - text_w // 2, 1, px + text_w // 2, 17,
                                    fill='#ffffcc', outline='#aaaaaa', tags="crosshair")
        tk_canvas.create_text(px, 9, text=text, fill='#333333',
                               font=("Segoe UI", 8), tags="crosshair")

        # Find and show values at intersections with each visible channel
        if self.loader.temp_channels and self.loader.temp_time is not None:
            time_vals = self.loader.temp_time
            x_num = mdates.date2num(x) if isinstance(x, (datetime, pd.Timestamp)) else x
            time_num = mdates.date2num(time_vals) if hasattr(time_vals, 'dtype') else np.array(time_vals, dtype=float)
            idx = np.argmin(np.abs(time_num - x_num))

            for i, (ch_name, ch_data) in enumerate(self.loader.temp_channels.items()):
                visible = True
                if hasattr(self, '_temp_channel_vars') and ch_name in self._temp_channel_vars:
                    visible = self._temp_channel_vars[ch_name].get()
                if not visible:
                    continue

                val = ch_data[idx] if idx < len(ch_data) else None
                if val is None:
                    continue

                color = CHANNEL_COLORS[i % len(CHANNEL_COLORS)]

                # Convert data coords to figure-pixel coords (origin bottom-left),
                # then flip Y for canvas (origin top-left)
                disp_x, disp_y = self.temp_ax.transData.transform((x_num, val))
                canvas_y = self.temp_fig.bbox.height - disp_y

                # Draw dot at intersection
                r = 4
                tk_canvas.create_oval(disp_x - r, canvas_y - r, disp_x + r, canvas_y + r,
                                       fill=color, outline='white', width=1, tags="crosshair")

                # Draw value label
                label = f"{ch_name}: {val:.1f}"
                text_w = len(label) * 6 + 8
                lx = disp_x + 12
                ly = canvas_y
                if lx + text_w > w - 5:
                    lx = disp_x - text_w - 12
                if ly < 10:
                    ly = 10
                if ly > h - 10:
                    ly = h - 10
                tk_canvas.create_rectangle(lx - 2, ly - 10, lx + text_w, ly + 10,
                                            fill='#ffffcc', outline=color, tags="crosshair")
                tk_canvas.create_text(lx, ly, text=label, fill=color,
                                       font=("Segoe UI", 8, "bold"), anchor='w', tags="crosshair")

    def _on_temp_leave(self, event):
        self.temp_canvas.get_tk_widget().delete("crosshair")

    def _build_statusbar(self):
        sb = ttk.Frame(self.root, style="Status.TFrame")
        sb.pack(fill=tk.X, side=tk.BOTTOM)

        self.status_var = tk.StringVar(value="Готово")
        ttk.Label(sb, textvariable=self.status_var, style="Status.TLabel").pack(side=tk.LEFT)

        self.stats_var = tk.StringVar(value="")
        ttk.Label(sb, textvariable=self.stats_var, style="Status.TLabel").pack(side=tk.RIGHT)

    def _make_tree(self, parent):
        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        tree = ttk.Treeview(container, show="headings", selectmode="browse")
        vsb = ttk.Scrollbar(container, orient=tk.VERTICAL, command=tree.yview)
        hsb = ttk.Scrollbar(container, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)
        return tree

    def _populate_tree(self, tree, df):
        tree.delete(*tree.get_children())
        if df is None or df.empty:
            return
        cols = list(df.columns)
        tree["columns"] = cols
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=130, minwidth=80, anchor=tk.CENTER)
        for i, (_, row) in enumerate(df.iterrows()):
            vals = [str(v) if pd.notna(v) else "" for v in row]
            tag = "even" if i % 2 == 0 else "odd"
            tree.insert("", tk.END, values=vals, tags=(tag,))
        tree.tag_configure("even", background="#f8fafc")
        tree.tag_configure("odd", background="#ffffff")

    def _populate_notebook_tabs(self, notebook, tabs_dict, channels, time_col):
        for t in tabs_dict.values():
            notebook.forget(t)
        tabs_dict.clear()

        if not channels:
            return

        for ch_name, ch_data in channels.items():
            frame = ttk.Frame(notebook)
            tabs_dict[ch_name] = frame
            notebook.add(frame, text=f"  {ch_name}  ")
            tree = self._make_tree(frame)
            df = pd.DataFrame({"Время, мсек": time_col, "Датчик Холла": ch_data})
            self._populate_tree(tree, df)

    def _show_single_tab(self, notebook, tabs_dict, label, df):
        for t in tabs_dict.values():
            notebook.forget(t)
        tabs_dict.clear()
        if df is None or df.empty:
            return
        frame = ttk.Frame(notebook)
        tabs_dict[label] = frame
        notebook.add(frame, text=f"  {label}  ")
        tree = self._make_tree(frame)
        self._populate_tree(tree, df)

    def _update_channel_toggles(self):
        for w in self.channel_toggle_frame.winfo_children():
            w.destroy()
        for w in self.result_toggle_frame.winfo_children():
            w.destroy()

        if not self.loader.dynamics_channels:
            return

        ttk.Label(self.channel_toggle_frame, text="Слои:", background=BG,
                  font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(4, 4))

        self._channel_vars = {}
        for i, ch_name in enumerate(self.loader.dynamics_channels.keys()):
            is_zero = np.all(self.loader.dynamics_channels[ch_name] == 0)
            var = tk.BooleanVar(value=not is_zero)
            self._channel_vars[ch_name] = var
            color = CHANNEL_COLORS[i % len(CHANNEL_COLORS)]
            cb = tk.Checkbutton(self.channel_toggle_frame, text=ch_name, variable=var,
                                bg=BG, fg=color, selectcolor=BG,
                                activebackground=BG, activeforeground=color,
                                font=("Segoe UI", 9, "bold"),
                                command=self._draw_raw_chart)
            cb.pack(side=tk.LEFT, padx=2)

        if self.loader.calib_channels:
            names = list(self.loader.calib_channels.keys())
            self._selected_calib = None

        if self.loader.result_channels:
            ttk.Label(self.result_toggle_frame, text="Результат:", background=BG,
                      font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(4, 4))

            self._result_vars = {}
            for i, ch_name in enumerate(self.loader.result_channels.keys()):
                var = tk.BooleanVar(value=True)
                self._result_vars[ch_name] = var
                color = CHANNEL_COLORS[i % len(CHANNEL_COLORS)]
                cb = tk.Checkbutton(self.result_toggle_frame, text=ch_name, variable=var,
                                    bg=BG, fg=color, selectcolor=BG,
                                    activebackground=BG, activeforeground=color,
                                    font=("Segoe UI", 9, "bold"),
                                    command=self._draw_result_chart)
                cb.pack(side=tk.LEFT, padx=2)

    def load_file(self):
        path = filedialog.askopenfilename(
            title="Выберите Excel-файл",
            filetypes=[("Excel файлы", "*.xlsx"), ("Все файлы", "*.*")]
        )
        if not path:
            return
        try:
            self.status_var.set("Загрузка файла...")
            self.file_label.configure(text="Загрузка...")
            
            # Мгновенная загрузка без блокировки UI
            self.loader.load_excel(path)
            self._file_path = Path(path)

            # Обновляем UI через after() чтобы не блокировать интерфейс
            self.root.after(0, self._finalize_load_file)
        except Exception as e:
            messagebox.showerror("Ошибка загрузки", str(e))
            self.status_var.set("Ошибка загрузки")
            self.file_label.configure(text="Ошибка")
    
    def _finalize_load_file(self):
        """Финализация загрузки файла в главном потоке."""
        try:
            # Show tabs per layer if channels were loaded
            if self.loader.dynamics_channels:
                self._populate_notebook_tabs(self.source_notebook, self._source_tabs,
                                             self.loader.dynamics_channels, self.loader.dynamics_time)
            else:
                self._show_single_tab(self.source_notebook, self._source_tabs,
                                       "Данные", self.loader.source_data)

            if self.loader.calib_channels:
                self._populate_notebook_tabs(self.calib_notebook, self._calib_tabs,
                                             self.loader.calib_channels, self.loader.calib_disp)
            else:
                self._show_single_tab(self.calib_notebook, self._calib_tabs,
                                       "Тарировка", self.loader.calib_data)
            self.tree_result.delete(*self.tree_result.get_children())

            self.result_ax.clear()
            self.result_ax.text(0.5, 0.5, "Выполняется расчёт...",
                                ha="center", va="center", transform=self.result_ax.transAxes,
                                fontsize=13, color="#94a3b8", style="italic")
            self.result_ax.set_axis_off()
            self.result_fig.tight_layout()
            self.result_canvas.draw()

            self._update_channel_toggles()
            self._draw_raw_chart()

            src_n = len(self.loader.source_data) if self.loader.source_data is not None else 0
            cal_n = len(self.loader.calib_data) if self.loader.calib_data is not None else 0
            self.file_label.configure(text=self._file_path.name)
            self.status_var.set(f"Загружено: {self._file_path.name}")
            self.stats_var.set(f"Исходных: {src_n}  |  Калибровка: {cal_n} точек")

            self.calculate()
        except Exception as e:
            messagebox.showerror("Ошибка загрузки", str(e))
            self.status_var.set("Ошибка загрузки")
            self.file_label.configure(text="Ошибка")

    def _on_drop_root(self, files):
        """Determine drop zone by mouse position and load the file."""
        if not files:
            return
        path = files[0].decode('mbcs') if isinstance(files[0], bytes) else str(files[0])
        if not path:
            return

        # Get mouse position and find which widget is under cursor
        mx = self.root.winfo_pointerx()
        my = self.root.winfo_pointery()
        widget = self.root.winfo_containing(mx, my)

        # Walk up the widget tree to find if we're in source or calibration area
        in_source = False
        in_calib = False
        w = widget
        while w is not None:
            if w == self.source_notebook:
                in_source = True
                break
            if w == self.calib_notebook:
                in_calib = True
                break
            try:
                w = w.master
            except:
                break

        if in_source:
            self._on_drop_dynamics(files)
        elif in_calib:
            self._on_drop_calibration(files)
        else:
            # Default: try to determine by horizontal position
            src_x = self.source_notebook.winfo_rootx()
            src_w = self.source_notebook.winfo_width()
            if mx >= src_x and mx <= src_x + src_w:
                self._on_drop_dynamics(files)
            else:
                self._on_drop_calibration(files)

    def _on_drop_dynamics(self, files):
        if not files:
            return
        path = files[0].decode('mbcs') if isinstance(files[0], bytes) else str(files[0])
        if not path:
            return
        try:
            self.status_var.set("Загрузка динамики...")
            
            # Мгновенная загрузка без блокировки UI
            if path.lower().endswith('.xlsx'):
                self.loader.load_dynamics_xlsx(path)
            else:
                self.loader.load_dynamics_csv(path)
            self._dynamics_file_path = Path(path)
            self.loader.per_layer_calib = {}

            if self._file_path is None:
                self._file_path = self._dynamics_file_path
            
            # Обновляем UI через after() чтобы не блокировать интерфейс
            self.root.after(0, lambda: self._finalize_dynamics_load())
        except Exception as e:
            messagebox.showerror("Ошибка загрузки", str(e))
            self.status_var.set("Ошибка загрузки")
    
    def _finalize_dynamics_load(self):
        """Финализация загрузки динамики в главном потоке."""
        try:
            self._populate_notebook_tabs(self.source_notebook, self._source_tabs,
                                         self.loader.dynamics_channels, self.loader.dynamics_time)
            self._update_channel_toggles()
            self._draw_raw_chart()

            n_ch = len(self.loader.dynamics_channels)
            self.file_label.configure(text=f"Динамика: {self._dynamics_file_path.name}")
            self.status_var.set(f"Загружена динамика: {self._dynamics_file_path.name} ({n_ch} каналов)")

            if self.loader.calib_data is not None:
                self.calculate()
        except Exception as e:
            messagebox.showerror("Ошибка загрузки", str(e))
            self.status_var.set("Ошибка загрузки")

    def _on_drop_calibration(self, files):
        if not files:
            return
        if not self.loader.dynamics_channels:
            messagebox.showwarning("Внимание", "Сначала загрузите файл Динамики.")
            return
        path = files[0].decode('mbcs') if isinstance(files[0], bytes) else str(files[0])
        if not path:
            return
        try:
            self.status_var.set("Загрузка тарировки...")
            
            # Мгновенная загрузка без блокировки UI
            layer_name = self._selected_source_layer
            if not layer_name:
                layer_name = list(self.loader.dynamics_channels.keys())[0]

            self.loader.load_calibration_for_layer(path, layer_name)
            self._calibration_file_path = Path(path)

            if self._file_path is None:
                self._file_path = self._calibration_file_path
            
            # Обновляем UI через after() чтобы не блокировать интерфейс
            self.root.after(0, lambda: self._finalize_calibration_load(layer_name))
        except Exception as e:
            messagebox.showerror("Ошибка загрузки", str(e))
            self.status_var.set("Ошибка загрузки")
    
    def _finalize_calibration_load(self, layer_name):
        """Финализация загрузки тарировки в главном потоке."""
        try:
            self._update_calib_notebook_for_layer()

            n_loaded = len(self.loader.per_layer_calib)
            n_total = len(self.loader.dynamics_channels)
            self.status_var.set(f"Тарировка загружена для {layer_name} ({n_loaded}/{n_total} слоёв)")

            self.calculate()
        except Exception as e:
            messagebox.showerror("Ошибка загрузки", str(e))
            self.status_var.set("Ошибка загрузки")

    def load_dynamics_csv(self):
        path = filedialog.askopenfilename(
            title="Выберите файл Динамика (CSV/XLSX)",
            filetypes=[("Все файлы", "*.csv *.xlsx"), ("CSV файлы", "*.csv"), ("Excel файлы", "*.xlsx")]
        )
        if not path:
            return
        try:
            self.status_var.set("Загрузка динамики...")
            
            # Мгновенная загрузка без блокировки UI
            if path.lower().endswith('.xlsx'):
                self.loader.load_dynamics_xlsx(path)
            else:
                self.loader.load_dynamics_csv(path)
            self._dynamics_file_path = Path(path)
            self.loader.per_layer_calib = {}

            if self._file_path is None:
                self._file_path = self._dynamics_file_path
            
            # Обновляем UI через after() чтобы не блокировать интерфейс
            self.root.after(0, lambda: self._finalize_dynamics_csv_load())
        except Exception as e:
            messagebox.showerror("Ошибка загрузки", str(e))
            self.status_var.set("Ошибка загрузки")
    
    def _finalize_dynamics_csv_load(self):
        """Финализация загрузки CSV динамики в главном потоке."""
        try:
            self._populate_notebook_tabs(self.source_notebook, self._source_tabs,
                                         self.loader.dynamics_channels, self.loader.dynamics_time)
            self._update_channel_toggles()
            self._draw_raw_chart()

            n_ch = len(self.loader.dynamics_channels)
            src_n = len(self.loader.source_data) if self.loader.source_data is not None else 0
            self.file_label.configure(text=f"Динамика: {self._dynamics_file_path.name}")
            self.status_var.set(f"Загружена динамика: {self._dynamics_file_path.name} ({n_ch} каналов)")

            # Обновляем автоматические диапазоны для пиков после загрузки динамики
            self._update_auto_peak_ranges()

            if self.loader.calib_data is not None:
                self.calculate()
        except Exception as e:
            messagebox.showerror("Ошибка загрузки", str(e))
            self.status_var.set("Ошибка загрузки")

    def load_calibration_csv(self):
        if not self.loader.dynamics_channels:
            messagebox.showwarning("Внимание", "Сначала загрузите файл Динамики.")
            return
        path = filedialog.askopenfilename(
            title="Выберите файл Тарировка (CSV/XLSX)",
            filetypes=[("Все файлы", "*.csv *.xlsx"), ("CSV файлы", "*.csv"), ("Excel файлы", "*.xlsx")]
        )
        if not path:
            return
        try:
            self.status_var.set("Загрузка тарировки...")
            
            # Мгновенная загрузка без блокировки UI
            layer_name = self._selected_source_layer
            if not layer_name:
                layer_name = list(self.loader.dynamics_channels.keys())[0]

            self.loader.load_calibration_for_layer(path, layer_name)
            self._calibration_file_path = Path(path)

            if self._file_path is None:
                self._file_path = self._calibration_file_path
            
            # Обновляем UI через after() чтобы не блокировать интерфейс
            self.root.after(0, lambda: self._finalize_calibration_csv_load(layer_name))
        except Exception as e:
            messagebox.showerror("Ошибка загрузки", str(e))
            self.status_var.set("Ошибка загрузки")
    
    def _finalize_calibration_csv_load(self, layer_name):
        """Финализация загрузки CSV тарировки в главном потоке."""
        try:
            self._update_calib_notebook_for_layer()

            n_loaded = len(self.loader.per_layer_calib)
            n_total = len(self.loader.dynamics_channels)
            self.status_var.set(f"Тарировка загружена для {layer_name} ({n_loaded}/{n_total} слоёв)")

            if self._dynamics_file_path:
                self.file_label.configure(
                    text=f"Динамика: {self._dynamics_file_path.name}  |  Тарировка: {self._calibration_file_path.name}")
            else:
                self.file_label.configure(text=f"Тарировка: {self._calibration_file_path.name}")

            self.calculate()
        except Exception as e:
            messagebox.showerror("Ошибка загрузки", str(e))
            self.status_var.set("Ошибка загрузки")

    def load_dynamics_xlsx(self):
        path = filedialog.askopenfilename(
            title="Выберите файл Динамика (XLSX)",
            filetypes=[("Excel файлы", "*.xlsx"), ("Все файлы", "*.*")]
        )
        if not path:
            return
        try:
            self.status_var.set("Загрузка динамики...")
            
            # Мгновенная загрузка без блокировки UI
            self.loader.load_dynamics_xlsx(path)
            self._dynamics_file_path = Path(path)
            self.loader.per_layer_calib = {}

            if self._file_path is None:
                self._file_path = self._dynamics_file_path
            
            # Обновляем UI через after() чтобы не блокировать интерфейс
            self.root.after(0, lambda: self._finalize_dynamics_xlsx_load())
        except Exception as e:
            messagebox.showerror("Ошибка загрузки", str(e))
            self.status_var.set("Ошибка загрузки")
    
    def _finalize_dynamics_xlsx_load(self):
        """Финализация загрузки XLSX динамики в главном потоке."""
        try:
            self._populate_notebook_tabs(self.source_notebook, self._source_tabs,
                                         self.loader.dynamics_channels, self.loader.dynamics_time)
            self._update_channel_toggles()
            self._draw_raw_chart()

            n_ch = len(self.loader.dynamics_channels)
            src_n = len(self.loader.source_data) if self.loader.source_data is not None else 0
            self.file_label.configure(text=f"Динамика: {self._dynamics_file_path.name}")
            self.status_var.set(f"Загружена динамика: {self._dynamics_file_path.name} ({n_ch} каналов)")

            # Обновляем автоматические диапазоны для пиков после загрузки динамики
            self._update_auto_peak_ranges()

            if self.loader.calib_data is not None:
                self.calculate()
        except Exception as e:
            messagebox.showerror("Ошибка загрузки", str(e))
            self.status_var.set("Ошибка загрузки")

    def load_calibration_xlsx(self):
        if not self.loader.dynamics_channels:
            messagebox.showwarning("Внимание", "Сначала загрузите файл Динамики.")
            return
        path = filedialog.askopenfilename(
            title="Выберите файл Тарировка (XLSX)",
            filetypes=[("Excel файлы", "*.xlsx"), ("Все файлы", "*.*")]
        )
        if not path:
            return
        try:
            self.status_var.set("Загрузка тарировки...")
            
            # Мгновенная загрузка без блокировки UI
            layer_name = self._selected_source_layer
            if not layer_name:
                layer_name = list(self.loader.dynamics_channels.keys())[0]

            self.loader.load_calibration_for_layer(path, layer_name)
            self._calibration_file_path = Path(path)

            if self._file_path is None:
                self._file_path = self._calibration_file_path
            
            # Обновляем UI через after() чтобы не блокировать интерфейс
            self.root.after(0, lambda: self._finalize_calibration_xlsx_load(layer_name))
        except Exception as e:
            messagebox.showerror("Ошибка загрузки", str(e))
            self.status_var.set("Ошибка загрузки")
    
    def _finalize_calibration_xlsx_load(self, layer_name):
        """Финализация загрузки XLSX тарировки в главном потоке."""
        try:
            self._update_calib_notebook_for_layer()

            n_loaded = len(self.loader.per_layer_calib)
            n_total = len(self.loader.dynamics_channels)
            self.status_var.set(f"Тарировка загружена для {layer_name} ({n_loaded}/{n_total} слоёв)")

            if self._dynamics_file_path:
                self.file_label.configure(
                    text=f"Динамика: {self._dynamics_file_path.name}  |  Тарировка: {self._calibration_file_path.name}")
            else:
                self.file_label.configure(text=f"Тарировка: {self._calibration_file_path.name}")

            self.calculate()
        except Exception as e:
            messagebox.showerror("Ошибка загрузки", str(e))
            self.status_var.set("Ошибка загрузки")

    def _reset_dynamics(self):
        self.loader.dynamics_channels = None
        self.loader.dynamics_time = None
        self.loader.source_data = None
        self.loader.result_df = None
        self.loader.result_channels = None
        self.loader.magnet_position = None
        self.loader.magnet_info = ""
        self.loader.calib_branches = None
        self.loader.trimmed_calib = None
        self.loader._magnet_intersections = {}
        self.loader._magnet_x = None
        self.loader.zero_point = None
        self.loader.auto_zero_point = None
        self.loader.manual_zero_point = None
        self.loader.channel_mins = None
        self.loader.channel_baselines = None
        self._peak_range = None
        self._calib_range_highlights.clear()
        self.loader.per_layer_calib = {}
        self.loader._per_layer_calib_info = {}
        self.loader._per_layer_manual = {}
        self._dynamics_file_path = None

        for t in self._source_tabs.values():
            self.source_notebook.forget(t)
        self._source_tabs.clear()

        self._draw_raw_chart()
        self._draw_magnet_chart()
        self._draw_result_chart()
        self.tree_result.delete(*self.tree_result.get_children())
        self._update_channel_toggles()
        self._clear_peak_chart()
        self._update_calib_selection_panel()

        if self._calibration_file_path:
            self.file_label.configure(text=f"Тарировка: {self._calibration_file_path.name}")
        else:
            self.file_label.configure(text="Файл не загружен")
        self.status_var.set("Динамика сброшена")

    def _reset_calibration(self):
        self.loader.calib_channels = None
        self.loader.calib_disp = None
        self.loader.calib_data = None
        self.loader.per_layer_calib = {}
        self.loader._per_layer_calib_info = {}
        self.loader._per_layer_manual = {}
        self.loader._global_calib_info = {}
        self.loader._global_calib_manual = {}
        self.loader.result_df = None
        self.loader.result_channels = None
        self.loader.magnet_position = None
        self.loader.magnet_info = ""
        self.loader.calib_branches = None
        self.loader.trimmed_calib = None
        self.loader._magnet_intersections = {}
        self.loader._magnet_x = None
        self.loader.zero_point = None
        self.loader.auto_zero_point = None
        self.loader.manual_zero_point = None
        self.loader.channel_mins = None
        self.loader.channel_baselines = None
        self._peak_range = None
        self._calib_range_highlights.clear()
        self._calibration_file_path = None

        for t in self._calib_tabs.values():
            self.calib_notebook.forget(t)
        self._calib_tabs.clear()

        self._draw_disp_chart()
        self._draw_magnet_chart()
        self._draw_result_chart()
        self.tree_result.delete(*self.tree_result.get_children())
        self._update_channel_toggles()
        self._clear_peak_chart()

        if self._dynamics_file_path:
            self.file_label.configure(text=f"Динамика: {self._dynamics_file_path.name}")
        else:
            self.file_label.configure(text="Файл не загружен")
        self.status_var.set("Тарировка сброшена")
        self._update_calib_selection_panel()

    def _update_calib_selection_panel(self):
        for w in self.calib_sel_inner.winfo_children():
            w.destroy()
        self._calib_sel_widgets.clear()

        has_per_layer = bool(self.loader.per_layer_calib)
        has_old_calib = bool(self.loader.calib_channels)

        if not has_per_layer and not has_old_calib:
            ttk.Label(self.calib_sel_inner,
                      text="Загрузите тарировку и выполните расчёт",
                      background=PANEL_BG, foreground="#94a3b8",
                      font=("Segoe UI", 10, "italic")).pack(padx=8, pady=12)
            self.calib_sel_info_label.configure(text="")
            return

        header = ttk.Frame(self.calib_sel_inner)
        header.pack(fill=tk.X, padx=4, pady=(4, 2))
        for col, text, width in [
            (0, "Слой", 90), (1, "Датчик", 110),
            (2, "От, мм", 70), (3, "До, мм", 70), (4, "Режим", 80), (5, "", 8)
        ]:
            ttk.Label(header, text=text, background=PANEL_BG, foreground=ACCENT,
                      font=("Segoe UI", 9, "bold"), width=width).grid(row=0, column=col, padx=2)

        if has_per_layer:
            for layer_name in self.loader.dynamics_channels.keys():
                if layer_name not in self.loader.per_layer_calib:
                    continue
                info = self.loader._per_layer_calib_info.get(layer_name)
                cal = self.loader.per_layer_calib[layer_name]
                sensor_names = list(cal["tug"].keys())
                if not info:
                    auto_range = getattr(self.loader, '_per_layer_auto_range', {}).get(layer_name)
                    auto_sensor = getattr(self.loader, '_per_layer_selected_sensor', {}).get(layer_name)
                    magnet_x = getattr(self.loader, '_per_layer_magnet_x', {}).get(layer_name)
                    if auto_range:
                        auto_left, auto_right = auto_range
                    else:
                        auto_left, auto_right = self.calculator._find_layer_overlap(cal["disp"], cal["tug"])
                    if not auto_sensor or auto_sensor not in sensor_names:
                        auto_sensor = sensor_names[0]
                    info = {
                        "sensor": auto_sensor,
                        "range_left": auto_left,
                        "range_right": auto_right,
                        "auto_sensor": auto_sensor,
                        "auto_range_left": auto_left,
                        "auto_range_right": auto_right,
                        "manual_sensor": False,
                        "manual_range": False,
                        "magnet_x": magnet_x,
                    }
                self._add_calib_sel_row(layer_name, sensor_names, info)
            loaded = len(self.loader.per_layer_calib)
            total = len(self.loader.dynamics_channels)
            self.calib_sel_info_label.configure(
                text=f"Тарировка: {loaded}/{total} слоёв  |  ▬ — выбор на графике")
        else:
            info = self.loader._global_calib_info
            sensor_names = list(self.loader.calib_channels.keys())
            if not info:
                auto_left, auto_right = self.calculator._find_overlap_region()
                info = {
                    "sensor": sensor_names[0] if sensor_names else "",
                    "range_left": auto_left,
                    "range_right": auto_right,
                    "auto_sensor": sensor_names[0] if sensor_names else "",
                    "auto_range_left": auto_left,
                    "auto_range_right": auto_right,
                    "manual_sensor": False,
                    "manual_range": False,
                }
            self._add_calib_sel_row("Все слои", sensor_names, info, is_global=True)
            self.calib_sel_info_label.configure(text="Общая тарировка  |  ▬ — выбор на графике")

    def _add_calib_sel_row(self, layer_name, sensor_names, info, is_global=False):
        row = ttk.Frame(self.calib_sel_inner)
        row.pack(fill=tk.X, padx=4, pady=3)

        sensor = info.get("sensor", sensor_names[0] if sensor_names else "")
        r_left = info.get("range_left", info.get("auto_range_left", 0))
        r_right = info.get("range_right", info.get("auto_range_right", 0))

        mode_parts = []
        if info.get("manual_sensor"):
            mode_parts.append("датчик")
        if info.get("manual_range"):
            mode_parts.append("диапазон")
        mode_text = "вручную" if mode_parts else "авто"

        ttk.Label(row, text=layer_name, background=PANEL_BG,
                  font=("Segoe UI", 9, "bold"), width=12).grid(row=0, column=0, padx=2, sticky="w")

        sensor_var = tk.StringVar(value=sensor)
        sensor_cb = ttk.Combobox(row, textvariable=sensor_var, values=sensor_names,
                                 state="readonly", width=14, font=("Segoe UI", 9))
        sensor_cb.grid(row=0, column=1, padx=2)

        left_var = tk.StringVar(value=f"{r_left:.1f}")
        left_entry = ttk.Entry(row, textvariable=left_var, width=8, font=("Consolas", 9))
        left_entry.grid(row=0, column=2, padx=2)

        right_var = tk.StringVar(value=f"{r_right:.1f}")
        right_entry = ttk.Entry(row, textvariable=right_var, width=8, font=("Consolas", 9))
        right_entry.grid(row=0, column=3, padx=2)

        auto_sensor = info.get("auto_sensor", sensor)
        auto_left = info.get("auto_range_left", r_left)
        auto_right = info.get("auto_range_right", r_right)
        magnet_x = info.get("magnet_x")
        mag_hint = f"  X={magnet_x:.1f}" if magnet_x is not None else ""
        auto_label = ttk.Label(
            row,
            text=f"{mode_text}\n↑ {auto_left:.1f}—{auto_right:.1f} мм{mag_hint}",
            background=PANEL_BG, foreground="#64748b", font=("Segoe UI", 8), width=12)
        auto_label.grid(row=0, column=4, padx=2, sticky="w")

        ttk.Button(row, text="▬", width=3, style="ToolbarCsv.TButton",
                   command=lambda ln=layer_name: self._start_calib_range_selection(ln)
                   ).grid(row=0, column=5, padx=2)

        self._calib_sel_widgets[layer_name] = {
            "sensor_var": sensor_var,
            "left_var": left_var,
            "right_var": right_var,
            "auto_label": auto_label,
            "is_global": is_global,
            "auto_sensor": auto_sensor,
            "auto_left": auto_left,
            "auto_right": auto_right,
        }
        
        # Добавляем привязку для обновления метки режима при изменении значений
        def on_manual_change(*args):
            self._update_calib_row_mode(layer_name)
        
        sensor_var.trace_add("write", on_manual_change)
        left_var.trace_add("write", on_manual_change)
        right_var.trace_add("write", on_manual_change)

    def _update_calib_row_mode(self, layer_name):
        """Обновление метки режима при ручном изменении значений."""
        if layer_name not in self._calib_sel_widgets:
            return
        
        widgets = self._calib_sel_widgets[layer_name]
        auto_sensor = widgets["auto_sensor"]
        auto_left = widgets["auto_left"]
        auto_right = widgets["auto_right"]
        
        sensor = widgets["sensor_var"].get()
        try:
            left = float(widgets["left_var"].get().replace(",", "."))
            right = float(widgets["right_var"].get().replace(",", "."))
        except ValueError:
            return
        
        mode_parts = []
        if sensor != auto_sensor:
            mode_parts.append("датчик")
        if abs(left - auto_left) > 0.01 or abs(right - auto_right) > 0.01:
            mode_parts.append("диапазон")
        
        mode_text = "вручную" if mode_parts else "авто"
        
        # Получаем magnet_x из данных калибровки
        magnet_x = None
        if layer_name in self.loader._per_layer_magnet_x:
            magnet_x = self.loader._per_layer_magnet_x.get(layer_name)
        mag_hint = f"  X={magnet_x:.1f}" if magnet_x is not None else ""
        
        widgets["auto_label"].configure(
            text=f"{mode_text}\n↑ {auto_left:.1f}—{auto_right:.1f} мм{mag_hint}"
        )

    def _apply_calib_selection(self):
        if not self._calib_sel_widgets:
            return
        try:
            for layer_name, widgets in self._calib_sel_widgets.items():
                sensor = widgets["sensor_var"].get()
                left = float(widgets["left_var"].get().replace(",", "."))
                right = float(widgets["right_var"].get().replace(",", "."))
                self._calib_range_highlights[layer_name] = (left, right)

                auto_sensor = widgets["auto_sensor"]
                auto_left = widgets["auto_left"]
                auto_right = widgets["auto_right"]

                if widgets["is_global"]:
                    manual = {}
                    if sensor != auto_sensor:
                        manual["sensor"] = sensor
                    if abs(left - auto_left) > 0.01:
                        manual["range_left"] = left
                    if abs(right - auto_right) > 0.01:
                        manual["range_right"] = right
                    self.loader._global_calib_manual = manual
                else:
                    manual_sensor = sensor if sensor != auto_sensor else None
                    manual_left = left if abs(left - auto_left) > 0.01 else None
                    manual_right = right if abs(right - auto_right) > 0.01 else None
                    if manual_sensor or manual_left is not None or manual_right is not None:
                        self.loader.set_layer_manual(
                            layer_name,
                            sensor=manual_sensor,
                            range_left=manual_left,
                            range_right=manual_right,
                        )
                    else:
                        self.loader.clear_layer_manual(layer_name)

            self.calculate()
            self.status_var.set("Настройки тарировки применены")
        except ValueError:
            messagebox.showerror("Ошибка", "Проверьте числовые значения диапазона (мм)")

    def _disconnect_calib_range_handlers(self):
        for attr in ('_calib_range_press_id', '_calib_range_release_id'):
            cid = getattr(self, attr, None)
            if cid is not None:
                try:
                    self.disp_canvas.mpl_disconnect(cid)
                except Exception:
                    pass
                setattr(self, attr, None)
        self._calib_range_selection_active = False

    def _disconnect_peak_handlers(self):
        for attr in ('_peak_press_id', '_peak_release_id'):
            cid = getattr(self, attr, None)
            if cid is not None:
                try:
                    self.result_canvas.mpl_disconnect(cid)
                except Exception:
                    pass
                setattr(self, attr, None)
        self._peak_selection_active = False

    def _reset_calib_manual(self):
        self.loader._per_layer_manual.clear()
        self.loader._global_calib_manual.clear()
        self._calib_range_highlights.clear()
        if self.loader.source_data is not None and (
                self.loader.per_layer_calib or self.loader.calib_channels):
            self.calculate()
            self.status_var.set("Ручные настройки тарировки сброшены")

    def _get_calib_range_target(self):
        if self.loader.per_layer_calib:
            layer = self._selected_source_layer
            if not layer or layer not in self.loader.per_layer_calib:
                layers = [ln for ln in self.loader.dynamics_channels
                          if ln in self.loader.per_layer_calib]
                if not layers:
                    return None
                layer = layers[0]
            return layer
        if self.loader.calib_channels:
            return "Все слои"
        return None

    def _start_calib_range_selection(self, layer_name=None):
        target = layer_name or self._get_calib_range_target()
        if not target:
            messagebox.showinfo("Информация", "Сначала загрузите тарировку")
            return

        self._disconnect_calib_range_handlers()
        self._calib_range_target = target
        self._calib_range_selection_active = True
        self._calib_range_selection_start = None

        self.raw_notebook.select(self.tab_disp)

        if self._calib_range_selection_rect is not None:
            self._calib_range_selection_rect.remove()
            self._calib_range_selection_rect = None

        self._draw_disp_chart(draw_magnet=False)

        self._calib_range_press_id = self.disp_canvas.mpl_connect(
            'button_press_event', self._on_calib_range_press)
        self._calib_range_release_id = self.disp_canvas.mpl_connect(
            'button_release_event', self._on_calib_range_release)
        self.status_var.set(
            f"Выберите диапазон на графике тарировки для «{target}» (кликните и перетащите)")

    def _on_calib_range_press(self, event):
        if not self._calib_range_selection_active:
            return
        if event.inaxes != self.disp_ax:
            self._disconnect_calib_range_handlers()
            return
        self._calib_range_selection_start = event.xdata
        if self._calib_range_selection_rect is not None:
            self._calib_range_selection_rect.remove()
            self._calib_range_selection_rect = None
            self.disp_canvas.draw()

    def _on_calib_range_release(self, event):
        if not self._calib_range_selection_active:
            return
        if event.inaxes != self.disp_ax or self._calib_range_selection_start is None:
            return

        x_start = self._calib_range_selection_start
        x_end = event.xdata
        if x_start > x_end:
            x_start, x_end = x_end, x_start
        if abs(x_end - x_start) < 0.1:
            return

        self._calib_range_selection_rect = self.disp_ax.axvspan(
            x_start, x_end, alpha=0.25, color='#fbbf24', zorder=0)
        self.disp_canvas.draw()

        self.disp_canvas.mpl_disconnect(self._calib_range_press_id)
        self.disp_canvas.mpl_disconnect(self._calib_range_release_id)
        self._calib_range_press_id = None
        self._calib_range_release_id = None
        self._calib_range_selection_active = False
        self._calib_range_selection_rect = None

        target = self._calib_range_target
        if target and target in self._calib_sel_widgets:
            widgets = self._calib_sel_widgets[target]
            widgets["left_var"].set(f"{x_start:.1f}")
            widgets["right_var"].set(f"{x_end:.1f}")

        self._calib_range_highlights[target] = (x_start, x_end)
        self.status_var.set(f"Диапазон «{target}»: {x_start:.1f} — {x_end:.1f} мм")
        self.root.after(50, self._apply_calib_selection)

    def calculate(self):
        if self._calculating:
            return
        has_per_layer = bool(self.loader.per_layer_calib)
        has_old_calib = self.loader.calib_data is not None

        if self.loader.source_data is None:
            return
        if not has_per_layer and not has_old_calib:
            return

        self._calculating = True
        self.status_var.set("Выполнение расчёта...")
        
        # Запускаем вычисления в фоновом потоке для неблокирующего UI
        import threading
        
        def do_calculate():
            try:
                if has_per_layer:
                    self.loader.calculate_per_layer_magnet()
                    self.loader.calculate_per_layer()
                else:
                    self.loader.calculate()
                return True
            except Exception as e:
                raise e
        
        def on_complete(result):
            try:
                self._populate_tree(self.tree_result, self.loader.result_df)
                self._update_channel_toggles()
                self._draw_result_chart()
                self._draw_disp_chart(draw_magnet=False)
                self._draw_magnet_chart()
                self._update_calib_selection_panel()

                if self.loader.auto_zero_point is not None:
                    if self.loader.manual_zero_point is None:
                        pass  # Removed manual zero var usage

                # Обновляем автоматические диапазоны для пиков после расчёта
                self._update_auto_peak_ranges()

                if self._peak_range is not None:
                    self._calculate_and_draw_peaks(*self._peak_range)

                n = len(self.loader.result_df)
                mn = self.loader.result_df.iloc[:, 1].min()
                mx = self.loader.result_df.iloc[:, 1].max()

                src_n = len(self.loader.source_data) if self.loader.source_data is not None else 0
                cal_n = len(self.loader.calib_data) if self.loader.calib_data is not None else 0
                mag = self.loader.magnet_info
                n_ch = len(self.loader.result_channels) if self.loader.result_channels else 1
                self.stats_var.set(f"Каналов: {n_ch}  |  Результат: {n} точек  |  {mn} — {mx} мм  |  {mag}")
                self.status_var.set("Расчёт завершён")
            except Exception as e:
                messagebox.showerror("Ошибка расчёта", str(e))
                self.status_var.set("Ошибка расчёта")
            finally:
                self._calculating = False
        
        def on_error(error):
            messagebox.showerror("Ошибка расчёта", str(error))
            self.status_var.set("Ошибка расчёта")
            self._calculating = False
        
        def task_wrapper():
            try:
                result = do_calculate()
                self.root.after(0, lambda: on_complete(result))
            except Exception as e:
                self.root.after(0, lambda: on_error(e))
        
        thread = threading.Thread(target=task_wrapper, daemon=True)
        thread.start()

    def _draw_result_chart(self):
        self.result_ax.clear()
        self.result_ax.set_title("Перемещение от времени")

        # График "Перемещение от времени" должен показывать сырые данные (без центрирования)
        if hasattr(self.loader, 'result_channels_raw') and self.loader.result_channels_raw:
            visible_any = False
            for i, (ch_name, ch_data) in enumerate(self.loader.result_channels_raw.items()):
                visible = True
                if hasattr(self, '_result_vars') and ch_name in self._result_vars:
                    visible = self._result_vars[ch_name].get()
                if visible:
                    color = CHANNEL_COLORS[i % len(CHANNEL_COLORS)]
                    self.result_ax.plot(self.loader.dynamics_time, ch_data,
                                        linewidth=0.6, color=color, label=ch_name, rasterized=True)
                    visible_any = True
            if visible_any:
                self.result_ax.legend(loc="upper right", fontsize=8)
            self.result_ax.set_xlabel("Время, мсек")
            self.result_ax.set_ylabel("Перемещение, мм")
        elif self.loader.result_df is not None and not self.loader.result_df.empty:
            self.result_ax.plot(self.loader.result_df["Время, мсек"],
                                self.loader.result_df["Перемещение, мм"],
                                linewidth=0.6, color="#2196F3", rasterized=True)
            self.result_ax.set_xlabel("Время, мсек")
            self.result_ax.set_ylabel("Перемещение, мм")
        else:
            self.result_ax.text(0.5, 0.5, "Нет данных",
                                ha="center", va="center", transform=self.result_ax.transAxes,
                                fontsize=12, color="#94a3b8")

        self.result_ax.grid(True, alpha=0.2)

        self.result_fig.tight_layout()
        self.result_canvas.draw()

    def _on_result_motion(self, event):
        tk_canvas = self.result_canvas.get_tk_widget()
        tk_canvas.delete("crosshair")
        if event.inaxes != self.result_ax or event.xdata is None:
            return
        x, y = event.xdata, event.ydata
        px = event.x
        py = self.result_fig.bbox.height - event.y
        w = tk_canvas.winfo_width()
        h = tk_canvas.winfo_height()
        tk_canvas.create_line(px, 0, px, h, fill='#aaaaaa', dash=(4, 4), tags="crosshair")
        tk_canvas.create_line(0, py, w, py, fill='#aaaaaa', dash=(4, 4), tags="crosshair")
        tk_canvas.create_rectangle(px - 28, 1, px + 28, 17,
                                    fill='#ffffcc', outline='#aaaaaa', tags="crosshair")
        tk_canvas.create_text(px, 9, text=f"{x:.3f}", fill='#333333',
                               font=("Segoe UI", 8), tags="crosshair")
        tk_canvas.create_rectangle(w - 68, py - 9, w - 2, py + 9,
                                    fill='#ffffcc', outline='#aaaaaa', tags="crosshair")
        tk_canvas.create_text(w - 5, py, text=f"{y:.3f}", fill='#333333',
                               font=("Segoe UI", 8), anchor='e', tags="crosshair")

    def _on_result_leave(self, event):
        self.result_canvas.get_tk_widget().delete("crosshair")

    # === Deformation analysis methods ===

    def _analyze_deformations(self):
        """Анализ послойных деформаций с использованием данных перемещения от времени."""
        # Показываем пользователю, что анализ начался
        self.status_var.set("Выполнение анализа деформаций...")
        self.deform_status_label.configure(text="Анализ...")
        self.root.update_idletasks()  # Обновляем UI перед началом расчёта
        
        # Проверяем наличие данных: используем result_channels_raw или result_channels
        has_data = False
        if hasattr(self.loader, 'result_channels_raw') and self.loader.result_channels_raw:
            has_data = True
            print(f"[DEBUG] Используем result_channels_raw: {list(self.loader.result_channels_raw.keys())}")
        elif self.loader.result_channels:
            has_data = True
            print(f"[DEBUG] Используем result_channels: {list(self.loader.result_channels.keys())}")
            
        if not has_data or self.loader.dynamics_time is None:
            messagebox.showinfo("Информация", 
                "Сначала загрузите данные динамики и тарировки,\n"
                "затем выполните расчёт для получения данных перемещения.\n\n"
                f"Текущее состояние:\n"
                f"- dynamics_time: {'есть' if self.loader.dynamics_time is not None else 'нет'}\n"
                f"- result_channels_raw: {'есть' if hasattr(self.loader, 'result_channels_raw') and self.loader.result_channels_raw else 'нет'}\n"
                f"- result_channels: {'есть' if self.loader.result_channels else 'нет'}")
            self.status_var.set("Анализ не выполнен: нет данных")
            self.deform_status_label.configure(text="Нет данных для анализа")
            return
        
        try:
            speed_kmh = float(self.deform_speed_var.get())
            threshold_sigma = float(self.deform_threshold_var.get())
        except ValueError:
            messagebox.showerror("Ошибка", "Неверный формат скорости или порога")
            return
        
        # Подготовка данных: время и перемещения по слоям
        time_ms = self.loader.dynamics_time
        
        # Используем result_channels_raw если есть, иначе result_channels
        if hasattr(self.loader, 'result_channels_raw') and self.loader.result_channels_raw:
            channels_data = self.loader.result_channels_raw
        else:
            channels_data = self.loader.result_channels
            
        layer_names = list(channels_data.keys())
        
        # Собираем данные по слоям в массив
        data_list = []
        for ch_name in layer_names:
            ch_data = channels_data[ch_name]
            data_list.append(ch_data)
        
        data = np.column_stack(data_list)
        
        # Создание анализатора
        print(f"[DEBUG] Создание DeformationAnalyzer: time_ms len={len(time_ms)}, data shape={data.shape}, layers={layer_names}")
        self.deformation_analyzer = DeformationAnalyzer(time_ms, data, layer_names)
        
        # Поиск участков деформаций
        print(f"[DEBUG] Поиск участков с порогом σ={threshold_sigma}")
        zones = self.deformation_analyzer.find_zones(threshold_sigma=threshold_sigma)
        self._deformation_zones = zones
        print(f"[DEBUG] Найдено участков: {len(zones) if zones else 0}")
        
        if not zones:
            self.deform_status_label.configure(text="Участки деформаций не найдены")
            messagebox.showinfo("Результат", 
                               f"Участки деформаций не найдены.\n"
                               f"Данные: время={len(time_ms)} точек, слои={len(layer_names)}\n"
                               f"Попробуйте уменьшить порог σ (текущий: {threshold_sigma}).")
            self.status_var.set("Анализ завершён: участки не найдены")
            return
        
        # Создание вкладок для каждого участка
        print(f"[DEBUG] Построение вкладок для {len(zones)} участков")
        self._build_deformation_tabs(speed_kmh)
        
        self.deform_status_label.configure(
            text=f"Найдено участков: {len(zones)}")
        self.status_var.set(f"Анализ деформаций завершён: {len(zones)} участков")

    def _build_deformation_tabs(self, speed_kmh):
        """Создание вкладок для каждого участка деформации."""
        # Очищаем старые вкладки
        while self.deformation_notebook.index("end") != 0:
            self.deformation_notebook.forget(0)
        self._deformation_tabs.clear()
        
        if not self._deformation_zones:
            default_frame = ttk.Frame(self.deformation_notebook)
            self.deformation_notebook.add(default_frame, text="  Нет данных  ")
            lbl = ttk.Label(default_frame, text="Нет данных для отображения",
                           background=PANEL_BG, foreground="#94a3b8",
                           font=("Segoe UI", 10, "italic"))
            lbl.pack(expand=True)
            self._deformation_tabs["Нет данных"] = default_frame
            return
        
        # Создаем вкладки для каждого участка
        print(f"[DEBUG] Создание {len(self._deformation_zones)} вкладок")
        for i, zone_idx in enumerate(range(len(self._deformation_zones))):
            frame = ttk.Frame(self.deformation_notebook)
            tab_name = f"Участок {i + 1}"
            self.deformation_notebook.add(frame, text=f"  {tab_name}  ")
            
            # Вычисляем результаты для участка
            try:
                result = self.deformation_analyzer.zone_result(zone_idx, speed_kmh)
                print(f"[DEBUG] Участок {i+1}: result keys={list(result.keys())}")
                self._deformation_tabs[tab_name] = (zone_idx, result, frame)
                
                # Добавляем информацию об участке
                self._populate_deformation_tab(frame, result, zone_idx, speed_kmh)
            except Exception as e:
                print(f"[ERROR] Ошибка при построении вкладки {tab_name}: {e}")
                import traceback
                traceback.print_exc()
                lbl = ttk.Label(frame, text=f"Ошибка построения графика:\n{e}",
                               foreground="red")
                lbl.pack(expand=True)
                self._deformation_tabs[tab_name] = (zone_idx, None, frame)
        
        # Выбираем первую вкладку
        if self._deformation_zones:
            try:
                first_result = self.deformation_analyzer.zone_result(0, speed_kmh)
                self._current_deformation_zone = 0
            except Exception as e:
                print(f"[ERROR] Ошибка при получении первого результата: {e}")

    def _populate_deformation_tab(self, frame, result, zone_idx, speed_kmh):
        """Заполнение вкладки данными об участке."""
        # График деформаций - занимает всё пространство
        chart_frame = ttk.Frame(frame)
        chart_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        
        fig = Figure(figsize=(8, 5), dpi=100)
        ax = fig.add_subplot(111)
        
        x = result['x']
        defs = result['defs']
        
        # Построение графиков для каждого слоя (переворачиваем знак для правильной ориентации)
        for i in range(self.deformation_analyzer.n_layers):
            layer_name = self.deformation_analyzer.layer_names[i]
            color = CHANNEL_COLORS[i % len(CHANNEL_COLORS)]
            ax.plot(x, -defs[:, i], linewidth=1.5, color=color, label=layer_name)
        
        ax.set_xlabel("Путь, м")
        ax.set_ylabel("Деформация, мм")
        ax.set_title(f"Деформации по слоям (участок {zone_idx + 1})")
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(True, alpha=0.3)
        
        # Добавляем вертикальную линию курсора
        cursor_line = ax.axvline(
            result['largest_x'],
            color="blue",
            linestyle=":",
            linewidth=1.2,
            alpha=0.8,
            visible=False
        )
        
        cursor_points, = ax.plot(
            [], [],
            "o",
            color="black",
            markersize=4,
            visible=False
        )
        
        fig.tight_layout()
        
        canvas = FigureCanvasTkAgg(fig, master=chart_frame)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Toolbar для графика
        toolbar = NavigationToolbar2Tk(canvas, chart_frame)
        toolbar.update()
        toolbar.pack_forget()  # Скрываем тулбар по умолчанию
        
        # Сохраняем ссылки на элементы для интерактивности
        tab_data = {
            "canvas": canvas,
            "fig": fig,
            "ax": ax,
            "vline": cursor_line,
            "cursor_pts": cursor_points,
            "x": x,
            "defs": -defs,  # Перевёрнутые значения для отображения
            "time": result['time'],
            "frozen": False,
            "info_labels": {}
        }
        
        # Подключаем обработчики событий
        canvas.mpl_connect(
            "motion_notify_event",
            lambda event, zidx=zone_idx: self._on_deformation_motion(event, zidx)
        )
        canvas.mpl_connect(
            "button_press_event",
            lambda event, zidx=zone_idx: self._on_deformation_click(event, zidx)
        )
        
        # Сохраняем данные вкладки
        self._deformation_tabs[f"Участок {zone_idx + 1}"] = (zone_idx, result, frame, tab_data)
        
        # Верхняя панель с информацией (добавляем после графика)
        info_frame = ttk.Frame(frame)
        info_frame.pack(fill=tk.X, padx=4, pady=4)
        
        info_text = (
            f"Участок {zone_idx + 1}\n"
            f"Время: {result['t_start']:.2f} — {result['t_end']:.2f} мс\n"
            f"Длительность: {result['duration_ms']:.2f} мс\n"
            f"Путь: {result['x_start']:.3f} — {result['x_end']:.3f} м\n"
            f"Макс. слой: {self.deformation_analyzer.layer_names[result['largest_layer']]}\n"
            f"Макс. значение: {result['largest_value']:.4f} мм"
        )
        
        info_label = ttk.Label(info_frame, text=info_text, 
                               font=("Consolas", 9), justify=tk.LEFT)
        info_label.pack(side=tk.LEFT, padx=4, pady=4)
        
        # Правая панель со значениями ΔY
        delta_frame = ttk.LabelFrame(info_frame, text=" ΔY между слоями ")
        delta_frame.pack(side=tk.RIGHT, padx=4, pady=4)
        
        delta_texts = []
        for i in range(len(result['delta_y_at_largest'])):
            layer1 = self.deformation_analyzer.layer_names[i]
            layer2 = self.deformation_analyzer.layer_names[i + 1]
            delta = result['delta_y_at_largest'][i]
            delta_texts.append(f"{layer1}→{layer2}: {delta:+.4f} мм")
        
        delta_label = ttk.Label(delta_frame, text="\n".join(delta_texts),
                                font=("Consolas", 9), justify=tk.LEFT)
        delta_label.pack(padx=4, pady=4)
        
        # Панель с текущими значениями под курсором
        cursor_panel = ttk.LabelFrame(frame, text=" Значения под курсором ")
        cursor_panel.pack(fill=tk.X, padx=4, pady=4)
        
        cursor_info_frame = ttk.Frame(cursor_panel)
        cursor_info_frame.pack(fill=tk.X, padx=4, pady=4)
        
        # Время и расстояние
        time_lbl = ttk.Label(cursor_info_frame, text=f"Время: — мс", 
                            font=("Consolas", 9))
        time_lbl.pack(side=tk.LEFT, padx=10)
        
        dist_lbl = ttk.Label(cursor_info_frame, text=f"Расстояние: — м", 
                            font=("Consolas", 9))
        dist_lbl.pack(side=tk.LEFT, padx=10)
        
        # Значения по слоям
        values_frame = ttk.Frame(cursor_info_frame)
        values_frame.pack(side=tk.RIGHT)
        
        layer_labels = []
        for i in range(self.deformation_analyzer.n_layers):
            lbl = ttk.Label(values_frame, text=f"—", 
                           font=("Consolas", 9), foreground=CHANNEL_COLORS[i])
            lbl.pack(side=tk.LEFT, padx=5)
            layer_labels.append(lbl)
        
        tab_data["info_labels"] = {
            "time": time_lbl,
            "dist": dist_lbl,
            "layers": layer_labels
        }
        
        # Панель с пиками (скрыта по запросу)
        # peak_frame = ttk.LabelFrame(frame, text=" Пиковые значения ")
        # peak_frame.pack(fill=tk.X, padx=4, pady=4)
        # 
        # peak_info = []
        # for i in range(self.deformation_analyzer.n_layers):
        #     layer_name = self.deformation_analyzer.layer_names[i]
        #     peak_val = result['peak_vals'][i]
        #     peak_t = result['peak_time'][i]
        #     peak_x = result['peak_x'][i]
        #     peak_info.append(f"{layer_name}: {peak_val:+.4f} мм @ {peak_t:.1f} мс ({peak_x:.3f} м)")
        # 
        # peak_label = ttk.Label(peak_frame, text="  |  ".join(peak_info),
        #                        font=("Consolas", 8))
        # peak_label.pack(padx=4, pady=4)
        # 
        # # Информация о временах пиков для расчёта скорости
        # if result['first_two_peak_times'][0] is not None:
        #     t1 = result['first_two_peak_times'][0]
        #     t2 = result['first_two_peak_times'][1]
        #     if t2 is not None:
        #         axis_distance = 0.5  # м (можно вынести в настройки)
        #         dt = t2 - t1  # мс
        #         if dt > 0:
        #             calc_speed = axis_distance / (dt / 1000.0) * 3.6  # км/ч
        #             speed_info = f"Δt между пиками: {dt:.1f} мс → V={calc_speed:.1f} км/ч"
        #             speed_label = ttk.Label(peak_frame, text=speed_info,
        #                                    font=("Consolas", 8), foreground="#059669")
        #             speed_label.pack(padx=4, pady=2)

    def _on_deformation_tab_changed(self, event):
        """Обработчик переключения вкладок участков деформации."""
        try:
            tab_name = self.deformation_notebook.tab(
                self.deformation_notebook.select(), "text").strip()
            if tab_name in self._deformation_tabs:
                data = self._deformation_tabs[tab_name]
                zone_idx = data[0]
                self._current_deformation_zone = zone_idx
                # Сбрасываем заморозку при переключении вкладки
                if len(data) > 3:
                    tab_data = data[3]
                    tab_data["frozen"] = False
                    # Показываем линию на максимальном пике
                    self._update_deformation_cursor(zone_idx, tab_data["x"][len(tab_data["x"])//2])
        except Exception:
            pass
    
    def _on_deformation_motion(self, event, zone_idx):
        """Обработка движения мыши над графиком деформаций."""
        tab_name = f"Участок {zone_idx + 1}"
        if tab_name not in self._deformation_tabs:
            return
        
        data = self._deformation_tabs[tab_name]
        if len(data) <= 3:
            return
        
        tab_data = data[3]
        
        # Если заморожено - не обновляем
        if tab_data.get("frozen", False):
            return
        
        # Проверяем что курсор над осями
        if event.inaxes != tab_data["ax"] or event.xdata is None:
            tab_data["vline"].set_visible(False)
            tab_data["cursor_pts"].set_visible(False)
            tab_data["canvas"].draw_idle()
            return
        
        self._update_deformation_cursor(zone_idx, float(event.xdata))
    
    def _on_deformation_click(self, event, zone_idx):
        """Обработка клика по графику деформаций (фиксация/разморозка курсора)."""
        if event.button != 1:  # Только левая кнопка
            return
        
        tab_name = f"Участок {zone_idx + 1}"
        if tab_name not in self._deformation_tabs:
            return
        
        data = self._deformation_tabs[tab_name]
        if len(data) <= 3:
            return
        
        tab_data = data[3]
        
        if event.inaxes != tab_data["ax"]:
            return
        
        # Переключаем состояние заморозки
        tab_data["frozen"] = not tab_data["frozen"]
        
        if tab_data["frozen"]:
            self.status_var.set("🔒 Курсор зафиксирован")
        else:
            self.status_var.set("Курсор свободен")
        
        # Обновляем позицию если есть данные
        if event.xdata is not None:
            self._update_deformation_cursor(zone_idx, float(event.xdata))
    
    def _update_deformation_cursor(self, zone_idx, x_val):
        """Обновление позиции курсора на графике деформаций."""
        tab_name = f"Участок {zone_idx + 1}"
        if tab_name not in self._deformation_tabs:
            return
        
        data = self._deformation_tabs[tab_name]
        if len(data) <= 3:
            return
        
        tab_data = data[3]
        result = data[1]
        
        x = tab_data["x"]
        defs = tab_data["defs"]
        time_arr = tab_data["time"]
        
        if len(x) == 0:
            return
        
        # Находим ближайший индекс
        idx = int(np.clip(np.searchsorted(x, x_val), 0, len(x) - 1))
        
        xv = float(x[idx])
        vals = defs[idx, :]
        
        # Обновляем вертикальную линию
        tab_data["vline"].set_xdata([xv, xv])
        tab_data["vline"].set_visible(True)
        
        # Обновляем точки на кривых
        tab_data["cursor_pts"].set_data([xv] * len(vals), vals)
        tab_data["cursor_pts"].set_visible(True)
        
        # Перерисовываем график
        tab_data["canvas"].draw_idle()
        
        # Обновляем панель с информацией
        info_labels = tab_data.get("info_labels", {})
        if info_labels:
            time_lbl = info_labels.get("time")
            dist_lbl = info_labels.get("dist")
            layer_labels = info_labels.get("layers", [])
            
            if time_lbl:
                time_lbl.config(text=f"Время: {time_arr[idx]:.0f} мс")
            if dist_lbl:
                dist_lbl.config(text=f"Расстояние: {xv:.3f} м")
            
            for i, lbl in enumerate(layer_labels):
                if i < len(vals):
                    lbl.config(text=f"{vals[i]:+.3f}")

    # === Peak selection methods ===

    def _apply_manual_zero(self):
        pass  # Removed - no longer used

    def _reset_manual_zero(self):
        pass  # Removed - no longer used

    def _reset_peak_selection(self):
        """Сброс выбранного диапазона и возврат к автоматическому определению."""
        if self._peak_selection_rect is not None:
            self._peak_selection_rect.remove()
            self._peak_selection_rect = None
        self._disconnect_peak_handlers()
        self._peak_selection_active = False
        self._peak_range = None
        # Пересчитываем пики с использованием автоматических диапазонов
        self._update_auto_peak_ranges()
        self.status_var.set("Диапазон сброшен")

    def _disconnect_peak_handlers(self):
        """Отключение обработчиков событий выделения диапазона."""
        if self._peak_press_id is not None:
            self.result_canvas.mpl_disconnect(self._peak_press_id)
            self._peak_press_id = None
        if self._peak_release_id is not None:
            self.result_canvas.mpl_disconnect(self._peak_release_id)
            self._peak_release_id = None

    def _update_auto_peak_ranges(self):
        """Автоматическое определение диапазонов между нулями и обновление вкладок (отключено)."""
        pass  # Отключено вместе с панелью пиковых значений

    def _update_peak_range_tabs(self, ranges):
        """Обновление вкладок для каждого диапазона (отключено)."""
        pass  # Отключено вместе с панелью пиковых значений

    def _on_peak_range_tab_changed(self, event):
        """Обработчик переключения вкладок диапазонов (отключено)."""
        pass  # Отключено вместе с панелью пиковых значений

    def _start_peak_selection(self):
        if not self.loader.result_channels:
            messagebox.showinfo("Информация", "Сначала загрузите данные и выполните расчёт")
            return
        self._disconnect_peak_handlers()
        self._peak_selection_active = True
        self._peak_selection_start = None
        if self._peak_selection_rect is not None:
            self._peak_selection_rect.remove()
            self._peak_selection_rect = None
            self.result_canvas.draw()
        self._peak_press_id = self.result_canvas.mpl_connect(
            'button_press_event', self._on_peak_press)
        self._peak_release_id = self.result_canvas.mpl_connect(
            'button_release_event', self._on_peak_release)
        self.status_var.set("Выберите диапазон на графике (кликните и перетащите)")

    def _on_peak_press(self, event):
        if not self._peak_selection_active:
            return
        if event.inaxes != self.result_ax:
            return
        self._peak_selection_start = event.xdata
        if self._peak_selection_rect is not None:
            self._peak_selection_rect.remove()
            self._peak_selection_rect = None
            self.result_canvas.draw()

    def _on_peak_release(self, event):
        if not self._peak_selection_active:
            return
        if event.inaxes != self.result_ax or self._peak_selection_start is None:
            return
        x_start = self._peak_selection_start
        x_end = event.xdata
        if x_start > x_end:
            x_start, x_end = x_end, x_start
        if abs(x_end - x_start) < 1:
            return

        self._peak_selection_rect = self.result_ax.axvspan(
            x_start, x_end, alpha=0.25, color='#fbbf24', zorder=0)
        self.result_canvas.draw()

        self.result_canvas.mpl_disconnect(self._peak_press_id)
        self.result_canvas.mpl_disconnect(self._peak_release_id)
        self._peak_selection_active = False

        self._calculate_and_draw_peaks(x_start, x_end)
        self._peak_range = (x_start, x_end)
        self.status_var.set(f"Диапазон: {x_start:.1f} — {x_end:.1f} мс")

    def _calculate_and_draw_peaks(self, x_start, x_end):
        if not self.loader.result_channels or self.loader.dynamics_time is None:
            return
        baselines = self.loader.channel_baselines or self.loader.channel_mins
        if self.loader.zero_point is None or baselines is None:
            return

        time = self.loader.dynamics_time
        mask = (time >= x_start) & (time <= x_end)
        zero_point = self.loader.zero_point
        DEVIATION_THRESHOLD = 0.0001  # mm

        names = []
        deviations = []
        peak_values = []
        for ch_name, ch_data in self.loader.result_channels.items():
            if ch_name not in baselines:
                continue
            ch_in_range = ch_data[mask]
            if len(ch_in_range) == 0:
                continue
            baseline = baselines[ch_name]
            # Для центрированных данных deviation считается от нуля (т.к. данные уже центрированы)
            max_in_range = float(np.max(ch_in_range))
            deviation = max_in_range  # Данные уже центрированы относительно своего baseline
            if deviation < DEVIATION_THRESHOLD:
                continue
            names.append(ch_name)
            deviations.append(deviation)
            peak_values.append(max_in_range)

        zero_mode = "вручную" if self.loader.manual_zero_point is not None else "авто"
        auto_zero = self.loader.auto_zero_point
        auto_text = f" (авто: {auto_zero:.3f})" if auto_zero is not None and zero_mode == "вручную" else ""

        if not names:
            self.peak_ax.clear()
            self.peak_ax.set_title("Профиль пиков")
            self.peak_ax.text(0.5, 0.5, "Значимых отклонений\nне обнаружено",
                              ha="center", va="center", transform=self.peak_ax.transAxes,
                              fontsize=11, color="#94a3b8", style="italic")
            self.peak_ax.set_axis_off()
            self.peak_info_label.configure(
                text=f"Ноль ({zero_mode}): {zero_point:.3f} мм{auto_text} | Порог: {DEVIATION_THRESHOLD} мм")
            self.peak_fig.tight_layout()
            self.peak_canvas.draw()
            return

        deltas = [abs(peak_values[i] - peak_values[i - 1]) for i in range(1, len(peak_values))]

        # Draw peak chart
        self.peak_ax.clear()
        self.peak_ax.set_title("Профиль пиков — Прогиб")

        n = len(names)
        max_dev = max(deviations)

        y_zero = 0.0
        self.peak_ax.axhline(y=y_zero, color='#94a3b8', linestyle='-', alpha=0.4, linewidth=2, zorder=1)
        self.peak_ax.text(0, y_zero + 0.15, f"Ноль: {zero_point:.3f} мм ({zero_mode})",
                          fontsize=8, color='#64748b', ha='center', va='bottom')

        for i, (name, dev, peak_val) in enumerate(zip(names, deviations, peak_values)):
            y_point = -(i + 1) * 0.8
            t = np.linspace(0, 1, 100)
            y_curve = y_point + (y_zero - y_point) * t
            x_right = dev * np.sqrt(t)
            x_left = -dev * np.sqrt(t)

            self.peak_ax.fill_betweenx(y_curve, x_left, x_right,
                                        alpha=0.10, color='#2563eb', zorder=2)
            self.peak_ax.plot(x_right, y_curve, color='#2563eb', linewidth=2.5, alpha=0.9, zorder=3)
            self.peak_ax.plot(x_left, y_curve, color='#2563eb', linewidth=2.5, alpha=0.9, zorder=3)
            self.peak_ax.plot(0, y_point, 'o', color='#dc2626', markersize=10,
                              markeredgecolor='white', markeredgewidth=2, zorder=5)

            delta_text = ""
            if i > 0:
                delta_text = f"  Δ={deltas[i - 1]:.3f} мм"
            self.peak_ax.annotate(
                f"  {name}: {dev:.3f} мм (пик {peak_val:.3f}){delta_text}",
                xy=(0, y_point), xytext=(max_dev * 0.15, y_point),
                fontsize=8, va='center', color='#1e293b',
                bbox=dict(boxstyle='round,pad=0.2',
                          facecolor='#fef3c7', edgecolor='#f59e0b',
                          alpha=0.9), zorder=4)

            if i > 0:
                y_prev = -(i) * 0.8
                y_mid = (y_point + y_prev) / 2
                self.peak_ax.annotate(
                    '', xy=(max_dev * 0.55, y_prev), xytext=(max_dev * 0.55, y_point),
                    arrowprops=dict(arrowstyle='<->', color='#059669', lw=1.5),
                    zorder=4)
                self.peak_ax.text(max_dev * 0.62, y_mid,
                                  f"Δ {deltas[i - 1]:.3f} мм",
                                  fontsize=7, color='#059669', va='center', fontweight='bold')

        self.peak_ax.set_xlim(-max_dev * 1.3, max_dev * 1.8)
        self.peak_ax.set_xlabel("Отклонение от нуля, мм")
        self.peak_ax.grid(True, axis='x', alpha=0.2)

        delta_parts = [f"{d:.3f} мм" for d in deltas]
        delta_str = " | Δ: " + ", ".join(delta_parts) if delta_parts else ""
        info = (f"Ноль ({zero_mode}): {zero_point:.3f} мм{auto_text} | "
                f"Порог: {DEVIATION_THRESHOLD} мм | Каналов: {n}{delta_str}")
        self.peak_info_label.configure(text=info)

        self.peak_fig.tight_layout()
        self.peak_canvas.draw()

    def _clear_peak_chart(self):
        self.peak_ax.clear()
        self.peak_ax.set_title("Профиль пиков")
        self.peak_ax.text(0.5, 0.5, "Выберите диапазон\nна графике",
                          ha="center", va="center", transform=self.peak_ax.transAxes,
                          fontsize=11, color="#94a3b8", style="italic")
        self.peak_ax.set_axis_off()
        self.peak_info_label.configure(text="")
        self._peak_range = None
        if self._peak_selection_rect is not None:
            self._peak_selection_rect.remove()
            self._peak_selection_rect = None
            self.result_canvas.draw()
        self.peak_fig.tight_layout()
        self.peak_canvas.draw()

    def _draw_raw_chart(self):
        self.raw_ax.clear()
        self.raw_ax.set_title("Динамика")

        if self.loader.dynamics_channels:
            visible_any = False
            for i, (ch_name, ch_data) in enumerate(self.loader.dynamics_channels.items()):
                visible = True
                if hasattr(self, '_channel_vars') and ch_name in self._channel_vars:
                    visible = self._channel_vars[ch_name].get()
                if visible:
                    color = CHANNEL_COLORS[i % len(CHANNEL_COLORS)]
                    self.raw_ax.plot(self.loader.dynamics_time, ch_data,
                                     linewidth=0.6, color=color, label=ch_name, rasterized=True)
                    visible_any = True
            if visible_any:
                self.raw_ax.legend(loc="upper right", fontsize=8)
            self.raw_ax.set_xlabel("Время, мсек")
            self.raw_ax.set_ylabel("Датчик Холла")
        elif self.loader.source_data is not None and not self.loader.source_data.empty:
            src_cols = list(self.loader.source_data.columns)
            src_time = src_cols[0]
            src_val = src_cols[1] if len(src_cols) > 1 else src_cols[0]
            self.raw_ax.plot(self.loader.source_data[src_time],
                             self.loader.source_data[src_val],
                             linewidth=0.6, color="#4CAF50", rasterized=True)
            self.raw_ax.set_xlabel(src_time)
            self.raw_ax.set_ylabel(src_val)
        else:
            self.raw_ax.text(0.5, 0.5, "Нет данных",
                             ha="center", va="center", transform=self.raw_ax.transAxes,
                             fontsize=12, color="#94a3b8")

        self.raw_ax.grid(True, alpha=0.2)
        self.raw_fig.tight_layout()
        self.raw_canvas.draw()

        self._draw_disp_chart()

    def _plot_calib_rising_curve(self, ax, disp, tug, color, label):
        """Рисует тарировку: восходящий участок ярко, скат — бледно."""
        disp = np.asarray(disp, dtype=float)
        tug = np.asarray(tug, dtype=float)
        min_idx, peak_idx = self.calculator._find_rising_indices(tug)

        if min_idx > 0:
            ax.plot(disp[:min_idx + 1], tug[:min_idx + 1],
                    color=color, linewidth=0.6, alpha=0.25)
        if peak_idx < len(disp) - 1:
            ax.plot(disp[peak_idx:], tug[peak_idx:],
                    color=color, linewidth=0.6, alpha=0.25, linestyle='--')
        ax.plot(disp[min_idx:peak_idx + 1], tug[min_idx:peak_idx + 1],
                color=color, linewidth=1.4, label=label)
        ax.plot(disp[min_idx], tug[min_idx], 'v', color=color, markersize=5, alpha=0.85)
        ax.plot(disp[peak_idx], tug[peak_idx], '^', color=color, markersize=5, alpha=0.85)

    def _draw_disp_chart(self, draw_magnet=True):
        self.disp_ax.clear()
        self.disp_ax.set_title("Тарировка")

        if self.loader.per_layer_calib:
            visible_any = False
            color_idx = 0
            for ch_name, cal in self.loader.per_layer_calib.items():
                visible = True
                if hasattr(self, '_channel_vars') and ch_name in self._channel_vars:
                    visible = self._channel_vars[ch_name].get()
                if visible:
                    for tug_name, tug_vals in cal["tug"].items():
                        color = CHANNEL_COLORS[color_idx % len(CHANNEL_COLORS)]
                        label = f"{ch_name} — {tug_name}"
                        self._plot_calib_rising_curve(
                            self.disp_ax, cal["disp"], tug_vals, color, label)
                        color_idx += 1
                    info = self.loader._per_layer_calib_info.get(ch_name)
                    if info:
                        self.disp_ax.axvline(info["range_left"], color="#ef4444",
                                             linewidth=1.0, linestyle="--", alpha=0.6)
                        self.disp_ax.axvline(info["range_right"], color="#ef4444",
                                             linewidth=1.0, linestyle="--", alpha=0.6)
                    visible_any = True
            if visible_any:
                self.disp_ax.legend(loc="upper right", fontsize=7)
            self.disp_ax.set_xlabel("мм")
            self.disp_ax.set_ylabel("Датчик Холла")
        elif self.loader.calib_channels and self.loader.calib_disp is not None:
            visible_any = False
            for i, (ch_name, ch_data) in enumerate(self.loader.calib_channels.items()):
                visible = True
                if hasattr(self, '_channel_vars') and ch_name in self._channel_vars:
                    visible = self._channel_vars[ch_name].get()
                if visible:
                    color = CHANNEL_COLORS[i % len(CHANNEL_COLORS)]
                    self._plot_calib_rising_curve(
                        self.disp_ax, self.loader.calib_disp, ch_data, color, ch_name)
                    visible_any = True
            info = self.loader._global_calib_info
            if info:
                self.disp_ax.axvline(info["range_left"], color="#ef4444",
                                     linewidth=1.0, linestyle="--", alpha=0.6)
                self.disp_ax.axvline(info["range_right"], color="#ef4444",
                                     linewidth=1.0, linestyle="--", alpha=0.6)
            elif self.loader._overlap_range:
                rl, rr = self.loader._overlap_range
                self.disp_ax.axvline(rl, color="#ef4444", linewidth=1.0, linestyle="--", alpha=0.6)
                self.disp_ax.axvline(rr, color="#ef4444", linewidth=1.0, linestyle="--", alpha=0.6)
            if visible_any:
                self.disp_ax.legend(loc="upper right", fontsize=8)
            self.disp_ax.set_xlabel("мм")
            self.disp_ax.set_ylabel("Датчик Холла")
        elif self.loader.calib_data is not None and not self.loader.calib_data.empty:
            cal_cols = list(self.loader.calib_data.columns)
            cal_disp = cal_cols[0]
            cal_val = cal_cols[1] if len(cal_cols) > 1 else cal_cols[0]
            self.disp_ax.plot(self.loader.calib_data[cal_disp],
                              self.loader.calib_data[cal_val],
                              linewidth=0.6, color="#4CAF50", rasterized=True)
            self.disp_ax.set_xlabel(cal_disp)
            self.disp_ax.set_ylabel(cal_val)
        else:
            self.disp_ax.text(0.5, 0.5, "Нет данных",
                              ha="center", va="center", transform=self.disp_ax.transAxes,
                              fontsize=12, color="#94a3b8")

        for rl, rr in self._calib_range_highlights.values():
            self.disp_ax.axvspan(rl, rr, alpha=0.1, color='#fbbf24', zorder=0)

        self.disp_ax.grid(True, alpha=0.2)
        self.disp_fig.tight_layout()
        self.disp_canvas.draw()

        if draw_magnet:
            self._draw_magnet_chart()

    def _draw_magnet_chart(self):
        self.magnet_ax.clear()
        self.magnet_ax.set_title("Положение магнита — тарировка")

        if self.loader.per_layer_calib:
            visible_any = False
            all_cals = list(self.loader.per_layer_calib.values())
            all_disp = np.concatenate([c["disp"] for c in all_cals])
            all_tug_vals = []
            for c in all_cals:
                for v in c["tug"].values():
                    all_tug_vals.append(v)
            all_tugs = np.concatenate(all_tug_vals)
            self.magnet_ax.set_xlim(all_disp.min(), all_disp.max())
            y_margin = (all_tugs.max() - all_tugs.min()) * 0.05
            self.magnet_ax.set_ylim(all_tugs.min() - y_margin, all_tugs.max() + y_margin)

            color_idx = 0
            for ch_name, cal in self.loader.per_layer_calib.items():
                visible = True
                if hasattr(self, '_channel_vars') and ch_name in self._channel_vars:
                    visible = self._channel_vars[ch_name].get()
                if not visible:
                    continue
                visible_any = True

                layer_ix = self.loader._per_layer_intersections.get(ch_name, {})
                selected = self.loader._per_layer_selected_sensor.get(ch_name)
                magnet_x = self.loader._per_layer_magnet_x.get(ch_name)

                for tug_name, tug_vals in cal["tug"].items():
                    color = CHANNEL_COLORS[color_idx % len(CHANNEL_COLORS)]
                    is_sel = (tug_name == selected)
                    lw = 2.2 if is_sel else 0.6
                    alpha = 1.0 if is_sel else 0.4
                    suffix = " *" if is_sel else ""
                    label = f"{ch_name} — {tug_name}{suffix}"
                    self.magnet_ax.plot(cal["disp"], tug_vals,
                                        linewidth=lw, color=color, alpha=alpha, label=label, rasterized=(not is_sel))

                    ix_info = layer_ix.get(tug_name, {})
                    mid_y = ix_info.get('mid_y')
                    if mid_y is None:
                        mid_idx = len(tug_vals) // 2
                        mid_y = tug_vals[mid_idx]
                    x_pts = ix_info.get('x_points', np.array([]))

                    self.magnet_ax.axhline(y=mid_y, color=color, linewidth=0.8,
                                           linestyle='--', alpha=0.5)
                    if len(x_pts) > 0:
                        self.magnet_ax.plot(x_pts, np.full_like(x_pts, mid_y), 'o',
                                            color=color, markersize=5,
                                            markeredgecolor='black', markeredgewidth=0.6, zorder=5)
                    color_idx += 1

                if magnet_x is not None:
                    y_vals = [np.interp(magnet_x, cal["disp"], tv) for tv in cal["tug"].values()]
                    y_mark = float(np.mean(y_vals)) if y_vals else 0
                    self.magnet_ax.axvline(x=magnet_x, color='red', linewidth=2.0,
                                           linestyle='-', alpha=0.8, zorder=6)
                    self.magnet_ax.plot(magnet_x, y_mark, 'v', color='red',
                                        markersize=9, zorder=7)
                    sel_txt = f", {selected}" if selected else ""
                    self.magnet_ax.annotate(
                        f"{ch_name}: X={magnet_x:.1f} мм{sel_txt}",
                        xy=(magnet_x, y_mark), xytext=(5, 10),
                        textcoords='offset points', fontsize=8,
                        color='red', fontweight='bold')
            if visible_any:
                self.magnet_ax.legend(loc="upper right", fontsize=7)
            self.magnet_ax.set_xlabel("мм")
            self.magnet_ax.set_ylabel("Датчик Холла")
        elif self.loader.calib_channels and self.loader.magnet_position is not None:
            disp = self.loader.calib_disp

            x_min, x_max = disp.min(), disp.max()
            all_tugs = np.concatenate(list(self.loader.calib_channels.values()))
            y_min, y_max = all_tugs.min(), all_tugs.max()
            y_margin = (y_max - y_min) * 0.05
            self.magnet_ax.set_xlim(x_min, x_max)
            self.magnet_ax.set_ylim(y_min - y_margin, y_max + y_margin)

            selected = getattr(self.loader, '_selected_calib_auto', None)

            for i, (ch_name, ch_data) in enumerate(self.loader.calib_channels.items()):
                visible = True
                if hasattr(self, '_channel_vars') and ch_name in self._channel_vars:
                    visible = self._channel_vars[ch_name].get()
                if not visible:
                    continue

                color = CHANNEL_COLORS[i % len(CHANNEL_COLORS)]
                is_selected = (ch_name == selected)

                lw = 2.5 if is_selected else 0.6
                alpha = 1.0 if is_selected else 0.4
                label = f"{ch_name} *" if is_selected else ch_name
                self.magnet_ax.plot(disp, ch_data, linewidth=lw, color=color, alpha=alpha, label=label, rasterized=(not is_selected))

                if ch_name in self.loader._magnet_intersections:
                    info = self.loader._magnet_intersections[ch_name]
                    mid_y = info['mid_y']
                    x_pts = info['x_points']

                    self.magnet_ax.axhline(y=mid_y, color=color, linewidth=0.8, linestyle='--', alpha=0.5)

                    self.magnet_ax.plot(x_pts, np.full_like(x_pts, mid_y), 'o',
                                        color=color, markersize=6, markeredgecolor='black',
                                        markeredgewidth=0.8, zorder=5)

            mag_x = self.loader._magnet_x
            if mag_x is not None:
                self.magnet_ax.axvline(x=mag_x, color='red', linewidth=2.0, linestyle='-',
                                       label=f"Магнит X={mag_x:.1f}")

                y_lo, y_hi = self.magnet_ax.get_ylim()
                y_mark = y_lo + (y_hi - y_lo) * 0.03
                self.magnet_ax.plot(mag_x, y_mark, 'v', color='red', markersize=9, zorder=6)

            self.magnet_ax.legend(loc="upper right", fontsize=7)
            self.magnet_ax.set_xlabel("мм")
            self.magnet_ax.set_ylabel("Датчик Холла")
        else:
            self.magnet_ax.text(0.5, 0.5, "Нет данных",
                                ha="center", va="center", transform=self.magnet_ax.transAxes,
                                fontsize=12, color="#94a3b8")

        self.magnet_ax.grid(True, alpha=0.2)
        self.magnet_fig.tight_layout()
        self.magnet_canvas.draw()

    def _on_raw_tab_changed(self, event):
        tab_idx = self.raw_notebook.index(self.raw_notebook.select())
        self.raw_toolbar.pack_forget()
        self.disp_toolbar.pack_forget()
        self.magnet_toolbar.pack_forget()
        if tab_idx == 0:
            self.raw_toolbar.pack(fill=tk.X, expand=True)
            self.raw_toolbar.update()
        elif tab_idx == 1:
            self.disp_toolbar.pack(fill=tk.X, expand=True)
            self.disp_toolbar.update()
        else:
            self.magnet_toolbar.pack(fill=tk.X, expand=True)
            self.magnet_toolbar.update()

    def _on_source_tab_changed(self, event):
        try:
            tab_idx = self.source_notebook.index(self.source_notebook.select())
            self._selected_source_layer = list(self._source_tabs.keys())[tab_idx]
        except (tk.TclError, IndexError):
            self._selected_source_layer = None
        self._update_calib_notebook_for_layer()
        self._draw_disp_chart()
        self._draw_magnet_chart()
        # Обновляем автоматические диапазоны для пиков при переключении слоя
        self._update_auto_peak_ranges()

    def _update_calib_notebook_for_layer(self):
        for t in self._calib_tabs.values():
            self.calib_notebook.forget(t)
        self._calib_tabs.clear()

        layer = self._selected_source_layer
        if not layer or layer not in self.loader.per_layer_calib:
            frame = ttk.Frame(self.calib_notebook)
            self._calib_tabs["Нет данных"] = frame
            self.calib_notebook.add(frame, text="  Нет данных  ")
            lbl = ttk.Label(frame, text="Тарировка не загружена для этого слоя",
                            background=PANEL_BG, foreground="#94a3b8",
                            font=("Segoe UI", 11, "italic"))
            lbl.pack(expand=True)
            return

        cal = self.loader.per_layer_calib[layer]
        frame = ttk.Frame(self.calib_notebook)
        self._calib_tabs[layer] = frame
        self.calib_notebook.add(frame, text=f"  {layer}  ")
        tree = self._make_tree(frame)
        data = {"Перемещение, мм": cal["disp"]}
        for tug_name, tug_vals in cal["tug"].items():
            data[tug_name] = tug_vals
        df = pd.DataFrame(data)
        self._populate_tree(tree, df)

    def load_temperature(self):
        path = filedialog.askopenfilename(
            title="Выберите файл Температуры (CSV/XLSX)",
            filetypes=[("Все файлы", "*.csv *.xlsx"), ("CSV файлы", "*.csv"), ("Excel файлы", "*.xlsx")]
        )
        if not path:
            return
        try:
            self.status_var.set("Загрузка температур...")
            
            # Мгновенная загрузка без блокировки UI
            # Не создаём новый DataLoader, используем существующий
            if path.lower().endswith('.xlsx'):
                self.loader.load_temperature_xlsx(path)
            else:
                self.loader.load_temperature_csv(path)
            self._temp_file_path = Path(path)
            
            # Обновляем UI через after() чтобы не блокировать интерфейс
            self.root.after(0, self._finalize_temperature_load)
        except Exception as e:
            messagebox.showerror("Ошибка загрузки", str(e))
            self.status_var.set("Ошибка загрузки")
    
    def _finalize_temperature_load(self):
        """Финализация загрузки температур в главном потоке."""
        try:
            self.global_notebook.select(self.tab_temp)

            self._populate_tree(self.temp_tree, self._make_temp_df())
            self._update_temp_channel_toggles()
            self._draw_temp_chart()
            self._update_temp_stats()

            self.file_label.configure(text=f"Температуры: {self._temp_file_path.name}")
            n_ch = len(self.loader.temp_channels) if self.loader.temp_channels else 0
            self.status_var.set(f"Загружены температуры: {self._temp_file_path.name} ({n_ch} каналов)")
            self.stats_var.set(f"Температуры: {n_ch} каналов  |  {len(self.loader.temp_time)} точек")
        except Exception as e:
            messagebox.showerror("Ошибка загрузки", str(e))
            self.status_var.set("Ошибка загрузки")

    def _make_temp_df(self):
        if self.loader.temp_data is None or self.loader.temp_channels is None:
            return pd.DataFrame()
        cols = {"Дата": self.loader.temp_time}
        for ch_name, ch_vals in self.loader.temp_channels.items():
            cols[ch_name] = ch_vals
        return pd.DataFrame(cols)

    def _update_temp_channel_toggles(self):
        for w in self.temp_toggle_frame.winfo_children():
            w.destroy()
        if not self.loader.temp_channels:
            return

        ttk.Label(self.temp_toggle_frame, text="Слои:", background=BG,
                  font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(4, 4))

        self._temp_channel_vars = {}
        for i, ch_name in enumerate(self.loader.temp_channels.keys()):
            var = tk.BooleanVar(value=True)
            self._temp_channel_vars[ch_name] = var
            color = CHANNEL_COLORS[i % len(CHANNEL_COLORS)]
            cb = tk.Checkbutton(self.temp_toggle_frame, text=ch_name, variable=var,
                                bg=BG, fg=color, selectcolor=BG,
                                activebackground=BG, activeforeground=color,
                                font=("Segoe UI", 9, "bold"),
                                command=self._draw_temp_chart)
            cb.pack(side=tk.LEFT, padx=2)

    def _draw_temp_chart(self):
        self.temp_ax.clear()
        self.temp_ax.set_title("Температура")

        if self.loader.temp_channels:
            visible_any = False
            for i, (ch_name, ch_data) in enumerate(self.loader.temp_channels.items()):
                visible = True
                if hasattr(self, '_temp_channel_vars') and ch_name in self._temp_channel_vars:
                    visible = self._temp_channel_vars[ch_name].get()
                if visible:
                    color = CHANNEL_COLORS[i % len(CHANNEL_COLORS)]
                    self.temp_ax.plot(self.loader.temp_time, ch_data,
                                      linewidth=0.8, color=color, label=ch_name)
                    visible_any = True
            if visible_any:
                self.temp_ax.legend(loc="upper right", fontsize=8)
            self.temp_ax.set_xlabel("Дата")
            self.temp_ax.set_ylabel("Температура, °C")
        else:
            self.temp_ax.text(0.5, 0.5, "Нет данных",
                              ha="center", va="center", transform=self.temp_ax.transAxes,
                              fontsize=12, color="#94a3b8")

        self.temp_ax.grid(True, alpha=0.3)
        self.temp_fig.autofmt_xdate()
        self.temp_fig.tight_layout()
        self.temp_canvas.draw()

    def _update_temp_stats(self):
        self.temp_stats_text.delete("1.0", tk.END)
        if self.loader.temp_channels is None or not self.loader.temp_channels:
            self.temp_stats_text.insert(tk.END, "Нет данных")
            return
        lines = []
        lines.append(f"Файл: {self._temp_file_path.name if self._temp_file_path else '—'}")
        lines.append(f"Точек: {len(self.loader.temp_time)}")
        lines.append(f"Слоев: {len(self.loader.temp_channels)}")
        lines.append("")
        for ch_name, ch_data in self.loader.temp_channels.items():
            mn = np.min(ch_data)
            mx = np.max(ch_data)
            avg = np.mean(ch_data)
            lines.append(f"{ch_name}:  min={mn:.1f}  max={mx:.1f}  avg={avg:.1f} °C")
        self.temp_stats_text.insert(tk.END, "\n".join(lines))

    def save_file(self):
        if self.loader.result_df is None or self.loader.result_df.empty:
            messagebox.showwarning("Внимание", "Нет данных для сохранения. Сначала выполните расчёт.")
            return

        ts = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        if self._file_path:
            stem = self._file_path.stem
        else:
            stem = "Результат"
        default_name = f"{stem}_результат_{ts}.xlsx"

        path = filedialog.asksaveasfilename(
            title="Сохранить результат",
            defaultextension=".xlsx",
            filetypes=[("Excel файлы", "*.xlsx")],
            initialfile=default_name
        )
        if not path:
            return

        try:
            self.status_var.set("Сохранение...")
            self.root.update_idletasks()

            wb_out = openpyxl.Workbook()
            ws_out = wb_out.active
            ws_out.title = "Результат"

            # Write all dynamics channels starting from column B
            dyn_col = 2  # column B (1-based)
            if self.loader.dynamics_channels:
                for ch_name, ch_data in self.loader.dynamics_channels.items():
                    ws_out.cell(row=2, column=dyn_col, value=ch_name)
                    for i, val in enumerate(ch_data):
                        ws_out.cell(row=i + 3, column=1, value=self.loader.dynamics_time[i] if i < len(self.loader.dynamics_time) else None)
                        ws_out.cell(row=i + 3, column=dyn_col, value=val)
                    dyn_col += 1
            else:
                ws_out.cell(row=2, column=dyn_col, value="Слои")
                for i, (_, row) in enumerate(self.loader.source_data.iterrows()):
                    ws_out.cell(row=i + 3, column=1, value=row.iloc[0])
                    ws_out.cell(row=i + 3, column=dyn_col, value=row.iloc[1])
                dyn_col += 1

            # Section header for dynamics (col 1)
            ws_out.cell(row=1, column=1, value="Динамика в тугриках")
            ws_out.cell(row=2, column=1, value="Время, мсек")

            # Calibration data starts after dynamics channels
            cal_start = dyn_col
            cal_disp_name = "Перемещение, мм"
            if self.loader.calib_data is not None and not self.loader.calib_data.empty:
                cal_cols = list(self.loader.calib_data.columns)
                cal_disp_name = cal_cols[0]

            ws_out.cell(row=1, column=cal_start, value="Тарировка")
            ws_out.cell(row=2, column=cal_start, value=cal_disp_name)

            # Write displacement column
            if self.loader.calib_data is not None:
                for i, (_, row) in enumerate(self.loader.calib_data.iterrows()):
                    ws_out.cell(row=i + 3, column=cal_start, value=row[cal_disp_name])

            # Write all calibration channels
            cal_ch_col = cal_start + 1
            if self.loader.calib_channels:
                for ch_name, ch_data in self.loader.calib_channels.items():
                    ws_out.cell(row=2, column=cal_ch_col, value=ch_name)
                    for i, val in enumerate(ch_data):
                        ws_out.cell(row=i + 3, column=cal_ch_col, value=val)
                    cal_ch_col += 1
            elif self.loader.calib_data is not None and len(cal_cols) > 1:
                cal_val_name = cal_cols[1]
                ws_out.cell(row=2, column=cal_ch_col, value=cal_val_name)
                for i, (_, row) in enumerate(self.loader.calib_data.iterrows()):
                    ws_out.cell(row=i + 3, column=cal_ch_col, value=row[cal_val_name])
                cal_ch_col += 1

            # Result data starts after calibration channels
            res_start = cal_ch_col

            # Result data
            ws_out.cell(row=1, column=res_start, value="Динамика в мм")
            ws_out.cell(row=2, column=res_start, value="Время, мсек")
            res_col = res_start + 1

            if self.loader.result_channels:
                for ch_name, ch_data in self.loader.result_channels.items():
                    ws_out.cell(row=2, column=res_col, value=ch_name)
                    for i, val in enumerate(ch_data):
                        ws_out.cell(row=i + 3, column=res_start, value=self.loader.result_df.iloc[i, 0] if i < len(self.loader.result_df) else None)
                        ws_out.cell(row=i + 3, column=res_col, value=val)
                    res_col += 1
            else:
                ws_out.cell(row=2, column=res_col, value="Перемещение, мм")
                for i, (_, row) in enumerate(self.loader.result_df.iterrows()):
                    ws_out.cell(row=i + 3, column=res_start, value=row["Время, мсек"])
                    ws_out.cell(row=i + 3, column=res_col, value=row["Перемещение, мм"])

            for col, w in {"A": 15, "B": 12, "D": 16, "E": 12, "S": 15, "T": 16}.items():
                ws_out.column_dimensions[col].width = w

            wb_out.save(path)
            wb_out.close()
            self.status_var.set(f"Сохранено: {Path(path).name}")
        except Exception as e:
            messagebox.showerror("Ошибка сохранения", str(e))
            self.status_var.set("Ошибка сохранения")


def main():
    root = tk.Tk()
    app = DinamikaApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
