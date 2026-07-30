import numpy as np
import pandas as pd
import openpyxl


class DataLoader:
    def __init__(self):
        self.source_data = None
        self.calib_data = None
        self.result_df = None
        self.dynamics_channels = None
        self.calib_channels = None
        self.dynamics_time = None
        self.calib_disp = None
        self.result_channels = None
        self.magnet_position = None
        self.magnet_info = ""
        self.calib_branches = None
        self.trimmed_calib = None
        self._magnet_intersections = {}
        self._magnet_x = None
        self.temp_data = None
        self.temp_channels = None
        self.temp_time = None
        self.zero_point = None
        self.auto_zero_point = None
        self.manual_zero_point = None
        self.channel_mins = None
        self.channel_baselines = None
        self.per_layer_calib = {}  # {layer_name: {"disp": array, "tug": array}}
        self._per_layer_magnet_x = {}
        self._per_layer_all_intersections = {}
        self._per_layer_selected_sensor = {}
        self._per_layer_intersections = {}
        self._per_layer_auto_range = {}
        self._magnet_auto_range = None
        self._per_layer_calib_info = {}  # {layer: {sensor, range_left, range_right, auto_sensor, auto_range}}
        self._per_layer_manual = {}  # {layer: {sensor, range_left, range_right}}
        self._global_calib_info = {}  # sensor, range_left, range_right (old multi-channel mode)
        self._global_calib_manual = {}  # {sensor, range_left, range_right}
        self._overlap_range = None  # (left, right) used in trimmed calib

    def load_excel(self, path):
        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb.active

        # Read row 1 and row 2 to find sections
        max_col = ws.max_column or 25
        row1 = [ws.cell(row=1, column=c).value for c in range(1, max_col + 1)]
        row2 = [ws.cell(row=2, column=c).value for c in range(1, max_col + 1)]

        # Find calibration section: first column where row 2 contains "Перемещение"
        cal_section = None
        for c, name in enumerate(row2):
            if name and "Перемещение" in str(name):
                cal_section = c  # 0-based
                break

        # Find result section: first "Динамика в мм" in row 1
        res_section = None
        for c, val in enumerate(row1):
            if val == "Динамика в мм":
                res_section = c  # 0-based
                break

        # If no calibration found, check if this is an old-format file
        if cal_section is None:
            wb.close()
            return self._load_excel_legacy(path)

        # Dynamics section: everything before cal_section
        dyn_section = 0

        # === Read dynamics channels ===
        # Time is always at dyn_section + 1 (1-based)
        time_col = []
        for row in ws.iter_rows(min_row=3, max_row=ws.max_row,
                                min_col=dyn_section + 1, max_col=dyn_section + 1,
                                values_only=True):
            if row[0] is not None:
                time_col.append(row[0])
        n_time = len(time_col)

        # Dynamics channels are columns between time and cal_section
        dyn_channels = {}
        for c in range(dyn_section + 2, cal_section + 1):  # 1-based cols
            ch_name = ws.cell(row=2, column=c).value
            if not ch_name:
                continue
            vals = []
            for row in ws.iter_rows(min_row=3, max_row=ws.max_row,
                                    min_col=c, max_col=c, values_only=True):
                if row[0] is not None:
                    vals.append(float(row[0]))
            n = min(n_time, len(vals))
            if n > 0 and not all(v == 0 for v in vals[:n]):
                dyn_channels[ch_name] = np.array(vals[:n])

        self.dynamics_time = np.array(time_col[:n_time]) if n_time > 0 else None
        self.dynamics_channels = dyn_channels if dyn_channels else None

        # Build source_data
        if self.dynamics_time is not None and self.dynamics_channels:
            first_key = list(self.dynamics_channels.keys())[0]
            self.source_data = pd.DataFrame({
                "Время, мсек": self.dynamics_time,
                "Слои": self.dynamics_channels[first_key]
            })
        elif n_time > 0:
            self.source_data = pd.DataFrame({"Время, мсек": self.dynamics_time})
        else:
            self.source_data = None

        # === Read calibration data ===
        # First column at cal_section is displacement
        cal_disp = []
        for row in ws.iter_rows(min_row=3, max_row=ws.max_row,
                                min_col=cal_section + 1, max_col=cal_section + 1,
                                values_only=True):
            if row[0] is not None:
                cal_disp.append(float(row[0]))
        nc = len(cal_disp)
        cal_disp_name = ws.cell(row=2, column=cal_section + 1).value or "Перемещение, мм"

        # Calibration channels are columns after displacement until res_section
        end_cal = res_section if res_section else max_col
        cal_channels = {}
        for c in range(cal_section + 2, end_cal + 1):  # 1-based cols
            ch_name = ws.cell(row=2, column=c).value
            if not ch_name:
                continue
            ch_vals = []
            for row in ws.iter_rows(min_row=3, max_row=ws.max_row,
                                    min_col=c, max_col=c, values_only=True):
                if row[0] is not None:
                    ch_vals.append(float(row[0]))
            n = min(nc, len(ch_vals))
            if n > 0 and not all(v == 0 for v in ch_vals[:n]):
                cal_channels[ch_name] = np.round(np.array(ch_vals[:n]), 3)

        self.calib_disp = np.array(cal_disp[:nc]) if nc > 0 else None
        self.calib_channels = cal_channels if cal_channels else None

        if self.calib_disp is not None and self.calib_channels:
            first_key = list(self.calib_channels.keys())[0]
            self.calib_data = pd.DataFrame({
                cal_disp_name: self.calib_disp,
                first_key: self.calib_channels[first_key]
            })
        elif nc > 0:
            self.calib_data = pd.DataFrame({cal_disp_name: self.calib_disp})
        else:
            self.calib_data = None

        # === Read result data ===
        if res_section is not None:
            # Time is at res_section + 1 (1-based)
            res_time = []
            for row in ws.iter_rows(min_row=3, max_row=ws.max_row,
                                    min_col=res_section + 1, max_col=res_section + 1,
                                    values_only=True):
                if row[0] is not None:
                    res_time.append(row[0])
            nr = len(res_time)

            # Read all result channels starting from res_section + 2 (1-based)
            self.result_channels = {}
            for c in range(res_section + 2, max_col + 1):  # 1-based
                ch_name = ws.cell(row=2, column=c).value
                if not ch_name:
                    continue
                ch_vals = []
                for row in ws.iter_rows(min_row=3, max_row=ws.max_row,
                                        min_col=c, max_col=c, values_only=True):
                    if row[0] is not None:
                        ch_vals.append(float(row[0]))
                n = min(nr, len(ch_vals))
                if n > 0:
                    self.result_channels[ch_name] = np.round(np.array(ch_vals[:n]), 3)

            if nr > 0:
                # Build result_df from first channel
                first_key = list(self.result_channels.keys())[0] if self.result_channels else None
                self.result_df = pd.DataFrame({
                    "Время, мсек": res_time[:nr],
                    "Перемещение, мм": self.result_channels[first_key][:nr] if first_key else [0]*nr
                })
            else:
                self.result_df = None
                self.result_channels = {}
        else:
            self.result_df = None
            self.result_channels = {}

        wb.close()
        return self.source_data, self.calib_data

    def _load_excel_legacy(self, path):
        """Fallback for old format files without section headers."""
        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb.active

        time_col, tugriki_col = [], []
        for row in ws.iter_rows(min_row=3, max_row=ws.max_row, min_col=1, max_col=2, values_only=True):
            if row[0] is not None and row[1] is not None:
                time_col.append(row[0])
                tugriki_col.append(row[1])
        n = min(len(time_col), len(tugriki_col))
        self.source_data = pd.DataFrame({
            "Время, мсек": time_col[:n],
            "Датчик Холла": tugriki_col[:n]
        })

        calib_disp, calib_tugriki = [], []
        for row in ws.iter_rows(min_row=3, max_row=ws.max_row, min_col=4, max_col=5, values_only=True):
            if row[0] is not None and row[1] is not None:
                calib_disp.append(row[0])
                calib_tugriki.append(row[1])
        nc = min(len(calib_disp), len(calib_tugriki))
        self.calib_data = pd.DataFrame({
            "Перемещение, мм": calib_disp[:nc],
            "Датчик Холла": calib_tugriki[:nc]
        })

        wb.close()
        return self.source_data, self.calib_data

    def load_dynamics_csv(self, path):
        df = pd.read_csv(path, sep=";", header=None, decimal=",")
        df = df.sort_values(by=0).reset_index(drop=True)
        time_col = df.iloc[:, 0].values
        self.dynamics_time = time_col
        self.dynamics_channels = {}
        for i in range(1, df.shape[1]):
            col_name = f"Слой {i}"
            ch_vals = df.iloc[:, i].values.astype(float)
            if np.all(ch_vals == 0):
                continue
            self.dynamics_channels[col_name] = ch_vals
        self.source_data = pd.DataFrame({
            "Время, мсек": time_col,
            "Слои": df.iloc[:, 1].values
        })
        return self.dynamics_time, self.dynamics_channels

    def load_calibration_csv(self, path):
        df = pd.read_csv(path, sep=";", header=None, decimal=",")
        df = df.sort_values(by=0).reset_index(drop=True)
        disp_col = np.round(df.iloc[:, 0].values.astype(float), 3)
        self.calib_disp = disp_col
        self.calib_channels = {}
        for i in range(1, df.shape[1]):
            col_name = f"Слой {i}"
            ch_vals = np.round(df.iloc[:, i].values.astype(float), 3)
            if np.all(ch_vals == 0):
                continue
            self.calib_channels[col_name] = ch_vals
        self.calib_data = pd.DataFrame({
            "Перемещение, мм": disp_col,
            "Датчик Холла": df.iloc[:, 1].values
        })
        return self.calib_disp, self.calib_channels

    def load_dynamics_xlsx(self, path):
        df = pd.read_excel(path, header=None)
        df = df.sort_values(by=0).reset_index(drop=True)
        time_col = df.iloc[:, 0].values
        self.dynamics_time = time_col
        self.dynamics_channels = {}
        for i in range(1, df.shape[1]):
            col_name = f"Слой {i}"
            ch_vals = df.iloc[:, i].values.astype(float)
            if np.all(ch_vals == 0):
                continue
            self.dynamics_channels[col_name] = ch_vals
        self.source_data = pd.DataFrame({
            "Время, мсек": time_col,
            "Слои": df.iloc[:, 1].values
        })
        return self.dynamics_time, self.dynamics_channels

    def load_calibration_xlsx(self, path):
        df = pd.read_excel(path, header=None)
        df = df.sort_values(by=0).reset_index(drop=True)
        disp_col = np.round(df.iloc[:, 0].values.astype(float), 3)
        self.calib_disp = disp_col
        self.calib_channels = {}
        for i in range(1, df.shape[1]):
            col_name = f"Слой {i}"
            ch_vals = np.round(df.iloc[:, i].values.astype(float), 3)
            if np.all(ch_vals == 0):
                continue
            self.calib_channels[col_name] = ch_vals
        self.calib_data = pd.DataFrame({
            "Перемещение, мм": disp_col,
            "Датчик Холла": df.iloc[:, 1].values
        })
        return self.calib_disp, self.calib_channels

    def load_calibration_for_layer(self, path, layer_name):
        if path.lower().endswith('.xlsx'):
            df = pd.read_excel(path, header=None)
        else:
            df = pd.read_csv(path, sep=";", header=None, decimal=",")
        df = df.sort_values(by=0).reset_index(drop=True)
        disp_col = np.round(df.iloc[:, 0].values.astype(float), 3)
        tug_cols = {}
        for i in range(1, df.shape[1]):
            col_name = f"Датчик Холла {i}"
            vals = np.round(df.iloc[:, i].values.astype(float), 3)
            if not np.all(vals == 0):
                tug_cols[col_name] = vals
        self.per_layer_calib[layer_name] = {"disp": disp_col, "tug": tug_cols}

    def load_temperature_csv(self, path):
        df = pd.read_csv(path, sep=";", header=0, decimal=",")
        df.columns = [c.strip() for c in df.columns]
        date_col = df.columns[0]
        dates = pd.to_datetime(df[date_col], format="%d.%m.%Y %H:%M")
        self.temp_time = dates
        self.temp_channels = {}
        idx = 1
        for col in df.columns[1:]:
            vals = pd.to_numeric(df[col], errors="coerce").values
            if np.all(vals == 0):
                continue
            self.temp_channels[f"Слой {idx}"] = vals
            idx += 1
        self.temp_data = df.iloc[:, 1:].copy()
        return self.temp_time, self.temp_channels

    def load_temperature_xlsx(self, path):
        df = pd.read_excel(path, header=0)
        df.columns = [c.strip() for c in df.columns]
        date_col = df.columns[0]
        dates = pd.to_datetime(df[date_col], format="%d.%m.%Y %H:%M", errors="coerce")
        if dates.isna().all():
            dates = pd.to_datetime(df[date_col], errors="coerce")
        self.temp_time = dates
        self.temp_channels = {}
        idx = 1
        for col in df.columns[1:]:
            vals = pd.to_numeric(df[col], errors="coerce").values
            if np.all(vals == 0):
                continue
            self.temp_channels[f"Слой {idx}"] = vals
            idx += 1
        self.temp_data = df.iloc[:, 1:].copy()
        return self.temp_time, self.temp_channels

    def _find_baseline(self, values, max_std=0.02, min_fraction=0.05):
        """Среднее на самом длинном участке с мелкими колебаниями в нижней части сигнала."""
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

        best_mean = None
        best_len = 0
        step = 1 if n <= 4000 else max(1, n // 4000)

        for start in range(0, n - min_len + 1, step):
            end = start + min_len
            seg = arr[start:end]
            seg_mean = float(np.mean(seg))
            if np.std(seg) > max_std or seg_mean > lower_ceiling:
                continue
            while end < n:
                seg = arr[start:end + 1]
                if np.std(seg) > max_std or float(np.mean(seg)) > lower_ceiling:
                    break
                end += 1
            length = end - start
            if length > best_len:
                best_len = length
                best_mean = float(np.mean(arr[start:end]))

        if best_mean is not None:
            return best_mean

        low_n = max(int(n * 0.1), 5)
        return float(np.mean(np.sort(arr)[:low_n]))

    def _find_rising_indices(self, tug):
        """Индексы минимума и пика на восходящем участке (минимум строго до пика)."""
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
        """Восходящий участок тарировки: от минимума до пика (без ската вниз)."""
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
        # Нет пересечения — самый узкий восходящий участок (без объединения со скатом)
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
        if not self.result_channels:
            self.channel_baselines = None
            self.channel_mins = None
            self.auto_zero_point = None
            self.zero_point = None
            return

        self.channel_baselines = {
            ch: self._find_baseline(data)
            for ch, data in self.result_channels.items()
        }
        self.channel_mins = self.channel_baselines.copy()
        self.auto_zero_point = min(self.channel_baselines.values())
        self.zero_point = (
            self.manual_zero_point
            if self.manual_zero_point is not None
            else self.auto_zero_point
        )

    def set_manual_zero(self, value):
        self.manual_zero_point = float(value) if value is not None else None
        self._update_zero_and_baselines()

    def clear_manual_zero(self):
        self.manual_zero_point = None
        self._update_zero_and_baselines()

    def _find_overlap_region(self):
        ranges = [
            self._find_rising_range(self.calib_disp, ch_data)
            for ch_data in self.calib_channels.values()
        ]
        return self._merge_rising_ranges(ranges)

    def _find_layer_overlap(self, disp, tug_dict):
        ranges = [self._find_rising_range(disp, tv) for tv in tug_dict.values()]
        return self._merge_rising_ranges(ranges)

    def set_layer_manual(self, layer_name, sensor=None, range_left=None, range_right=None):
        manual = self._per_layer_manual.setdefault(layer_name, {})
        if sensor is not None:
            manual["sensor"] = sensor
        if range_left is not None:
            manual["range_left"] = float(range_left)
        if range_right is not None:
            manual["range_right"] = float(range_right)

    def clear_layer_manual(self, layer_name):
        self._per_layer_manual.pop(layer_name, None)

    def set_global_manual(self, sensor=None, range_left=None, range_right=None):
        if sensor is not None:
            self._global_calib_manual["sensor"] = sensor
        if range_left is not None:
            self._global_calib_manual["range_left"] = float(range_left)
        if range_right is not None:
            self._global_calib_manual["range_right"] = float(range_right)

    def clear_global_manual(self):
        self._global_calib_manual.clear()

    def _trim_to_overlap(self, left_b=None, right_b=None):
        if self.calib_disp is None or not self.calib_channels:
            return np.array([])

        if left_b is None or right_b is None:
            auto_left, auto_right = self._find_overlap_region()
            left_b = left_b if left_b is not None else auto_left
            right_b = right_b if right_b is not None else auto_right
        if left_b > right_b:
            left_b, right_b = right_b, left_b

        self._overlap_range = (left_b, right_b)

        tug_list = list(self.calib_channels.values())
        idx_start, idx_end = self._common_rising_bounds(self.calib_disp, tug_list)
        disp_rising = self.calib_disp[idx_start:idx_end + 1]
        mask = (disp_rising >= left_b) & (disp_rising <= right_b)
        trimmed_disp = disp_rising[mask]

        self.trimmed_calib = {}
        for ch_name, ch_data in self.calib_channels.items():
            tug_rising = ch_data[idx_start:idx_end + 1]
            self.trimmed_calib[ch_name] = tug_rising[mask].copy()

        return trimmed_disp

    def _find_magnet_position(self):
        disp = self._trim_to_overlap()
        n_points = len(self.dynamics_time)
        positions = np.full(n_points, np.nan)
        cal_names = list(self.trimmed_calib.keys())

        self._magnet_intersections = {}

        for i in range(n_points):
            displacements = []
            for cn in cal_names:
                if i >= len(self.trimmed_calib[cn]):
                    continue
                sig = self.trimmed_calib[cn][i]
                tug = self.trimmed_calib[cn]
                d = self._interp_linear(sig, tug, disp)
                if d is not None:
                    displacements.append(d)

            if len(displacements) >= 2:
                positions[i] = np.mean(displacements)

        self.magnet_position = positions
        valid = positions[~np.isnan(positions)]
        if len(valid) > 0:
            mn, mx = np.nanmin(valid), np.nanmax(valid)
            self.magnet_info = f"Магнит: X={mn:.1f}—{mx:.1f} мм (область перекрытия)"
        else:
            self.magnet_info = "Не удалось определить положение магнита"

    def _central_level(self, tug):
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

    def _resolve_calib_by_intersections(self, disp, tug_dict):
        """
        Выбор датчика по методу вертикальных пересечений.
        
        Алгоритм:
        1. Находим область перекрытия всех датчиков (между мин и макс перемещения)
        2. Берём три центральные точки по перемещению (25%, 50%, 75% от диапазона)
        3. Для каждой точки получаем значения всех датчиков
        4. Проводим горизонтальные линии на уровнях этих значений
        5. Для каждого датчика находим все точки пересечения с этими линиями
        6. Выбираем датчик, у которого точки пересечения наиболее вертикальны
        (имеют минимальный разброс по X)
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
        
        # 1. Находим область перекрытия всех датчиков (между мин и макс перемещения)
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
        
        # 2. Берём три центральные точки по перемещению
        center_disp = [
            overlap_left + (overlap_right - overlap_left) * 0.25,
            overlap_left + (overlap_right - overlap_left) * 0.50,
            overlap_left + (overlap_right - overlap_left) * 0.75,
        ]
        
        # 3. Для каждой точки получаем значения всех датчиков (уровни горизонтальных линий)
        levels = []
        for cd in center_disp:
            idx = int(np.argmin(np.abs(disp - cd)))
            for tug in tug_list:
                levels.append(float(tug[idx]))
        
        # 4. Для каждого датчика находим все точки пересечения с этими уровнями
        sensor_data = {}
        for name, tug in zip(tug_names, tug_list):
            x_points = []
            for level in levels:
                # Находим все точки пересечения уровня с кривой
                for i in range(len(tug) - 1):
                    if (tug[i] - level) * (tug[i + 1] - level) < 0:
                        x0, x1 = disp[i], disp[i + 1]
                        y0, y1 = tug[i], tug[i + 1]
                        if y1 != y0:
                            t = (level - y0) / (y1 - y0)
                            x_cross = x0 + t * (x1 - x0)
                            if overlap_left <= x_cross <= overlap_right:
                                x_points.append(float(x_cross))
            
            x_points = sorted(set(x_points))
            
            # 5. Проверяем, насколько точки пересечения вертикальны
            # Ищем группы по 3 точки (по одной от каждого уровня) с минимальным разбросом по X
            if len(x_points) >= 3:
                best_spread = float('inf')
                best_group = []
                # Перебираем все возможные комбинации по 3 точки
                for i in range(len(x_points) - 2):
                    for j in range(i + 1, len(x_points) - 1):
                        for k in range(j + 1, len(x_points)):
                            group = [x_points[i], x_points[j], x_points[k]]
                            spread = max(group) - min(group)
                            if spread < best_spread:
                                best_spread = spread
                                best_group = group
                
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
        
        # 6. Выбираем датчик с минимальным разбросом (наиболее вертикальные точки)
        best_sensor = min(sensor_data.items(), key=lambda x: x[1]['spread'])[0]
        best_data = sensor_data[best_sensor]
        
        # 7. Определяем диапазон по лучшей группе точек
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
        
        # Отладочная информация
        print(f"\n=== Выбор датчика (метод вертикальных пересечений) ===")
        print(f"Область перекрытия: {overlap_left:.1f} - {overlap_right:.1f} мм")
        print(f"Центральные точки: {[f'{cd:.1f}' for cd in center_disp]}")
        print(f"Уровни: {[f'{l:.1f}' for l in levels]}")
        for name, data in sensor_data.items():
            pts_str = ", ".join([f"{x:.1f}" for x in data['x_points']])
            best_str = ", ".join([f"{x:.1f}" for x in data['best_group']]) if data['best_group'] else "нет"
            marker = " ← ВЫБРАН" if name == best_sensor else ""
            print(f"{name}: пересечений={data['count']}, разброс={data['spread']:.2f} мм, "
                f"лучшая группа=[{best_str}]{marker}")
        print(f"Диапазон: {range_left:.1f} - {range_right:.1f} мм")
        print(f"====================================================\n")
        
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

    def _find_magnet_by_intersections(self):
        """Найти положение магнита по пересечениям горизонталей центральных уровней."""
        if self.calib_disp is None or self.calib_channels is None:
            return

        resolved = self._resolve_calib_by_intersections(self.calib_disp, self.calib_channels)
        self._magnet_intersections = resolved['intersections']
        self._magnet_x = resolved['magnet_x']
        self._selected_calib_auto = resolved['selected_sensor']
        self._magnet_auto_range = (
            resolved['range_left'], resolved['range_right']
        ) if resolved['range_left'] is not None else None

        if self._magnet_x is not None:
            self.magnet_position = np.full(len(self.dynamics_time), self._magnet_x)
            sensor = resolved['selected_sensor'] or "?"
            self.magnet_info = (
                f"Магнит X={self._magnet_x:.1f} мм  |  "
                f"Датчик: {sensor}  |  "
                f"Диапазон: {resolved['range_left']:.1f}—{resolved['range_right']:.1f} мм"
            )
        else:
            self.magnet_position = np.full(len(self.dynamics_time), np.nan)
            self.magnet_info = "Не удалось определить положение магнита"
            self._magnet_x = None

    def _interp_linear(self, target, tug_vals, disp_vals):
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
        result = np.empty(len(tugriki_vals))
        for i, t in enumerate(tugriki_vals):
            d = self._interp_linear(t, calib_tugriki, calib_disp)
            result[i] = d if d is not None else 0.0
        return np.round(result, 3)

    def calculate(self, selected_calib=None):
        if self.dynamics_channels and self.calib_channels:
            return self.calculate_all_channels(selected_calib)

        src_cols = list(self.source_data.columns)
        cal_cols = list(self.calib_data.columns)
        src_time = src_cols[0]
        src_val = src_cols[1] if len(src_cols) > 1 else src_cols[0]
        cal_disp = cal_cols[0]
        cal_val = cal_cols[1] if len(cal_cols) > 1 else cal_cols[0]

        tugriki_vals = self.source_data[src_val].to_numpy(dtype=float)
        calib_disp_vals = self.calib_data[cal_disp].to_numpy(dtype=float)
        calib_tugriki_vals = self.calib_data[cal_val].to_numpy(dtype=float)
        result_disp = self._calc_single_channel(tugriki_vals, calib_tugriki_vals, calib_disp_vals)
        self.result_df = pd.DataFrame({
            "Время, мсек": self.source_data[src_time].values,
            "Перемещение, мм": result_disp
        })
        self.result_channels = {cal_val: result_disp}
        self._update_zero_and_baselines()
        return self.result_df

    def calculate_all_channels(self, selected_calib=None):
        manual = self._global_calib_manual

        self._find_magnet_by_intersections()
        mag_x = self._magnet_x

        if getattr(self, '_magnet_auto_range', None):
            auto_left, auto_right = self._magnet_auto_range
        else:
            auto_left, auto_right = self._find_overlap_region()

        range_left = manual.get("range_left", auto_left)
        range_right = manual.get("range_right", auto_right)
        if range_left > range_right:
            range_left, range_right = range_right, range_left

        disp = self._trim_to_overlap(range_left, range_right)

        cal_names = list(self.trimmed_calib.keys())

        self.calib_branches = {}
        for cn in cal_names:
            tug = self.trimmed_calib[cn]
            peak_idx = np.argmax(tug)
            peak_disp = disp[peak_idx]
            left_mask = disp <= peak_disp
            right_mask = disp >= peak_disp
            self.calib_branches[cn] = {
                'left_disp': disp[left_mask],
                'left_tug': tug[left_mask],
                'right_disp': disp[right_mask],
                'right_tug': tug[right_mask],
                'peak_pos': peak_disp,
                'peak_val': tug[peak_idx],
                'full_disp': disp,
                'full_tug': tug,
            }

        best_cal = getattr(self, '_selected_calib_auto', None)
        if best_cal is None and cal_names:
            best_cal = cal_names[0]

        manual_sensor = manual.get("sensor")
        if selected_calib and selected_calib in cal_names:
            best_cal = selected_calib
        elif manual_sensor and manual_sensor in cal_names:
            best_cal = manual_sensor

        self._global_calib_info = {
            "sensor": best_cal,
            "range_left": range_left,
            "range_right": range_right,
            "auto_sensor": getattr(self, '_selected_calib_auto', best_cal),
            "auto_range_left": auto_left,
            "auto_range_right": auto_right,
            "manual_sensor": manual_sensor is not None,
            "manual_range": "range_left" in manual or "range_right" in manual,
            "magnet_x": mag_x,
        }

        br = self.calib_branches[best_cal]
        if mag_x is not None and not np.isnan(mag_x):
            branch_side = "левая" if mag_x <= br['peak_pos'] else "правая"
            self.magnet_info += f"  |  Датчик Холла: {best_cal} ({branch_side} ветка)"

        time_vals = self.dynamics_time
        dyn_names = list(self.dynamics_channels.keys())
        self.result_channels = {}

        for dn in dyn_names:
            tugriki_vals = self.dynamics_channels[dn]
            result_disp = np.empty(len(tugriki_vals))
            mx = mag_x if (mag_x is not None and not np.isnan(mag_x)) else br['peak_pos']
            for j, t in enumerate(tugriki_vals):
                if mx <= br['peak_pos']:
                    d = self._interp_linear(t, br['left_tug'], br['left_disp'])
                else:
                    d = self._interp_linear(t, br['right_tug'], br['right_disp'])
                if d is None:
                    d = self._interp_linear(t, br['full_tug'], br['full_disp'])
                result_disp[j] = d if d is not None else 0.0
            self.result_channels[dn] = np.round(result_disp, 3)

        if self.result_channels:
            self._update_zero_and_baselines()
            key = list(self.result_channels.keys())[0]
            self.result_df = pd.DataFrame({
                "Время, мсек": time_vals,
                "Перемещение, мм": self.result_channels[key]
            })
        else:
            self.zero_point = None
            self.auto_zero_point = None
            self.channel_mins = None
            self.channel_baselines = None
            self.result_df = pd.DataFrame()
        return self.result_df

    def calculate_per_layer_magnet(self):
            """
            Расчёт положения магнита для каждого слоя методом вертикальных пересечений.
            """
            self._per_layer_magnet_x = {}
            self._per_layer_all_intersections = {}
            self._per_layer_selected_sensor = {}
            
            for ch_name, cal in self.per_layer_calib.items():
                disp = cal["disp"]
                tug_dict = cal["tug"]
                tug_names = list(tug_dict.keys())
                tug_list = list(tug_dict.values())
                
                if len(tug_list) < 2:
                    continue
                
                # 1. Находим область перекрытия всех датчиков
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
                
                # 2. Берём три центральные точки по перемещению
                center_disp = [
                    overlap_left + (overlap_right - overlap_left) * 0.25,
                    overlap_left + (overlap_right - overlap_left) * 0.50,
                    overlap_left + (overlap_right - overlap_left) * 0.75,
                ]
                
                # 3. Для каждой точки получаем значения всех датчиков
                levels = []
                for cd in center_disp:
                    idx = int(np.argmin(np.abs(disp - cd)))
                    for tug_vals in tug_list:
                        levels.append(float(tug_vals[idx]))
                
                # 4. Для каждого датчика находим все точки пересечения
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
                    
                    # 5. Ищем группу из 3 точек с минимальным разбросом по X
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
                
                # 6. Выбираем датчик с минимальным разбросом
                best_sensor = min(sensor_data.items(), key=lambda x: x[1]['spread'])[0]
                best_data = sensor_data[best_sensor]
                
                # 7. Определяем положение магнита
                if len(best_data['best_group']) >= 2:
                    magnet_x = (min(best_data['best_group']) + max(best_data['best_group'])) / 2
                elif len(best_data['x_points']) >= 2:
                    magnet_x = (min(best_data['x_points']) + max(best_data['x_points'])) / 2
                else:
                    magnet_x = (overlap_left + overlap_right) / 2
                
                self._per_layer_magnet_x[ch_name] = float(magnet_x)
                self._per_layer_selected_sensor[ch_name] = best_sensor
                self._per_layer_all_intersections[ch_name] = best_data['x_points']
                
                # Отладочная информация
                print(f"\n=== Слой: {ch_name} ===")
                print(f"Область перекрытия: {overlap_left:.1f} - {overlap_right:.1f} мм")
                print(f"Центральные точки: {[f'{cd:.1f}' for cd in center_disp]}")
                for name, data in sensor_data.items():
                    pts_str = ", ".join([f"{x:.1f}" for x in data['x_points']]) if data['x_points'] else "нет"
                    best_str = ", ".join([f"{x:.1f}" for x in data['best_group']]) if data['best_group'] else "нет"
                    marker = " ← ВЫБРАН" if name == best_sensor else ""
                    print(f"  {name}: пересечений={data['count']}, разброс={data['spread']:.2f} мм, "
                        f"лучшая группа=[{best_str}]{marker}")
                print(f"Магнит X={magnet_x:.1f} мм")
                print(f"====================\n")

    def calculate_per_layer(self):
        if not self.per_layer_calib or not self.dynamics_channels:
            return self.result_df

        time_vals = self.dynamics_time
        self.magnet_info = ""
        self.result_channels = {}
        self._per_layer_calib_info = {}

        for dn, tugriki_vals in self.dynamics_channels.items():
            if dn not in self.per_layer_calib:
                continue
            cal = self.per_layer_calib[dn]
            disp = cal["disp"]
            tug_dict = cal["tug"]

            auto_range = self._per_layer_auto_range.get(dn)
            if auto_range:
                auto_left, auto_right = auto_range
            else:
                auto_left, auto_right = self._find_layer_overlap(disp, tug_dict)
            auto_sensor = self._per_layer_selected_sensor.get(dn)
            if not auto_sensor or auto_sensor not in tug_dict:
                auto_sensor = list(tug_dict.keys())[0]

            manual = self._per_layer_manual.get(dn, {})
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
            cal_disp, cal_tug = self._extract_rising_branch(
                disp, tug, range_left=range_left, range_right=range_right)

            self._per_layer_calib_info[dn] = {
                "sensor": selected,
                "range_left": float(range_left),
                "range_right": float(range_right),
                "auto_sensor": auto_sensor,
                "auto_range_left": float(auto_left),
                "auto_range_right": float(auto_right),
                "manual_sensor": manual_sensor is not None,
                "manual_range": "range_left" in manual or "range_right" in manual,
                "magnet_x": self._per_layer_magnet_x.get(dn),
            }

            result_disp = self._calc_single_channel(tugriki_vals, cal_tug, cal_disp)
            self.result_channels[dn] = np.round(result_disp, 3)

        if self.result_channels:
            self._update_zero_and_baselines()
            key = list(self.result_channels.keys())[0]
            self.result_df = pd.DataFrame({
                "Время, мсек": time_vals,
                "Перемещение, мм": self.result_channels[key]
            })
        else:
            self.zero_point = None
            self.auto_zero_point = None
            self.channel_mins = None
            self.channel_baselines = None
            self.result_df = pd.DataFrame()
        return self.result_df
