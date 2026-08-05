"""
Анализ послойной деформации дорожной конструкции.

Использует данные перемещений от времени из основного приложения.
"""

import numpy as np
import pandas as pd

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
# АНАЛИЗ ДЕФОРМАЦИЙ
# ============================================================

class DeformationAnalyzer:
    """
    Анализатор послойных деформаций.
    
    Принимает данные времени (мс) и перемещений (мм) из основного приложения.
    """
    
    def __init__(self, time_ms, data, layer_names):
        """
        Инициализация анализатора.
        
        Parameters
        ----------
        time_ms : array-like
            Время в миллисекундах
        data : array-like
            Данные перемещений по слоям (мм), shape (n_points, n_layers)
        layer_names : list
            Названия слоёв
        """
        self.time = np.asarray(time_ms, dtype=float)
        self.data = np.asarray(data, dtype=float)
        self.layer_names = list(layer_names)
        self.n_layers = self.data.shape[1] if len(self.data.shape) > 1 else 1
        self.n_points = len(self.time)

        if self.n_points > 1:
            self.dt_ms = float(np.median(np.diff(self.time)))
        else:
            self.dt_ms = 5.0

        self.global_baseline = None
        self.global_noise = None
        self.zones = []

    def ms_to_points(self, ms):
        """Перевод миллисекунд в количество точек."""
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

        # Поиск двух пиков на самом нижнем слое для расчёта скорости по расстоянию между осями
        # Берём самый нижний слой (последний в массиве данных)
        bottom_layer_idx = self.n_layers - 1
        bottom_layer_def = zone_def[:, bottom_layer_idx]
        
        # Находим локальные максимумы - данные уже центрированы (положительные значения),
        # а для отображения их переворачивают с -1, поэтому ищем максимумы в центрированных данных
        # (которые на графике будут выглядеть как пики вверх после переворота)
        peaks = []
        for i in range(1, len(bottom_layer_def)-1):
            if bottom_layer_def[i] > bottom_layer_def[i-1] and bottom_layer_def[i] > bottom_layer_def[i+1]:
                peaks.append((zone_time[i], bottom_layer_def[i]))
        
        # Фильтруем по амплитуде (берем только сильные пики, например > 0.05 мм)
        # Это нужно чтобы отсечь мелкие локальные экстремумы и найти два основных пика
        strong_peaks = [(t, v) for t, v in peaks if v > 0.05]
        
        # Сортируем пики по времени
        strong_peaks.sort(key=lambda x: x[0])
        
        # Берем два первых пика, разделённых минимум 50 мс (чтобы игнорировать близкие локальные экстремумы)
        min_gap_ms = 50.0
        selected_peaks = []
        for peak in strong_peaks:
            if not selected_peaks:
                selected_peaks.append(peak)
            elif peak[0] - selected_peaks[-1][0] >= min_gap_ms:
                selected_peaks.append(peak)
            if len(selected_peaks) == 2:
                break
        
        first_two_peak_times = []
        if len(selected_peaks) >= 2:
            first_two_peak_times = [selected_peaks[0][0], selected_peaks[1][0]]
        elif len(selected_peaks) == 1:
            first_two_peak_times = [selected_peaks[0][0], None]
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
