"""
Анализ послойной деформации дорожной конструкции.

Возможности:
- загрузка Excel-файла через диалог;
- автоматический поиск участков деформаций;
- локальный ноль берётся с плато перед участком;
- вкладки для нескольких участков;
- вертикальная линия за курсором;
- клик ЛКМ фиксирует/отфиксирует курсор;
- справа выводятся значения под курсором и ΔY между слоями;
- сверху выводятся данные по выбранному участку и пикам.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

# ============================================================
# НАСТРОЙКИ
# ============================================================

SPEED_KMH_DEFAULT = 60.0

# Запас по оси Y, мм
Y_MARGIN_MM = 0.01

# Доля начала данных для глобального плато
INITIAL_BASE_FRACTION = 0.15

# Окно перед участком для локального нуля
PRE_BASE_MS = 500.0
PRE_GAP_MS = 50.0

# Объединение близких пиков/участков
MERGE_GAP_MS = 500.0

# Минимальная длительность участка
MIN_ZONE_MS = 50.0

# Чувствительность обнаружения участков
THRESHOLD_SIGMA_DEFAULT = 5.0


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def robust_mad(x):
    """Устойчивая оценка разброса через MAD."""
    x = np.asarray(x)
    return float(1.4826 * np.median(np.abs(x - np.median(x))))


def find_peaks_simple(y, height, distance):
    """
    Простой поиск локальных максимумов без scipy.
    """
    candidates = []

    for i in range(1, len(y) - 1):
        if y[i] >= height and y[i] >= y[i - 1] and y[i] >= y[i + 1]:
            candidates.append(i)

    if not candidates:
        return np.array([], dtype=int)

    peaks = []
    for i in candidates:
        if not peaks:
            peaks.append(i)
        elif i - peaks[-1] >= distance:
            peaks.append(i)
        elif y[i] > y[peaks[-1]]:
            peaks[-1] = i

    return np.array(peaks, dtype=int)


def to_numeric_series(series):
    """
    Преобразует столбец в числа.
    Понимает и точку, и запятую как десятичный разделитель.
    """
    return pd.to_numeric(
        series.astype(str).str.replace(",", ".", regex=False),
        errors="coerce"
    )


# ============================================================
# ЗАГРУЗКА ФАЙЛА
# =====================================================================

def load_deformation_file(path):
    """
    Загружает Excel-файл и автоматически ищет лист, где есть:
    - колонка времени;
    - колонки Слой 1 ... Слой 6.

    Если есть лист с значениями в мм (обычно 30...50), выбирается он.
    Если есть только сырые коды (40000+), программа предупредит.
    """
    xls = pd.ExcelFile(path)
    candidates = []

    for sheet in xls.sheet_names:
        # Пробуем разные строки как заголовок
        headers_to_try = [None] + list(range(0, 20))

        for header in headers_to_try:
            try:
                df = pd.read_excel(xls, sheet_name=sheet, header=header)
            except Exception:
                break

            if df.empty:
                continue

            # Вариант без заголовка: первый столбец время, следующие 6 - слои
            if header is None:
                if df.shape[1] < 7:
                    continue

                time_col = df.columns[0]
                layer_cols = list(df.columns[1:7])

                test_time = pd.to_numeric(df[time_col], errors="coerce")
                if test_time.notna().sum() < 100:
                    continue
            else:
                cols = [str(c).strip() for c in df.columns]
                df.columns = cols

                time_col = None
                for c in cols:
                    if "время" in c.lower():
                        time_col = c
                        break

                if time_col is None:
                    continue

                layer_cols = [c for c in cols if "слой" in c.lower()]
                layer_cols = layer_cols[:6]

                if len(layer_cols) < 6:
                    continue

            df = df[[time_col] + layer_cols].copy()

            df[time_col] = to_numeric_series(df[time_col])
            for c in layer_cols:
                df[c] = to_numeric_series(df[c])

            df = df.dropna(subset=[time_col] + layer_cols)

            if len(df) < 100:
                continue

            df = df.sort_values(time_col)
            df = df.drop_duplicates(subset=[time_col], keep="first").reset_index(drop=True)

            time = df[time_col].to_numpy(dtype=float)
            data = df[layer_cols].to_numpy(dtype=float)

            max_abs = float(np.nanmax(np.abs(data)))

            candidates.append(
                {
                    "sheet": sheet,
                    "time": time,
                    "data": data,
                    "layer_cols": layer_cols,
                    "rows": len(df),
                    "max_abs": max_abs,
                }
            )

            # Если нашли валидный вариант на этом листе, дальше header не ищем
            break

    if not candidates:
        raise ValueError(
            "Не найдена таблица с колонками времени и слоёв.\n"
            "Нужны колонки вида 'Время, мсек' и 'Слой 1'...'Слой 6'."
        )

    # Предпочитаем лист со значениями, похожими на мм, а не сырые коды
    good = [c for c in candidates if c["max_abs"] < 1000.0]

    warning = None
    if good:
        chosen = max(good, key=lambda c: c["rows"])
    else:
        chosen = max(candidates, key=lambda c: c["rows"])
        warning = (
            "Внимание: не найден лист со значениями, похожими на мм.\n"
            "Возможно, загружены сырые коды датчиков (значения порядка 40000).\n"
            "Если деформации должны быть 0.0xxx мм, нужен лист с результатом в мм."
        )

    return (
        chosen["time"],
        chosen["data"],
        chosen["layer_cols"],
        chosen["sheet"],
        warning,
    )


# ============================================================
# АНАЛИЗ ДЕФОРМАЦИЙ
# ============================================================

class DeformationAnalyzer:
    def __init__(self, time_ms, data, layer_names):
        self.time = np.asarray(time_ms, dtype=float)
        self.data = np.asarray(data, dtype=float)
        self.layer_names = list(layer_names)
        self.n_layers = self.data.shape[1]
        self.n_points = len(self.time)

        if self.n_points > 1:
            self.dt_ms = float(np.median(np.diff(self.time)))
        else:
            self.dt_ms = 5.0

        self.global_baseline = None
        self.global_noise = None
        self.zones = []

    def ms_to_points(self, ms):
        return max(1, int(round(float(ms) / self.dt_ms)))

    def prepare(self):
        """
        Глобальная базовая линия и шум по начальному плато.
        """
        n_base = max(50, int(self.n_points * INITIAL_BASE_FRACTION))
        base_data = self.data[:n_base, :]

        self.global_baseline = np.nanmedian(base_data, axis=0)

        # Шум базовой линии
        mad = 1.4826 * np.nanmedian(
            np.abs(base_data - self.global_baseline),
            axis=0
        )
        std = np.nanstd(base_data, axis=0)

        noise = np.where(mad < 1e-9, std, mad)
        noise = np.where(noise < 1e-9, 1e-6, noise)

        self.global_noise = noise

    def find_zones(self, threshold_sigma=THRESHOLD_SIGMA_DEFAULT):
        """
        Автоматический поиск участков деформаций.
        """
        if self.global_baseline is None:
            self.prepare()

        z = np.abs((self.data - self.global_baseline) / self.global_noise)
        score = np.sum(z, axis=1)

        med = float(np.nanmedian(score))
        mad = robust_mad(score)

        threshold_high = max(
            med + threshold_sigma * mad,
            3.0 * self.n_layers
        )

        threshold_low = max(
            med + max(2.0, threshold_sigma * 0.5) * mad,
            1.5 * self.n_layers
        )

        distance_points = self.ms_to_points(100.0)

        peaks = find_peaks_simple(score, threshold_high, distance_points)

        # Если пики не нашлись, пробуем снизить порог
        if len(peaks) == 0:
            threshold_high = max(
                med + threshold_sigma * 0.5 * mad,
                2.0 * self.n_layers
            )
            peaks = find_peaks_simple(score, threshold_high, distance_points)

        # Если всё равно нет, пробуем просто активные области
        if len(peaks) == 0:
            active_idx = np.where(score > threshold_high)[0]
            if len(active_idx) == 0:
                self.zones = []
                return self.zones

            peaks = []
            start = active_idx[0]
            prev = active_idx[0]

            for i in active_idx[1:]:
                if i - prev > 1:
                    seg = np.arange(start, prev + 1)
                    peaks.append(seg[int(np.argmax(score[seg]))])
                    start = i
                prev = i

            seg = np.arange(start, prev + 1)
            peaks.append(seg[int(np.argmax(score[seg]))])
            peaks = np.array(peaks, dtype=int)

        # Расширяем каждый пик до уровня threshold_low
        raw_zones = []
        for p in peaks:
            s = int(p)
            e = int(p)

            while s > 0 and score[s - 1] > threshold_low:
                s -= 1

            while e < self.n_points - 1 and score[e + 1] > threshold_low:
                e += 1

            raw_zones.append((s, e))

        # Сортировка и объединение близких зон
        raw_zones.sort(key=lambda z: z[0])

        merged = []
        merge_gap_points = self.ms_to_points(MERGE_GAP_MS)

        for s, e in raw_zones:
            if not merged:
                merged.append([s, e])
                continue

            if s - merged[-1][1] <= merge_gap_points:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])

        min_points = self.ms_to_points(MIN_ZONE_MS)

        self.zones = [
            (int(s), int(e))
            for s, e in merged
            if (e - s + 1) >= min_points
        ]

        return self.zones

    def local_baseline(self, start_idx):
        """
        Локальный ноль участка.
        Берётся медиана плато перед началом участка.
        """
        t_start = self.time[start_idx]

        left = np.searchsorted(
            self.time,
            t_start - PRE_BASE_MS,
            side="left"
        )

        right = np.searchsorted(
            self.time,
            t_start - PRE_GAP_MS,
            side="left"
        ) - 1

        if right - left + 1 >= 20:
            segment = self.data[left:right + 1, :]
            base = np.nanmedian(segment, axis=0)
            seg_std = np.nanstd(segment, axis=0)

            # Если окно перед участком слишком шумное, берём глобальный ноль
            if np.nanmean(seg_std) <= 5.0 * np.nanmean(self.global_noise):
                return base

        return self.global_baseline

    def zone_result(self, zone_idx, speed_kmh):
        """
        Подготавливает данные для одного участка.
        """
        s, e = self.zones[zone_idx]

        base = self.local_baseline(s)

        zone_time = self.time[s:e + 1]
        zone_raw = self.data[s:e + 1, :]
        zone_def = zone_raw - base

        speed_ms = speed_kmh / 3.6
        x = (zone_time - zone_time[0]) / 1000.0 * speed_ms

        # Пики каждого слоя
        peak_idx = np.argmax(np.abs(zone_def), axis=0)
        peak_x = x[peak_idx]
        peak_time = zone_time[peak_idx]
        peak_vals = zone_def[peak_idx, np.arange(self.n_layers)]

        # Поиск двух самых больших пиков для расчёта скорости по расстоянию между осями
        # Находим точки с максимальными абсолютными отклонениями, сортируем по величине,
        # затем берём первые две по времени
        abs_def = np.abs(zone_def)
        
        # Находим все локальные максимумы на summed score (сумма по всем слоям)
        score = np.sum(abs_def, axis=1)
        candidates = []
        for i in range(1, len(score) - 1):
            if score[i] >= score[i - 1] and score[i] >= score[i + 1]:
                candidates.append((i, score[i]))
        
        # Сортируем кандидаты по величине пика (убывание)
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        # Берём топ пики (сначала самые большие), затем сортируем их по времени
        # и берём первые два
        top_peaks = []
        distance_points = self.ms_to_points(50.0)  # минимальное расстояние между пиками 50 мс
        
        for idx, val in candidates:
            # Проверяем, что пик достаточно далеко от уже выбранных
            is_valid = True
            for existing_idx in top_peaks:
                if abs(idx - existing_idx) < distance_points:
                    is_valid = False
                    break
            if is_valid:
                top_peaks.append(idx)
                if len(top_peaks) >= 2:
                    break
        
        # Сортируем найденные пики по времени и берём первые два
        top_peaks.sort()
        
        first_two_peak_times = []
        if len(top_peaks) >= 2:
            first_two_peak_times = [float(zone_time[top_peaks[0]]), float(zone_time[top_peaks[1]])]
        elif len(top_peaks) == 1:
            first_two_peak_times = [float(zone_time[top_peaks[0]]), None]
        else:
            first_two_peak_times = [None, None]

        # Самый большой пик среди всех слоёв
        flat_idx = int(np.nanargmax(np.abs(zone_def)))
        largest_row, largest_layer = np.unravel_index(flat_idx, zone_def.shape)

        largest_x = float(x[largest_row])
        largest_time = float(zone_time[largest_row])
        largest_value = float(zone_def[largest_row, largest_layer])

        # Значения всех слоёв на вертикали максимального пика
        vert_values = zone_def[largest_row, :]
        delta_y_at_largest = np.diff(vert_values)

        return {
            "zone_idx": zone_idx,
            "start_idx": int(s),
            "end_idx": int(e),
            "t_start": float(zone_time[0]),
            "t_end": float(zone_time[-1]),
            "duration_ms": float(zone_time[-1] - zone_time[0]),
            "x": x,
            "time": zone_time,
            "defs": zone_def,
            "x_start": float(x[0]),
            "x_end": float(x[-1]),
            "base": base,
            "peak_x": peak_x,
            "peak_time": peak_time,
            "peak_vals": peak_vals,
            "first_two_peak_times": first_two_peak_times,
            "largest_layer": int(largest_layer),
            "largest_x": largest_x,
            "largest_time": largest_time,
            "largest_value": largest_value,
            "vert_values": vert_values,
            "delta_y_at_largest": delta_y_at_largest,
        }


# ============================================================
# ГЛАВНОЕ ПРИЛОЖЕНИЕ
# ============================================================

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Анализ послойной деформации")
        self.root.geometry("1500x900")

        self.analyzer = None
        self.sheet_name = ""
        self.load_warning = None

        self.layer_names = []
        self.zone_results = []
        self.graphics = []

        self.current_zone = 0
        self.frozen = False

        self._build_ui()

    # ------------------------------------------------------------
    # UI
    # ------------------------------------------------------------

    def _build_ui(self):
        # Верхняя панель управления
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill=tk.X)

        ttk.Button(
            top,
            text="📂 Загрузить файл",
            command=self.load_file,
            width=22
        ).pack(side=tk.LEFT, padx=5)

        ttk.Label(top, text="Скорость, км/ч:").pack(side=tk.LEFT, padx=(15, 5))
        self.speed_var = tk.StringVar(value=str(SPEED_KMH_DEFAULT))
        ttk.Entry(top, textvariable=self.speed_var, width=8).pack(side=tk.LEFT)

        ttk.Label(top, text="Порог, σ:").pack(side=tk.LEFT, padx=(15, 5))
        self.threshold_var = tk.StringVar(value=str(THRESHOLD_SIGMA_DEFAULT))
        ttk.Entry(top, textvariable=self.threshold_var, width=8).pack(side=tk.LEFT)

        ttk.Label(top, text="Расстояние между осями, м:").pack(side=tk.LEFT, padx=(15, 5))
        self.axis_distance_var = tk.StringVar(value="0.5")
        ttk.Entry(top, textvariable=self.axis_distance_var, width=8).pack(side=tk.LEFT)

        ttk.Button(
            top,
            text="🔍 Анализировать",
            command=self.analyze,
            width=18
        ).pack(side=tk.LEFT, padx=15)

        self.file_label = ttk.Label(top, text="Файл не загружен", foreground="gray")
        self.file_label.pack(side=tk.LEFT, padx=15)

        self.status_label = ttk.Label(top, text="Курсор свободен", foreground="navy")
        self.status_label.pack(side=tk.LEFT, padx=15)

        # Верхняя информационная панель
        self.info_text = tk.Text(self.root, height=8, font=("Consolas", 9))
        self.info_text.pack(fill=tk.X, padx=10, pady=5)
        self.info_text.configure(state=tk.DISABLED)

        # Основная область: слева графики, справа панель данных
        paned = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        left_frame = ttk.Frame(paned)
        self.right_frame = ttk.Frame(paned, width=330)

        paned.add(left_frame, weight=3)
        paned.add(self.right_frame, weight=1)

        self.notebook = ttk.Notebook(left_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_selected)

        self._build_right_panel()

    def _build_right_panel(self, n_layers=6, layer_names=None):
        """
        Правая панель с текущими значениями под курсором.
        """
        for widget in self.right_frame.winfo_children():
            widget.destroy()

        if layer_names is None:
            layer_names = [f"Слой {i + 1}" for i in range(n_layers)]

        self.layer_names = list(layer_names)

        ttk.Label(
            self.right_frame,
            text="Данные курсора",
            font=("Arial", 11, "bold")
        ).pack(anchor=tk.W, pady=(5, 3))

        self.cursor_time_label = ttk.Label(
            self.right_frame,
            text="Время: —",
            font=("Consolas", 10)
        )
        self.cursor_time_label.pack(anchor=tk.W)

        self.cursor_dist_label = ttk.Label(
            self.right_frame,
            text="Расстояние: —",
            font=("Consolas", 10)
        )
        self.cursor_dist_label.pack(anchor=tk.W, pady=(0, 5))

        ttk.Separator(self.right_frame, orient=tk.HORIZONTAL).pack(
            fill=tk.X, pady=5
        )

        ttk.Label(
            self.right_frame,
            text="Деформация слоёв, мм",
            font=("Arial", 10, "bold")
        ).pack(anchor=tk.W, pady=(0, 3))

        self.layer_value_labels = []

        for i, name in enumerate(self.layer_names):
            row = ttk.Frame(self.right_frame)
            row.pack(fill=tk.X, pady=1)

            ttk.Label(
                row,
                text=f"{name}:",
                width=16,
                anchor="w"
            ).pack(side=tk.LEFT)

            val_label = ttk.Label(row, text="—", font=("Consolas", 10))
            val_label.pack(side=tk.LEFT)

            self.layer_value_labels.append(val_label)

        ttk.Separator(self.right_frame, orient=tk.HORIZONTAL).pack(
            fill=tk.X, pady=5
        )

        ttk.Label(
            self.right_frame,
            text="ΔY между соседними слоями, мм",
            font=("Arial", 10, "bold")
        ).pack(anchor=tk.W, pady=(0, 3))

        self.delta_labels = []

        for i in range(len(self.layer_names) - 1):
            row = ttk.Frame(self.right_frame)
            row.pack(fill=tk.X, pady=1)

            ttk.Label(
                row,
                text=f"ΔY {i + 1}-{i + 2}:",
                width=16,
                anchor="w"
            ).pack(side=tk.LEFT)

            delta_label = ttk.Label(row, text="—", font=("Consolas", 10))
            delta_label.pack(side=tk.LEFT)

            self.delta_labels.append(delta_label)

        ttk.Separator(self.right_frame, orient=tk.HORIZONTAL).pack(
            fill=tk.X, pady=5
        )

        self.peak_info_label = ttk.Label(
            self.right_frame,
            text="Максимальный пик: —",
            wraplength=300,
            justify=tk.LEFT,
            font=("Arial", 9)
        )
        self.peak_info_label.pack(anchor=tk.W, pady=(5, 5))

        self.freeze_label = ttk.Label(
            self.right_frame,
            text="Клик ЛКМ — фиксация/отмена курсора",
            wraplength=300,
            foreground="gray"
        )
        self.freeze_label.pack(anchor=tk.W, pady=(10, 0))

    # ------------------------------------------------------------
    # ЗАГРУЗКА И АНАЛИЗ
    # ------------------------------------------------------------

    def load_file(self):
        path = filedialog.askopenfilename(
            title="Выберите Excel-файл",
            filetypes=[
                ("Excel файлы", "*.xlsx *.xls"),
                ("Все файлы", "*.*"),
            ]
        )

        if not path:
            return

        try:
            time_ms, data, layer_cols, sheet_name, warning = load_deformation_file(path)

            self.layer_names = list(layer_cols)
            self.sheet_name = sheet_name
            self.load_warning = warning

            self.analyzer = DeformationAnalyzer(time_ms, data, layer_cols)
            self.analyzer.prepare()

            self._build_right_panel(len(layer_cols), layer_cols)

            self.file_label.config(
                text=f"✅ {path.split('/')[-1]}",
                foreground="green"
            )

            if warning:
                messagebox.showwarning("Внимание", warning)

            self.analyze()

        except Exception as exc:
            messagebox.showerror("Ошибка", str(exc))

    def analyze(self):
        if self.analyzer is None:
            messagebox.showwarning("Внимание", "Сначала загрузите файл")
            return

        try:
            speed = float(self.speed_var.get())
            threshold_sigma = float(self.threshold_var.get())
        except ValueError:
            messagebox.showerror("Ошибка", "Некорректные параметры скорости или порога")
            return

        zones = self.analyzer.find_zones(threshold_sigma=threshold_sigma)

        if not zones:
            self.zone_results = []
            self._clear_tabs()
            self._set_info_text("Участки деформаций не найдены.")
            messagebox.showwarning(
                "Внимание",
                "Участки деформаций не найдены.\n"
                "Попробуйте уменьшить порог."
            )
            return

        self.zone_results = [
            self.analyzer.zone_result(i, speed)
            for i in range(len(zones))
        ]

        self._build_tabs()
        self._update_top_info()

        if self.zone_results:
            self.current_zone = 0
            self.notebook.select(0)
            self._show_zone_static(0)

    # ------------------------------------------------------------
    # ВКЛАДКИ
    # ------------------------------------------------------------

    def _clear_tabs(self):
        for tab in self.notebook.tabs():
            self.notebook.forget(tab)

        for g in self.graphics:
            try:
                g["canvas"].get_tk_widget().destroy()
            except Exception:
                pass

            try:
                plt.close(g["fig"])
            except Exception:
                pass

        self.graphics = []

    def _build_tabs(self):
        self._clear_tabs()

        for i, res in enumerate(self.zone_results):
            tab = ttk.Frame(self.notebook)
            self.notebook.add(tab, text=f"Участок {i + 1}")

            fig, ax = plt.subplots(figsize=(10.5, 5.5), dpi=100)
            graph = self._draw_zone(ax, res)

            canvas = FigureCanvasTkAgg(fig, master=tab)
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

            toolbar = NavigationToolbar2Tk(canvas, tab)
            toolbar.update()

            canvas.mpl_connect(
                "motion_notify_event",
                lambda event, idx=i: self.on_move(event, idx)
            )

            canvas.mpl_connect(
                "button_press_event",
                lambda event, idx=i: self.on_click(event, idx)
            )

            graph["canvas"] = canvas
            graph["fig"] = fig

            self.graphics.append(graph)

    def _draw_zone(self, ax, res):
        x = res["x"]
        defs = res["defs"]

        # Переворачиваем значения для отображения
        defs = -defs

        x_span = float(x[-1] - x[0])
        if x_span <= 1e-12:
            x_span = 1.0

        # Кривые слоёв
        for i, name in enumerate(self.layer_names):
            ax.plot(
                x,
                defs[:, i],
                label=name,
                linewidth=1.6
            )

        # Курсорная вертикальная линия
        cursor_line = ax.axvline(
            res["largest_x"],
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

        # Границы Y с запасом
        y_min = float(np.nanmin(defs))
        y_max = float(np.nanmax(defs))

        if not np.isfinite(y_min) or not np.isfinite(y_max):
            y_min, y_max = -0.05, 0.05

        if y_max - y_min < 2.0 * Y_MARGIN_MM:
            center = (y_min + y_max) / 2.0
            y_min = center - 0.02
            y_max = center + 0.02

        ax.set_ylim(y_min - Y_MARGIN_MM, y_max + Y_MARGIN_MM)
        ax.set_xlim(x[0] - 0.03 * x_span, x[-1] + 0.18 * x_span)

        ax.set_xlabel("Расстояние от начала участка, м")
        ax.set_ylabel("Деформация, мм")
        ax.grid(True, linestyle="--", alpha=0.4)
        ax.legend(loc="upper right", fontsize=8)

        return {
            "ax": ax,
            "vline": cursor_line,
            "cursor_pts": cursor_points,
            "x": x,
            "defs": defs,
            "time": res["time"],
        }

    # ------------------------------------------------------------
    # СОБЫТИЯ МЫШИ
    # ------------------------------------------------------------

    def _current_tab_index(self):
        try:
            return self.notebook.index(self.notebook.select())
        except Exception:
            return None

    def on_move(self, event, zone_idx):
        if self.frozen:
            return

        current = self._current_tab_index()
        if current is None or current != zone_idx:
            return

        if zone_idx >= len(self.graphics):
            return

        g = self.graphics[zone_idx]

        if event.inaxes != g["ax"] or event.xdata is None:
            g["vline"].set_visible(False)
            g["cursor_pts"].set_visible(False)
            g["ax"].figure.canvas.draw_idle()
            return

        self._update_cursor(zone_idx, float(event.xdata))

    def on_click(self, event, zone_idx):
        if event.button != 1:
            return

        current = self._current_tab_index()
        if current is None or current != zone_idx:
            return

        if zone_idx >= len(self.graphics):
            return

        g = self.graphics[zone_idx]

        if event.inaxes != g["ax"]:
            return

        self.frozen = not self.frozen

        if self.frozen:
            self.status_label.config(text="🔒 Курсор зафиксирован", foreground="red")
        else:
            self.status_label.config(text="Курсор свободен", foreground="navy")

        if event.xdata is not None:
            self._update_cursor(zone_idx, float(event.xdata))

    def _update_cursor(self, zone_idx, x_val):
        if zone_idx >= len(self.graphics):
            return

        g = self.graphics[zone_idx]

        x = g["x"]
        defs = g["defs"]
        time_arr = g["time"]

        if len(x) == 0:
            return

        idx = int(np.clip(np.searchsorted(x, x_val), 0, len(x) - 1))

        xv = float(x[idx])
        vals = defs[idx, :]

        g["vline"].set_xdata([xv, xv])
        g["vline"].set_visible(True)

        g["cursor_pts"].set_data([xv] * len(vals), vals)
        g["cursor_pts"].set_visible(True)

        g["ax"].figure.canvas.draw_idle()

        # Правая панель
        self.cursor_time_label.config(text=f"Время: {time_arr[idx]:.0f} мс")
        self.cursor_dist_label.config(text=f"Расстояние: {xv:.3f} м")

        for i, lbl in enumerate(self.layer_value_labels):
            lbl.config(text=f"{vals[i]:+.3f}")

        for i, lbl in enumerate(self.delta_labels):
            dy = abs(vals[i + 1] - vals[i])
            lbl.config(text=f"{dy:.3f}")

    # ------------------------------------------------------------
    # ВЫБОР ВКЛАДКИ
    # ------------------------------------------------------------

    def on_tab_selected(self, _event=None):
        idx = self._current_tab_index()

        if idx is None or idx >= len(self.zone_results):
            return

        self.current_zone = idx
        self.frozen = False
        self.status_label.config(text="Курсор свободен", foreground="navy")

        self._update_top_info()
        self._show_zone_static(idx)

    def _show_zone_static(self, zone_idx):
        if zone_idx >= len(self.zone_results):
            return

        res = self.zone_results[zone_idx]

        layer_name = self.layer_names[res["largest_layer"]]

        self.peak_info_label.config(
            text=(
                f"Максимальный пик:\n"
                f"{layer_name}: {res['largest_value']:+.3f} мм\n"
                f"Время: {res['largest_time']:.0f} мс\n"
                f"Расстояние: {res['largest_x']:.3f} м"
            )
        )

        self._update_cursor(zone_idx, res["largest_x"])

    # ------------------------------------------------------------
    # ВЕРХНЯЯ ИНФОРМАЦИОННАЯ ПАНЕЛЬ
    # ------------------------------------------------------------

    def _set_info_text(self, text):
        self.info_text.configure(state=tk.NORMAL)
        self.info_text.delete("1.0", tk.END)
        self.info_text.insert(tk.END, text)
        self.info_text.configure(state=tk.DISABLED)

    def _update_top_info(self):
        if not self.zone_results:
            self._set_info_text("Нет данных.")
            return

        idx = self.current_zone

        if idx >= len(self.zone_results):
            idx = 0

        res = self.zone_results[idx]

        lines = []

        # Расчёт скорости по первым двум пикам и расстоянию между осями
        speed_calculated_str = "—"
        try:
            axis_distance = float(self.axis_distance_var.get())
            t1, t2 = res["first_two_peak_times"]
            if t1 is not None and t2 is not None and t2 > t1:
                delta_t_ms = t2 - t1
                if delta_t_ms > 0:
                    # v = distance / time
                    # distance в метрах, time в секундах
                    delta_t_s = delta_t_ms / 1000.0
                    v_ms = axis_distance / delta_t_s
                    v_kmh = v_ms * 3.6
                    speed_calculated_str = f"{v_kmh:.1f} км/ч"
        except (ValueError, TypeError, KeyError):
            pass

        lines.append(
            f"Лист: {self.sheet_name} | "
            f"Скорость заданная: {self.speed_var.get()} км/ч | "
            f"Скорость расчётная: {speed_calculated_str} | "
            f"Участков: {len(self.zone_results)} | "
            f"Выбран участок: {idx + 1}"
        )

        lines.append(
            f"Диапазон участка: {res['t_start']:.0f}–{res['t_end']:.0f} мс | "
            f"длительность {res['duration_ms']:.0f} мс | "
            f"расстояние {res['x_start']:.3f}–{res['x_end']:.3f} м"
        )

        peaks_str = "; ".join(
            [
                f"{self.layer_names[i]}: {res['peak_vals'][i]:+.3f}"
                for i in range(self.analyzer.n_layers)
            ]
        )
        lines.append(f"Пики слоёв: {peaks_str}")

        dy_str = "; ".join(
            [
                f"{abs(d):.3f}"
                for d in res["delta_y_at_largest"]
            ]
        )
        lines.append(f"ΔY на вертикали макс. пика: {dy_str}")

        lines.append(
            f"Макс. пик: {self.layer_names[res['largest_layer']]} "
            f"{res['largest_value']:+.3f} мм; "
            f"t={res['largest_time']:.0f} мс; "
            f"x={res['largest_x']:.3f} м"
        )

        self._set_info_text("\n".join(lines))


# ============================================================
# ЗАПУСК
# ============================================================

def main():
    plt.rcParams["font.family"] = "DejaVu Sans"

    root = tk.Tk()
    app = App(root)
    root.mainloop()


if __name__ == "__main__":
    main()