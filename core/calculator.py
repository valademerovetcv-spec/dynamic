"""
Модуль для расчёта перемещений и обработки калибровочных данных.
"""
import numpy as np
import pandas as pd

from .interpolator import Interpolator
from .magnet_locator import MagnetLocator
from models.analyzers import SignalAnalyzer


class Calculator:
    """Класс для расчёта перемещений на основе калибровочных данных."""

    def __init__(self, data_loader):
        self.loader = data_loader

    def _find_rising_indices(self, tug):
        """Индексы минимума и пика на восходящем участке."""
        tug = np.asarray(tug, dtype=float)
        n = len(tug)
        if n == 0:
            return 0, 0
        peak_idx = int(np.argmax(tug))
        if peak_idx == 0:
            return 0, 0
        min_idx = int(np.argmin(tug[:peak_idx]))
        return min_idx, peak_idx

    def _find_rising_range(self, disp, tug):
        """Восходящий участок тарировки: от минимума до пика."""
        disp = np.asarray(disp, dtype=float)
        if len(disp) == 0:
            return 0.0, 0.0
        min_idx, peak_idx = self._find_rising_indices(tug)
        left = float(disp[min_idx])
        right = float(disp[peak_idx])
        if left > right:
            left, right = right, left
        return left, right

    def _merge_rising_ranges(self, ranges):
        """Пересечение восходящих диапазонов всех датчиков."""
        if not ranges:
            return 0.0, 0.0
        left = max(r[0] for r in ranges)
        right = min(r[1] for r in ranges)
        if left < right:
            return left, right
        return min(ranges, key=lambda r: r[1] - r[0])

    def _common_rising_bounds(self, disp, tug_series):
        """Общее окно индексов восходящей ветки для нескольких датчиков."""
        disp = np.asarray(disp, dtype=float)
        starts, ends = [], []
        for tug in tug_series:
            mi, pi = self._find_rising_indices(tug)
            starts.append(mi)
            ends.append(pi)
        idx_start = max(starts)
        idx_end = min(ends)
        if idx_start > idx_end:
            idx_start, idx_end = starts[0], ends[0]
        return idx_start, idx_end

    def _extract_rising_branch(self, disp, tug, range_left=None, range_right=None):
        """Точки только восходящей ветки между минимумом и пиком."""
        disp = np.asarray(disp, dtype=float)
        tug = np.asarray(tug, dtype=float)
        min_idx, peak_idx = self._find_rising_indices(tug)

        cal_disp = disp[min_idx:peak_idx + 1]
        cal_tug = tug[min_idx:peak_idx + 1]

        if range_left is not None:
            m = cal_disp >= range_left
            cal_disp = cal_disp[m]
            cal_tug = cal_tug[m]
        if range_right is not None:
            m = cal_disp <= range_right
            cal_disp = cal_disp[m]
            cal_tug = cal_tug[m]

        return cal_disp, cal_tug

    def _update_zero_and_baselines(self):
        """Обновление нулевой точки и базовых линий."""
        if not self.loader.result_channels:
            self.loader.channel_baselines = None
            self.loader.channel_mins = None
            self.loader.auto_zero_point = None
            self.loader.zero_point = None
            return

        self.loader.channel_baselines = {
            ch: SignalAnalyzer.find_baseline(data)
            for ch, data in self.loader.result_channels.items()
        }
        self.loader.channel_mins = self.loader.channel_baselines.copy()
        self.loader.auto_zero_point = min(self.loader.channel_baselines.values())
        self.loader.zero_point = (
            self.loader.manual_zero_point
            if self.loader.manual_zero_point is not None
            else self.loader.auto_zero_point
        )

    def set_manual_zero(self, value):
        """Установка ручной нулевой точки."""
        self.loader.manual_zero_point = float(value) if value is not None else None
        self._update_zero_and_baselines()

    def clear_manual_zero(self):
        """Сброс ручной нулевой точки."""
        self.loader.manual_zero_point = None
        self._update_zero_and_baselines()

    def _find_overlap_region(self):
        """Поиск области перекрытия калибровочных кривых."""
        ranges = [
            self._find_rising_range(self.loader.calib_disp, ch_data)
            for ch_data in self.loader.calib_channels.values()
        ]
        return self._merge_rising_ranges(ranges)

    def _find_layer_overlap(self, disp, tug_dict):
        """Поиск области перекрытия для конкретного слоя."""
        ranges = [self._find_rising_range(disp, tv) for tv in tug_dict.values()]
        return self._merge_rising_ranges(ranges)

    def set_layer_manual(self, layer_name, sensor=None, range_left=None, range_right=None):
        """Установка ручных параметров для слоя."""
        manual = self.loader._per_layer_manual.setdefault(layer_name, {})
        if sensor is not None:
            manual["sensor"] = sensor
        if range_left is not None:
            manual["range_left"] = float(range_left)
        if range_right is not None:
            manual["range_right"] = float(range_right)

    def clear_layer_manual(self, layer_name):
        """Сброс ручных параметров для слоя."""
        self.loader._per_layer_manual.pop(layer_name, None)

    def set_global_manual(self, sensor=None, range_left=None, range_right=None):
        """Установка глобальных ручных параметров."""
        if sensor is not None:
            self.loader._global_calib_manual["sensor"] = sensor
        if range_left is not None:
            self.loader._global_calib_manual["range_left"] = float(range_left)
        if range_right is not None:
            self.loader._global_calib_manual["range_right"] = float(range_right)

    def clear_global_manual(self):
        """Сброс глобальных ручных параметров."""
        self.loader._global_calib_manual.clear()

    def _trim_to_overlap(self, left_b=None, right_b=None):
        """Обрезка калибровочных данных до области перекрытия."""
        if self.loader.calib_disp is None or not self.loader.calib_channels:
            return np.array([])

        if left_b is None or right_b is None:
            auto_left, auto_right = self._find_overlap_region()
            left_b = left_b if left_b is not None else auto_left
            right_b = right_b if right_b is not None else auto_right
        if left_b > right_b:
            left_b, right_b = right_b, left_b

        self.loader._overlap_range = (left_b, right_b)

        tug_list = list(self.loader.calib_channels.values())
        idx_start, idx_end = self._common_rising_bounds(self.loader.calib_disp, tug_list)
        disp_rising = self.loader.calib_disp[idx_start:idx_end + 1]
        mask = (disp_rising >= left_b) & (disp_rising <= right_b)
        trimmed_disp = disp_rising[mask]

        self.loader.trimmed_calib = {}
        for ch_name, ch_data in self.loader.calib_channels.items():
            tug_rising = ch_data[idx_start:idx_end + 1]
            self.loader.trimmed_calib[ch_name] = tug_rising[mask].copy()

        return trimmed_disp

    def _central_level(self, tug):
        """Центральное значение сигнала датчика."""
        tug = np.asarray(tug, dtype=float)
        if len(tug) == 0:
            return 0.0
        return float(tug[len(tug) // 2])

    def _find_intersections_at_level(self, disp, tug, level):
        """Точки пересечения горизонтали y=level с кривой тарировки."""
        disp = np.asarray(disp, dtype=float)
        tug = np.asarray(tug, dtype=float)
        result = []
        for i in range(len(tug) - 1):
            if (tug[i] - level) * (tug[i + 1] - level) < 0:
                x0, x1 = disp[i], disp[i + 1]
                y0, y1 = tug[i], tug[i + 1]
                if y1 != y0:
                    t = (level - y0) / (y1 - y0)
                    result.append(float(x0 + t * (x1 - x0)))
        return result

    def _interp_linear(self, target, tug_vals, disp_vals):
        """Линейная интерполяция."""
        n = len(tug_vals)
        if n < 2:
            return None
        idx = np.argmin(np.abs(tug_vals - target))
        if idx == n - 1:
            t0, t1 = tug_vals[-2], tug_vals[-1]
            d0, d1 = disp_vals[-2], disp_vals[-1]
        else:
            t0, t1 = tug_vals[idx], tug_vals[idx + 1]
            d0, d1 = disp_vals[idx], disp_vals[idx + 1]
        res1 = t0 - t1
        if res1 == 0:
            return d0
        del1 = (d0 - d1) / res1
        del2 = target - t0
        del3 = del1 * del2
        return round(d0 + del3, 3)

    def _calc_single_channel(self, tugriki_vals, calib_tugriki, calib_disp):
        """Расчёт перемещения для одного канала."""
        result = np.empty(len(tugriki_vals))
        for i, t in enumerate(tugriki_vals):
            d = self._interp_linear(t, calib_tugriki, calib_disp)
            result[i] = d if d is not None else 0.0
        return np.round(result, 3)

    def calculate(self, selected_calib=None):
        """Основной метод расчёта перемещений."""
        if self.loader.dynamics_channels and self.loader.calib_channels:
            return self.calculate_all_channels(selected_calib)

        src_cols = list(self.loader.source_data.columns)
        cal_cols = list(self.loader.calib_data.columns)
        src_time = src_cols[0]
        src_val = src_cols[1] if len(src_cols) > 1 else src_cols[0]
        cal_disp = cal_cols[0]
        cal_val = cal_cols[1] if len(cal_cols) > 1 else cal_cols[0]

        tugriki_vals = self.loader.source_data[src_val].to_numpy(dtype=float)
        calib_disp_vals = self.loader.calib_data[cal_disp].to_numpy(dtype=float)
        calib_tugriki_vals = self.loader.calib_data[cal_val].to_numpy(dtype=float)
        result_disp = self._calc_single_channel(tugriki_vals, calib_tugriki_vals, calib_disp_vals)
        self.loader.result_df = pd.DataFrame({
            "Время, мсек": self.loader.source_data[src_time].values,
            "Перемещение, мм": result_disp
        })
        self.loader.result_channels = {cal_val: result_disp}
        self._update_zero_and_baselines()
        return self.loader.result_df

    def _resolve_calib_by_intersections(self, disp, tug_dict):
        """Выбор датчика по методу вертикальных пересечений."""
        return MagnetLocator.resolve_calib_by_intersections(disp, tug_dict)

    def _find_magnet_by_intersections(self):
        """Найти положение магнита по пересечениям горизонталей."""
        if self.loader.calib_disp is None or self.loader.calib_channels is None:
            return

        resolved = self._resolve_calib_by_intersections(
            self.loader.calib_disp, self.loader.calib_channels
        )
        self.loader._magnet_intersections = resolved['intersections']
        self.loader._magnet_x = resolved['magnet_x']
        self.loader._selected_calib_auto = resolved['selected_sensor']
        self.loader._magnet_auto_range = (
            resolved['range_left'], resolved['range_right']
        ) if resolved['range_left'] is not None else None

        if self.loader._magnet_x is not None:
            self.loader.magnet_position = np.full(
                len(self.loader.dynamics_time), self.loader._magnet_x
            )
            sensor = resolved['selected_sensor'] or "?"
            self.loader.magnet_info = (
                f"Магнит X={self.loader._magnet_x:.1f} мм  |  "
                f"Датчик: {sensor}  |  "
                f"Диапазон: {resolved['range_left']:.1f}—{resolved['range_right']:.1f} мм"
            )
        else:
            self.loader.magnet_position = np.full(len(self.loader.dynamics_time), np.nan)
            self.loader.magnet_info = "Не удалось определить положение магнита"
            self.loader._magnet_x = None

    def calculate_all_channels(self, selected_calib=None):
        """Расчёт перемещений для всех каналов."""
        manual = self.loader._global_calib_manual

        self._find_magnet_by_intersections()
        mag_x = self.loader._magnet_x

        if getattr(self.loader, '_magnet_auto_range', None):
            auto_left, auto_right = self.loader._magnet_auto_range
        else:
            auto_left, auto_right = self._find_overlap_region()

        range_left = manual.get("range_left", auto_left)
        range_right = manual.get("range_right", auto_right)
        if range_left > range_right:
            range_left, range_right = range_right, range_left

        disp = self._trim_to_overlap(range_left, range_right)

        cal_names = list(self.loader.trimmed_calib.keys())

        self.loader.calib_branches = {}
        for cn in cal_names:
            tug = self.loader.trimmed_calib[cn]
            peak_idx = np.argmax(tug)
            peak_disp = disp[peak_idx]
            left_mask = disp <= peak_disp
            right_mask = disp >= peak_disp
            self.loader.calib_branches[cn] = {
                'left_disp': disp[left_mask],
                'left_tug': tug[left_mask],
                'right_disp': disp[right_mask],
                'right_tug': tug[right_mask],
                'peak_pos': peak_disp,
                'peak_val': tug[peak_idx],
                'full_disp': disp,
                'full_tug': tug,
            }

        best_cal = getattr(self.loader, '_selected_calib_auto', None)
        if best_cal is None and cal_names:
            best_cal = cal_names[0]

        manual_sensor = manual.get("sensor")
        if selected_calib and selected_calib in cal_names:
            best_cal = selected_calib
        elif manual_sensor and manual_sensor in cal_names:
            best_cal = manual_sensor

        self.loader._global_calib_info = {
            "sensor": best_cal,
            "range_left": range_left,
            "range_right": range_right,
            "auto_sensor": getattr(self.loader, '_selected_calib_auto', best_cal),
            "auto_range_left": auto_left,
            "auto_range_right": auto_right,
            "manual_sensor": manual_sensor is not None,
            "manual_range": "range_left" in manual or "range_right" in manual,
            "magnet_x": mag_x,
        }

        br = self.loader.calib_branches[best_cal]
        if mag_x is not None and not np.isnan(mag_x):
            branch_side = "левая" if mag_x <= br['peak_pos'] else "правая"
            self.loader.magnet_info += f"  |  Датчик Холла: {best_cal} ({branch_side} ветка)"

        time_vals = self.loader.dynamics_time
        dyn_names = list(self.loader.dynamics_channels.keys())
        self.loader.result_channels = {}

        for dn in dyn_names:
            tugriki_vals = self.loader.dynamics_channels[dn]
            result_disp = np.empty(len(tugriki_vals))
            mx = mag_x if (mag_x is not None and not np.isnan(mag_x)) else br['peak_pos']
            for j, t in enumerate(tugriki_vals):
                if mx <= br['peak_pos']:
                    d = Interpolator.interp_linear(t, br['left_tug'], br['left_disp'])
                else:
                    d = Interpolator.interp_linear(t, br['right_tug'], br['right_disp'])
                if d is None:
                    d = Interpolator.interp_linear(t, br['full_tug'], br['full_disp'])
                result_disp[j] = d if d is not None else 0.0
            self.loader.result_channels[dn] = np.round(result_disp, 3)

        # Сохраняем сырые результаты для графика "Перемещение от времени" и анализа деформаций
        self.loader.result_channels_raw = self.loader.result_channels.copy()

        if self.loader.result_channels:
            self._update_zero_and_baselines()
            key = list(self.loader.result_channels.keys())[0]
            self.loader.result_df = pd.DataFrame({
                "Время, мсек": time_vals,
                "Перемещение, мм": self.loader.result_channels[key]
            })
        else:
            self.loader.zero_point = None
            self.loader.auto_zero_point = None
            self.loader.channel_mins = None
            self.loader.channel_baselines = None
            self.loader.result_df = pd.DataFrame()
        return self.loader.result_df

    def calculate_per_layer_magnet(self):
        """Расчёт положения магнита для каждого слоя."""
        self.loader._per_layer_magnet_x = {}
        self.loader._per_layer_all_intersections = {}
        self.loader._per_layer_selected_sensor = {}

        for ch_name, cal in self.loader.per_layer_calib.items():
            disp = cal["disp"]
            tug_dict = cal["tug"]
            tug_names = list(tug_dict.keys())
            tug_list = list(tug_dict.values())

            if len(tug_list) < 2:
                continue

            ranges = []
            for tug_vals in tug_list:
                min_idx = int(np.argmin(tug_vals))
                peak_idx = int(np.argmax(tug_vals))
                left = float(disp[min_idx])
                right = float(disp[peak_idx])
                if left > right:
                    left, right = right, left
                ranges.append((left, right))

            overlap_left = max(r[0] for r in ranges)
            overlap_right = min(r[1] for r in ranges)

            if overlap_left >= overlap_right:
                narrowest = min(ranges, key=lambda r: r[1] - r[0])
                overlap_left = narrowest[0]
                overlap_right = narrowest[1]

            center_disp = [
                overlap_left + (overlap_right - overlap_left) * 0.25,
                overlap_left + (overlap_right - overlap_left) * 0.50,
                overlap_left + (overlap_right - overlap_left) * 0.75,
            ]

            levels = []
            for cd in center_disp:
                idx = int(np.argmin(np.abs(disp - cd)))
                for tug_vals in tug_list:
                    levels.append(float(tug_vals[idx]))

            sensor_data = {}
            for s_name, tug_vals in zip(tug_names, tug_list):
                x_points = []
                for level in levels:
                    for i in range(len(tug_vals) - 1):
                        if (tug_vals[i] - level) * (tug_vals[i + 1] - level) < 0:
                            x0, x1 = disp[i], disp[i + 1]
                            y0, y1 = tug_vals[i], tug_vals[i + 1]
                            if y1 != y0:
                                t = (level - y0) / (y1 - y0)
                                x_cross = x0 + t * (x1 - x0)
                                if overlap_left <= x_cross <= overlap_right:
                                    x_points.append(float(x_cross))

                x_points = sorted(set(x_points))

                if len(x_points) >= 3:
                    best_spread = float('inf')
                    best_group = []
                    for i in range(len(x_points) - 2):
                        for j in range(i + 1, len(x_points) - 1):
                            for k in range(j + 1, len(x_points)):
                                group = [x_points[i], x_points[j], x_points[k]]
                                spread = max(group) - min(group)
                                if spread < best_spread:
                                    best_spread = spread
                                    best_group = group

                    sensor_data[s_name] = {
                        'x_points': x_points,
                        'best_group': best_group,
                        'spread': best_spread,
                        'count': len(x_points),
                    }
                else:
                    sensor_data[s_name] = {
                        'x_points': x_points,
                        'best_group': x_points,
                        'spread': float('inf'),
                        'count': len(x_points),
                    }

            best_sensor = min(sensor_data.items(), key=lambda x: x[1]['spread'])[0]
            best_data = sensor_data[best_sensor]

            if len(best_data['best_group']) >= 2:
                magnet_x = (min(best_data['best_group']) + max(best_data['best_group'])) / 2
            elif len(best_data['x_points']) >= 2:
                magnet_x = (min(best_data['x_points']) + max(best_data['x_points'])) / 2
            else:
                magnet_x = (overlap_left + overlap_right) / 2

            self.loader._per_layer_magnet_x[ch_name] = float(magnet_x)
            self.loader._per_layer_selected_sensor[ch_name] = best_sensor
            self.loader._per_layer_all_intersections[ch_name] = best_data['x_points']

    def calculate_per_layer(self):
        """Расчёт перемещений для каждого слоя."""
        if not self.loader.per_layer_calib or not self.loader.dynamics_channels:
            return self.loader.result_df

        time_vals = self.loader.dynamics_time
        self.loader.magnet_info = ""
        self.loader.result_channels = {}
        self.loader._per_layer_calib_info = {}
        
        # Шаг 1: Рассчитываем перемещения для каждого слоя с индивидуальным нулём
        raw_results = {}
        for dn, tugriki_vals in self.loader.dynamics_channels.items():
            if dn not in self.loader.per_layer_calib:
                continue
            cal = self.loader.per_layer_calib[dn]
            disp = cal["disp"]
            tug_dict = cal["tug"]

            auto_range = self.loader._per_layer_auto_range.get(dn)
            if auto_range:
                auto_left, auto_right = auto_range
            else:
                auto_left, auto_right = self._find_layer_overlap(disp, tug_dict)
            auto_sensor = self.loader._per_layer_selected_sensor.get(dn)
            if not auto_sensor or auto_sensor not in tug_dict:
                auto_sensor = list(tug_dict.keys())[0]

            manual = self.loader._per_layer_manual.get(dn, {})
            range_left = manual.get("range_left", auto_left)
            range_right = manual.get("range_right", auto_right)
            if range_left > range_right:
                range_left, range_right = range_right, range_left

            manual_sensor = manual.get("sensor")
            if manual_sensor and manual_sensor in tug_dict:
                selected = manual_sensor
            elif auto_sensor in tug_dict:
                selected = auto_sensor
            else:
                selected = list(tug_dict.keys())[0]

            tug = tug_dict[selected]
            cal_disp, cal_tug = Interpolator.extract_rising_branch(
                disp, tug, range_left=range_left, range_right=range_right
            )
            
            # Вычисляем значения для статистики: первое плато, пик, второе плато
            # Первое плато - среднее значение до пика (в начале диапазона)
            # Пик - максимальное значение в диапазоне калибровки
            # Второе плато - среднее значение после пика
            
            # Находим индекс пика в калибровочных данных
            peak_idx = np.argmax(cal_disp)
            
            # Первое плато - среднее значение в первой трети диапазона до пика
            plateau1_end = max(1, peak_idx // 3)
            plateau1_val = float(np.mean(cal_disp[:plateau1_end])) if plateau1_end > 0 else float(cal_disp[0])
            
            # Пик - максимальное значение
            peak_val = float(cal_disp[peak_idx])
            
            # Второе плато - среднее значение в последней трети диапазона после пика
            plateau2_start = min(len(cal_disp) - 1, peak_idx + (len(cal_disp) - peak_idx) * 2 // 3)
            plateau2_val = float(np.mean(cal_disp[plateau2_start:])) if plateau2_start < len(cal_disp) else float(cal_disp[-1])

            self.loader._per_layer_calib_info[dn] = {
                "sensor": selected,
                "range_left": float(range_left),
                "range_right": float(range_right),
                "auto_sensor": auto_sensor,
                "auto_range_left": float(auto_left),
                "auto_range_right": float(auto_right),
                "manual_sensor": manual_sensor is not None,
                "manual_range": "range_left" in manual or "range_right" in manual,
                "magnet_x": self.loader._per_layer_magnet_x.get(dn),
                "plateau1": plateau1_val,
                "peak": peak_val,
                "plateau2": plateau2_val,
            }

            # Расчёт перемещения с использованием интерполяции
            result_disp = Interpolator.calc_single_channel(tugriki_vals, cal_tug, cal_disp)
            raw_results[dn] = np.round(result_disp, 3)
        
        # Шаг 2: Сохраняем сырые результаты для графика "Перемещение от времени"
        # (без приведения к локальному нулю)
        self.loader.result_channels_raw = raw_results.copy()
        
        # Шаг 3: Для каждого слоя находим свой baseline (усредненный ноль)
        layer_baselines = {}
        for dn, disp_vals in raw_results.items():
            layer_baselines[dn] = SignalAnalyzer.find_baseline(disp_vals)
        
        # Шаг 4: Центрируем каждый слой относительно своего нуля для графика "Пиковые значения"
        centered_results = {}
        for dn, disp_vals in raw_results.items():
            centered_results[dn] = disp_vals - layer_baselines[dn]
        
        # Шаг 5: Находим общий ноль для отображения (минимум из всех baseline'ов)
        if layer_baselines:
            common_zero = min(layer_baselines.values())
        else:
            common_zero = 0.0
        
        # Шаг 6: Сохраняем результаты и обновляем информацию о нулях
        # result_channels используется для графика "Пиковые значения" (с центрированием)
        self.loader.result_channels = centered_results
        # result_channels_raw используется для графика "Перемещение от времени" (без центрирования)
        self.loader.channel_baselines = layer_baselines
        self.loader.channel_mins = layer_baselines.copy()
        self.loader.auto_zero_point = common_zero
        self.loader.zero_point = (
            self.loader.manual_zero_point
            if self.loader.manual_zero_point is not None
            else self.loader.auto_zero_point
        )

        if self.loader.result_channels_raw:
            key = list(self.loader.result_channels_raw.keys())[0]
            # Для result_df используем исходные данные (без центрирования) для таблицы "Результат расчёта"
            self.loader.result_df = pd.DataFrame({
                "Время, мсек": time_vals,
                "Перемещение, мм": self.loader.result_channels_raw[key]
            })
        else:
            self.loader.zero_point = None
            self.loader.auto_zero_point = None
            self.loader.channel_mins = None
            self.loader.channel_baselines = None
            self.loader.result_df = pd.DataFrame()
        return self.loader.result_df
