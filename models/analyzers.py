"""
Модуль для анализа сигналов: поиск базовой линии, восходящих участков и пересечений.
"""
import numpy as np


class SignalAnalyzer:
    """Анализ сигналов для обработки данных калибровки и динамики."""

    @staticmethod
    def find_baseline(values, max_std=0.02, min_fraction=0.05):
        """
        Поиск базовой линии на участке с минимальными колебаниями.
        Оптимизированная векторизованная версия.
        
        Args:
            values: массив значений сигнала
            max_std: максимальное стандартное отклонение для участка
            min_fraction: минимальная доля длины сигнала для участка
            
        Returns:
            float: значение базовой линии
        """
        arr = np.asarray(values, dtype=float)
        n = len(arr)
        if n == 0:
            return 0.0
        if n < 10:
            return float(np.min(arr))

        val_min = float(np.min(arr))
        val_max = float(np.max(arr))
        val_span = val_max - val_min
        lower_ceiling = val_min + val_span * 0.35 if val_span > 1e-9 else val_max
        min_len = max(int(n * min_fraction), 10)
        
        # Ограничиваем поиск только начальным участком (первые 20% данных)
        # и используем полностью векторизованный подход
        search_len = min(int(n * 0.2), 5000)
        if search_len < min_len:
            search_len = min_len
        
        search_arr = arr[:search_len]
        m = len(search_arr)
        
        # Векторизованный расчет скользящего среднего и стандартного отклонения
        # Используем cumsum для быстрого расчета скользящих статистик
        cumsum = np.cumsum(np.insert(search_arr, 0, 0))
        cumsum_sq = np.cumsum(np.insert(search_arr**2, 0, 0))
        
        best_mean = None
        best_len = 0
        
        # Проверяем различные длины сегментов
        for seg_len in range(min_len, min(search_len, 2000), max(1, min_len // 10)):
            # Векторизованный расчет средних и стандартных отклонений для всех позиций
            if m < seg_len:
                continue
                
            sums = cumsum[seg_len:] - cumsum[:-seg_len]
            sums_sq = cumsum_sq[seg_len:] - cumsum_sq[:-seg_len]
            
            means = sums / seg_len
            stds = np.sqrt(sums_sq / seg_len - means**2)
            
            # Находим сегменты, удовлетворяющие критериям
            valid_mask = (stds <= max_std) & (means <= lower_ceiling)
            valid_indices = np.where(valid_mask)[0]
            
            if len(valid_indices) > 0:
                # Берем первый подходящий сегмент (самый ранний)
                idx = valid_indices[0]
                seg_mean = means[idx]
                
                # Пытаемся расширить сегмент
                end_idx = idx + seg_len
                while end_idx < m:
                    test_seg = search_arr[idx:end_idx + 1]
                    test_std = np.std(test_seg)
                    test_mean = np.mean(test_seg)
                    if test_std > max_std or test_mean > lower_ceiling:
                        break
                    end_idx += 1
                
                actual_len = end_idx - idx
                if actual_len > best_len:
                    best_len = actual_len
                    best_mean = float(np.mean(search_arr[idx:end_idx]))
        
        if best_mean is not None:
            return best_mean

        # Fallback: берем среднее наименьших 10% значений
        low_n = max(int(n * 0.1), 5)
        return float(np.mean(np.sort(arr)[:low_n]))

    @staticmethod
    def find_rising_indices(tug):
        """
        Поиск индексов минимума и пика на восходящем участке.
        
        Args:
            tug: массив значений датчика Холла
            
        Returns:
            tuple: (индекс начала, индекс пика)
        """
        arr = np.asarray(tug, dtype=float)
        n = len(arr)
        if n < 10:
            return 0, n - 1

        baseline = SignalAnalyzer.find_baseline(arr)
        threshold = baseline + 0.15 * (np.max(arr) - baseline)

        above = np.where(arr >= threshold)[0]
        if len(above) == 0:
            return 0, n - 1

        start_idx = above[0]
        peak_idx = start_idx
        for i in range(start_idx, n):
            if arr[i] >= arr[peak_idx]:
                peak_idx = i
            elif i > peak_idx + 10 and arr[i] < arr[peak_idx] * 0.95:
                break

        pre_start = max(0, start_idx - 10)
        for i in range(start_idx - 1, pre_start - 1, -1):
            if arr[i] <= baseline:
                start_idx = i
                break

        return int(start_idx), int(peak_idx)

    @staticmethod
    def find_rising_range(disp, tug):
        """Определение диапазона восходящего участка по перемещению."""
        idx_min, idx_peak = SignalAnalyzer.find_rising_indices(tug)
        disp_arr = np.asarray(disp, dtype=float)
        return float(disp_arr[idx_min]), float(disp_arr[idx_peak])

    @staticmethod
    def merge_rising_ranges(ranges):
        """Объединение пересекающихся диапазонов восходящих участков."""
        if not ranges:
            return None
        ranges_sorted = sorted(ranges, key=lambda x: x[0])
        merged = [list(ranges_sorted[0])]
        for curr in ranges_sorted[1:]:
            last = merged[-1]
            if curr[0] <= last[1]:
                last[1] = max(last[1], curr[1])
            else:
                merged.append(list(curr))
        if len(merged) == 1:
            return tuple(merged[0])
        return None

    @staticmethod
    def common_rising_bounds(disp, tug_series):
        """Поиск общих границ восходящего участка для нескольких сенсоров."""
        ranges = []
        for sensor_name, tug in tug_series.items():
            r = SignalAnalyzer.find_rising_range(disp, tug)
            if r:
                ranges.append(r)
        return SignalAnalyzer.merge_rising_ranges(ranges)

    @staticmethod
    def extract_rising_branch(disp, tug, range_left=None, range_right=None):
        """
        Извлечение восходящей ветви калибровки.
        
        Args:
            disp: массив перемещений
            tug: массив значений датчика
            range_left: левая граница диапазона (опционально)
            range_right: правая граница диапазона (опционально)
            
        Returns:
            tuple: (disp_eff, tug_eff) - эффективные массивы
        """
        disp_arr = np.asarray(disp, dtype=float)
        tug_arr = np.asarray(tug, dtype=float)

        if range_left is not None and range_right is not None:
            mask = (disp_arr >= range_left) & (disp_arr <= range_right)
            disp_eff = disp_arr[mask]
            tug_eff = tug_arr[mask]
        else:
            idx_min, idx_peak = SignalAnalyzer.find_rising_indices(tug_arr)
            disp_eff = disp_arr[idx_min:idx_peak + 1]
            tug_eff = tug_arr[idx_min:idx_peak + 1]

        if len(disp_eff) < 2:
            return None, None

        sort_idx = np.argsort(disp_eff)
        return disp_eff[sort_idx], tug_eff[sort_idx]

    @staticmethod
    def find_intersections_at_level(disp, tug, level):
        """
        Поиск точек пересечения с заданным уровнем.
        
        Args:
            disp: массив перемещений
            tug: массив значений датчика
            level: целевой уровень
            
        Returns:
            list: список точек пересечения (tug, disp)
        """
        tug_arr = np.asarray(tug, dtype=float)
        disp_arr = np.asarray(disp, dtype=float)
        n = len(tug_arr)
        intersections = []

        for i in range(n - 1):
            y1, y2 = tug_arr[i], tug_arr[i + 1]
            if (y1 - level) * (y2 - level) < 0:
                t = (level - y1) / (y2 - y1 + 1e-12)
                x_interp = disp_arr[i] + t * (disp_arr[i + 1] - disp_arr[i])
                intersections.append((level, x_interp))
            elif abs(y1 - level) < 1e-9:
                intersections.append((y1, disp_arr[i]))

        return intersections

    @staticmethod
    def interp_linear(target, tug_vals, disp_vals):
        """
        Линейная интерполяция перемещения по значению датчика.
        
        Args:
            target: целевое значение датчика
            tug_vals: массив значений датчика (отсортированный)
            disp_vals: массив перемещений (соответствующий tug_vals)
            
        Returns:
            float: интерполированное перемещение или None
        """
        tug_arr = np.asarray(tug_vals, dtype=float)
        disp_arr = np.asarray(disp_vals, dtype=float)
        n = len(tug_arr)

        if n < 2:
            return None

        if target <= tug_arr[0]:
            return float(disp_arr[0])
        if target >= tug_arr[-1]:
            return float(disp_arr[-1])

        for i in range(n - 1):
            if tug_arr[i] <= target <= tug_arr[i + 1]:
                t = (target - tug_arr[i]) / (tug_arr[i + 1] - tug_arr[i] + 1e-12)
                return float(disp_arr[i] + t * (disp_arr[i + 1] - disp_arr[i]))

        return None

    @staticmethod
    def central_level(tug):
        """Вычисление центрального уровня сигнала."""
        tug_arr = np.asarray(tug, dtype=float)
        return float((np.min(tug_arr) + np.max(tug_arr)) / 2)

    @staticmethod
    def get_overlap_range(calib_tug, dyn_channel, zero_point=None):
        """
        Определение диапазона перекрытия калибровки и динамики.
        
        Args:
            calib_tug: массив значений калибровочного датчика
            dyn_channel: массив значений динамического канала
            zero_point: точка нуля (опционально)
            
        Returns:
            tuple: (left, right) - границы перекрытия или None
        """
        tug = np.asarray(calib_tug, dtype=float)
        dyn = np.asarray(dyn_channel, dtype=float)

        if zero_point is None:
            zero_point = SignalAnalyzer.find_baseline(dyn)
        dyn_centered = dyn - zero_point

        dyn_min, dyn_max = float(np.min(dyn_centered)), float(np.max(dyn_centered))
        tug_min, tug_max = float(np.min(tug)), float(np.max(tug))

        overlap_left = max(dyn_min, tug_min)
        overlap_right = min(dyn_max, tug_max)

        if overlap_left >= overlap_right:
            return None

        return (overlap_left, overlap_right)

    @staticmethod
    def find_zero_crossings(values, baseline=0.0, threshold=0.0001):
        """
        Поиск точек пересечения сигнала с базовой линией (нулем).
        
        Args:
            values: массив значений сигнала
            baseline: базовая линия (по умолчанию 0.0)
            threshold: порог для обнаружения пересечения
            
        Returns:
            list: список индексов точек пересечения
        """
        arr = np.asarray(values, dtype=float)
        n = len(arr)
        if n < 2:
            return []
        
        # Центрируем данные относительно baseline
        centered = arr - baseline
        
        crossings = []
        for i in range(n - 1):
            # Проверяем пересечение с нулем
            if centered[i] * centered[i + 1] < 0:
                # Точное пересечение между i и i+1
                crossings.append(i + 1)
            elif abs(centered[i]) < threshold and (i == 0 or abs(centered[i - 1]) >= threshold):
                # Сигнал на нуле
                crossings.append(i)
        
        return crossings

    @staticmethod
    def find_peak_ranges(time, values, baseline=0.0, min_gap_points=10, min_amplitude_fraction=0.15):
        """
        Определение диапазонов между точками пересечения с нулем.
        
        Args:
            time: массив времени
            values: массив значений сигнала (центрированный)
            baseline: базовая линия (по умолчанию 0.0)
            min_gap_points: минимальное количество точек между пересечениями
            min_amplitude_fraction: минимальная доля амплитуды от максимума для участка
            
        Returns:
            list: список кортежей (time_start, time_end, start_idx, end_idx)
        """
        crossings = SignalAnalyzer.find_zero_crossings(values, baseline)
        
        # Центрируем данные
        centered = np.asarray(values, dtype=float) - baseline
        
        if len(crossings) < 2:
            # Если меньше 2 пересечений, ищем участок с максимальной амплитудой
            max_amp = np.max(np.abs(centered))
            if max_amp > 0:
                # Находим индекс максимального отклонения
                max_idx = np.argmax(np.abs(centered))
                # Ищем ближайшие пересечения с нулем или границы
                left_idx = 0
                for i in range(max_idx, -1, -1):
                    if abs(centered[i]) < baseline * 0.01:
                        left_idx = i
                        break
                right_idx = len(values) - 1
                for i in range(max_idx, len(values)):
                    if abs(centered[i]) < baseline * 0.01:
                        right_idx = i
                        break
                return [(time[left_idx], time[right_idx], left_idx, right_idx)]
            return [(time[0], time[-1], 0, len(values) - 1)]
        
        ranges = []
        global_max_amp = np.max(np.abs(centered))
        
        for i in range(len(crossings) - 1):
            start_idx = crossings[i]
            end_idx = crossings[i + 1]
            
            # Проверяем минимальную длину диапазона
            if end_idx - start_idx < min_gap_points:
                continue
            
            # Проверяем амплитуду в диапазоне
            segment = centered[start_idx:end_idx + 1]
            segment_amp = np.max(np.abs(segment))
            
            # Отбираем только участки с значимой амплитудой
            if segment_amp >= min_amplitude_fraction * global_max_amp:
                ranges.append((time[start_idx], time[end_idx], start_idx, end_idx))
        
        # Если не нашли подходящих диапазонов, возвращаем весь диапазон
        if not ranges:
            return [(time[0], time[-1], 0, len(values) - 1)]
        
        return ranges
