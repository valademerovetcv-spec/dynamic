"""
Модуль для определения положения магнита по методу пересечений.
"""
import numpy as np


class MagnetLocator:
    """Класс для определения положения магнита по калибровочным данным."""

    @staticmethod
    def find_rising_indices(tug):
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

    @staticmethod
    def find_rising_range(disp, tug):
        """Восходящий участок тарировки: от минимума до пика."""
        disp = np.asarray(disp, dtype=float)
        if len(disp) == 0:
            return 0.0, 0.0
        min_idx, peak_idx = MagnetLocator.find_rising_indices(tug)
        left = float(disp[min_idx])
        right = float(disp[peak_idx])
        if left > right:
            left, right = right, left
        return left, right

    @staticmethod
    def merge_rising_ranges(ranges):
        """Пересечение восходящих диапазонов всех датчиков."""
        if not ranges:
            return 0.0, 0.0
        left = max(r[0] for r in ranges)
        right = min(r[1] for r in ranges)
        if left < right:
            return left, right
        return min(ranges, key=lambda r: r[1] - r[0])

    @staticmethod
    def common_rising_bounds(disp, tug_series):
        """Общее окно индексов восходящей ветки для нескольких датчиков."""
        disp = np.asarray(disp, dtype=float)
        starts, ends = [], []
        for tug in tug_series:
            mi, pi = MagnetLocator.find_rising_indices(tug)
            starts.append(mi)
            ends.append(pi)
        idx_start = max(starts)
        idx_end = min(ends)
        if idx_start > idx_end:
            idx_start, idx_end = starts[0], ends[0]
        return idx_start, idx_end

    @staticmethod
    def resolve_calib_by_intersections(disp, tug_dict):
        """
        Выбор датчика по методу вертикальных пересечений.
        
        Args:
            disp: массив перемещений
            tug_dict: словарь {имя_датчика: значения}
            
        Returns:
            dict: результаты анализа (magnet_x, selected_sensor, range_left, range_right, etc.)
        """
        disp = np.asarray(disp, dtype=float)
        tug_names = list(tug_dict.keys())
        tug_list = [np.asarray(tug_dict[n], dtype=float) for n in tug_names]

        if not tug_list:
            return {
                'magnet_x': None,
                'selected_sensor': None,
                'range_left': None,
                'range_right': None,
                'intersections': {},
                'all_intersections_x': [],
            }

        # Поиск диапазонов восходящих участков
        ranges = []
        for tug in tug_list:
            min_idx = int(np.argmin(tug))
            peak_idx = int(np.argmax(tug))
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

        # Центральные точки для анализа
        center_disp = [
            overlap_left + (overlap_right - overlap_left) * 0.25,
            overlap_left + (overlap_right - overlap_left) * 0.50,
            overlap_left + (overlap_right - overlap_left) * 0.75,
        ]

        levels = []
        for cd in center_disp:
            idx = int(np.argmin(np.abs(disp - cd)))
            for tug in tug_list:
                levels.append(float(tug[idx]))

        # Поиск точек пересечения для каждого датчика (векторизованный поиск)
        sensor_data = {}
        for name, tug in zip(tug_names, tug_list):
            x_points = []
            # Векторизованный поиск пересечений для всех уровней сразу
            for level in levels:
                diff = tug - level
                sign_changes = np.where(diff[:-1] * diff[1:] < 0)[0]
                
                for i in sign_changes:
                    x0, x1 = disp[i], disp[i + 1]
                    y0, y1 = tug[i], tug[i + 1]
                    if y1 != y0:
                        t = (level - y0) / (y1 - y0)
                        x_cross = x0 + t * (x1 - x0)
                        if overlap_left <= x_cross <= overlap_right:
                            x_points.append(float(x_cross))

            x_points = sorted(set(x_points))

            if len(x_points) >= 3:
                # Оптимизированный поиск лучшей группы через sliding window O(n) вместо O(n³)
                x_arr = np.array(x_points)
                best_spread = float('inf')
                best_group = []
                
                # Используем скользящее окно размером 3 - сложность O(n) вместо O(n³)
                for i in range(len(x_arr) - 2):
                    group = x_arr[i:i+3]
                    spread = group[-1] - group[0]
                    if spread < best_spread:
                        best_spread = spread
                        best_group = group.tolist()

                sensor_data[name] = {
                    'x_points': x_points,
                    'best_group': best_group,
                    'spread': best_spread,
                    'count': len(x_points),
                }
            else:
                sensor_data[name] = {
                    'x_points': x_points,
                    'best_group': x_points,
                    'spread': float('inf'),
                    'count': len(x_points),
                }

        # Выбор лучшего датчика
        best_sensor = min(sensor_data.items(), key=lambda x: x[1]['spread'])[0]
        best_data = sensor_data[best_sensor]

        # Определение диапазона
        if len(best_data['best_group']) >= 2:
            range_left = float(min(best_data['best_group']))
            range_right = float(max(best_data['best_group']))
        elif len(best_data['x_points']) >= 2:
            range_left = float(min(best_data['x_points']))
            range_right = float(max(best_data['x_points']))
        else:
            range_left = overlap_left
            range_right = overlap_right

        if range_left > range_right:
            range_left, range_right = range_right, range_left

        magnet_x = (range_left + range_right) / 2

        return {
            'magnet_x': magnet_x,
            'selected_sensor': best_sensor,
            'range_left': range_left,
            'range_right': range_right,
            'intersections': {name: {
                'x_points': data['x_points'],
                'best_group': data['best_group'],
                'spread': data['spread'],
                'count': data['count']
            } for name, data in sensor_data.items()},
            'all_intersections_x': list(best_data['x_points']),
        }

    @staticmethod
    def find_layer_overlap(disp, tug_dict):
        """Поиск области перекрытия для конкретного слоя."""
        ranges = [MagnetLocator.find_rising_range(disp, tv) for tv in tug_dict.values()]
        return MagnetLocator.merge_rising_ranges(ranges)
