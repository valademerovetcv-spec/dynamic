"""Вкладка Деформации - основной интерфейс."""
import tkinter as tk
from tkinter import ttk
import windnd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure


class DeformationsTab:
    """Класс вкладки Деформации."""
    
    def __init__(self, parent, app_instance):
        self.parent = parent
        self.app = app_instance
        self._build_ui()
    
    def _build_ui(self):
        """Создает интерфейс вкладки Деформации."""
        main_paned = ttk.PanedWindow(self.parent, orient=tk.VERTICAL)
        main_paned.pack(fill=tk.BOTH, expand=True)

        top_paned = ttk.PanedWindow(main_paned, orient=tk.HORIZONTAL)
        main_paned.add(top_paned, weight=1)

        # Левая панель - Исходные данные динамики
        left_frame = ttk.LabelFrame(top_paned, text=" Динамика — Исходные данные (Drop CSV/XLSX)")
        top_paned.add(left_frame, weight=3)
        self._build_dynamics_panel(left_frame)

        # Правая панель - Тарировка
        right_frame = ttk.LabelFrame(top_paned, text=" Тарировка — Калибровочная кривая (Drop CSV/XLSX)")
        top_paned.add(right_frame, weight=2)
        self._build_calibration_panel(right_frame)

        # Панель с графиками сырых данных
        raw_chart_frame = ttk.LabelFrame(top_paned, text=" Данные динамики ")
        top_paned.add(raw_chart_frame, weight=3)
        self._build_raw_charts_panel(raw_chart_frame)

        # Панель выбора тарировки
        calib_sel_frame = ttk.LabelFrame(top_paned, text=" Выбор тарировки ")
        top_paned.add(calib_sel_frame, weight=2)
        self._build_calib_selection_panel(calib_sel_frame)

        # Нижняя панель - Результаты
        bot_paned = ttk.PanedWindow(main_paned, orient=tk.HORIZONTAL)
        main_paned.add(bot_paned, weight=3)
        self._build_results_panel(bot_paned)
        
        # Drag-and-drop
        windnd.hook_dropfiles(self.app.root, func=self.app._on_drop_root)
    
    def _build_dynamics_panel(self, parent):
        """Создает панель загрузки динамики."""
        src_btn_frame = ttk.Frame(parent)
        src_btn_frame.pack(fill=tk.X, padx=4, pady=(4, 0))
        ttk.Button(src_btn_frame, text="Сброс", style="ToolbarCsv.TButton",
                   command=self.app._reset_dynamics).pack(side=tk.RIGHT, padx=2)
        self.app.source_notebook = ttk.Notebook(parent)
        self.app.source_notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.app._source_tabs = {}
        self.app.source_notebook.bind("<<NotebookTabChanged>>", self.app._on_source_tab_changed)
    
    def _build_calibration_panel(self, parent):
        """Создает панель загрузки тарировки."""
        cal_btn_frame = ttk.Frame(parent)
        cal_btn_frame.pack(fill=tk.X, padx=4, pady=(4, 0))
        ttk.Button(cal_btn_frame, text="Сброс", style="ToolbarCsv.TButton",
                   command=self.app._reset_calibration).pack(side=tk.RIGHT, padx=2)
        self.app.calib_notebook = ttk.Notebook(parent)
        self.app.calib_notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.app._calib_tabs = {}
    
    def _build_raw_charts_panel(self, parent):
        """Создает панель графиков сырых данных."""
        # Pack toolbar and toggle frames first (at bottom)
        self.app.channel_toggle_frame = ttk.Frame(parent)
        self.app.channel_toggle_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=(0, 2))

        raw_tb = ttk.Frame(parent)
        raw_tb.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=(0, 4))
        self.app.raw_toolbar_frame = raw_tb

        # Create notebook and tabs
        self.app.raw_notebook = ttk.Notebook(parent)

        self.app.tab_time = ttk.Frame(self.app.raw_notebook)
        self.app.raw_notebook.add(self.app.tab_time, text="  Динамика  ")

        self.app.tab_disp = ttk.Frame(self.app.raw_notebook)
        self.app.raw_notebook.add(self.app.tab_disp, text="  Тарировка  ")

        self.app.tab_magnet = ttk.Frame(self.app.raw_notebook)
        self.app.raw_notebook.add(self.app.tab_magnet, text="  Положение магнита  ")

        self.app.raw_fig = Figure(figsize=(5, 3), dpi=100)
        self.app.raw_ax = self.app.raw_fig.add_subplot(111)
        self.app.raw_canvas = FigureCanvasTkAgg(self.app.raw_fig, master=self.app.tab_time)
        self.app.raw_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.app.disp_fig = Figure(figsize=(5, 3), dpi=100)
        self.app.disp_ax = self.app.disp_fig.add_subplot(111)
        self.app.disp_canvas = FigureCanvasTkAgg(self.app.disp_fig, master=self.app.tab_disp)
        self.app.disp_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.app.magnet_fig = Figure(figsize=(5, 3), dpi=100)
        self.app.magnet_ax = self.app.magnet_fig.add_subplot(111)
        self.app.magnet_canvas = FigureCanvasTkAgg(self.app.magnet_fig, master=self.app.tab_magnet)
        self.app.magnet_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Pack notebook last (fills remaining space above toolbar/toggles)
        self.app.raw_notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.app.raw_toolbar = NavigationToolbar2Tk(self.app.raw_canvas, raw_tb)
        self.app.raw_toolbar.update()
        self.app.disp_toolbar = NavigationToolbar2Tk(self.app.disp_canvas, raw_tb)
        self.app.disp_toolbar.pack_forget()
        self.app.magnet_toolbar = NavigationToolbar2Tk(self.app.magnet_canvas, raw_tb)
        self.app.magnet_toolbar.pack_forget()

        self.app.raw_notebook.bind("<<NotebookTabChanged>>", self.app._on_raw_tab_changed)
    
    def _build_calib_selection_panel(self, parent):
        """Создает панель выбора тарировки."""
        calib_sel_btn_frame = ttk.Frame(parent)
        calib_sel_btn_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=(0, 4))
        ttk.Button(calib_sel_btn_frame, text="Применить", style="ToolbarCsv.TButton",
                   command=self.app._apply_calib_selection).pack(side=tk.LEFT, padx=2)
        ttk.Button(calib_sel_btn_frame, text="Выбрать диапазон", style="ToolbarCsv.TButton",
                   command=self.app._start_calib_range_selection).pack(side=tk.LEFT, padx=2)
        ttk.Button(calib_sel_btn_frame, text="Сбросить вручную", style="ToolbarCsv.TButton",
                   command=self.app._reset_calib_manual).pack(side=tk.LEFT, padx=2)
        self.app.calib_sel_info_label = ttk.Label(calib_sel_btn_frame, text="", style="Info.TLabel")
        self.app.calib_sel_info_label.pack(side=tk.LEFT, padx=8)

        calib_sel_container = ttk.Frame(parent)
        calib_sel_container.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.app.calib_sel_canvas = tk.Canvas(calib_sel_container, bg="#ffffff", highlightthickness=0)
        calib_sel_vsb = ttk.Scrollbar(calib_sel_container, orient=tk.VERTICAL,
                                       command=self.app.calib_sel_canvas.yview)
        self.app.calib_sel_inner = ttk.Frame(self.app.calib_sel_canvas)
        self.app.calib_sel_inner.bind(
            "<Configure>",
            lambda e: self.app.calib_sel_canvas.configure(scrollregion=self.app.calib_sel_canvas.bbox("all"))
        )
        self.app.calib_sel_canvas.create_window((0, 0), window=self.app.calib_sel_inner, anchor="nw")
        self.app.calib_sel_canvas.configure(yscrollcommand=calib_sel_vsb.set)
        self.app.calib_sel_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        calib_sel_vsb.pack(side=tk.RIGHT, fill=tk.Y)
    
    def _build_results_panel(self, parent):
        """Создает панель результатов."""
        # Таблица результатов
        res = ttk.LabelFrame(parent, text=" Результат расчёта ")
        parent.add(res, weight=2)
        self.app.tree_result = self._make_tree(res)

        # График перемещения
        chart = ttk.LabelFrame(parent, text=" График: Перемещение от времени ")
        parent.add(chart, weight=3)

        self.app.result_fig = Figure(figsize=(7, 4), dpi=100)
        self.app.result_ax = self.app.result_fig.add_subplot(111)

        # Pack toggle frame and toolbar first (at bottom)
        self.app.result_toggle_frame = ttk.Frame(chart)
        self.app.result_toggle_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=(0, 2))

        tb_frame = ttk.Frame(chart)
        tb_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=(0, 4))

        # Create and pack canvas last (fills remaining space)
        self.app.result_canvas = FigureCanvasTkAgg(self.app.result_fig, master=chart)
        self.app.result_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.app.result_canvas.mpl_connect('motion_notify_event', self.app._on_result_motion)
        self.app.result_canvas.mpl_connect('axes_leave_event', self.app._on_result_leave)

        self.app.result_toolbar = NavigationToolbar2Tk(self.app.result_canvas, tb_frame)
        self.app.result_toolbar.update()

        # Панель пиковых значений
        self._build_peak_panel(parent)
    
    def _build_peak_panel(self, parent):
        """Создает панель пиковых значений (только график, без таблицы)."""
        peak_frame = ttk.LabelFrame(parent, text=" Пиковые значения ")
        parent.add(peak_frame, weight=2)

        peak_btn_frame = ttk.Frame(peak_frame)
        peak_btn_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=(0, 4))

        self.app.peak_select_btn = ttk.Button(peak_btn_frame, text="Выбрать диапазон",
                                               style="ToolbarCsv.TButton",
                                               command=self.app._start_peak_selection)
        self.app.peak_select_btn.pack(side=tk.LEFT, padx=2)

        self.app.peak_info_label = ttk.Label(peak_btn_frame, text="", style="Info.TLabel")
        self.app.peak_info_label.pack(side=tk.LEFT, padx=8)

        self.app.peak_fig = Figure(figsize=(5, 4), dpi=100)
        self.app.peak_ax = self.app.peak_fig.add_subplot(111)
        self.app.peak_canvas = FigureCanvasTkAgg(self.app.peak_fig, master=peak_frame)
        self.app.peak_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.app._peak_selection_active = False
        self.app._peak_selection_start = None
        self.app._peak_selection_rect = None
        self.app._peak_press_id = None
        self.app._peak_release_id = None
    
    def _make_tree(self, parent):
        """Создает Treeview для таблицы."""
        from ui.components import create_treeview
        return create_treeview(parent)
