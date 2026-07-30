"""
Модуль-обёртка для обратной совместимости.
Перенаправляет к новым модулям models и core.
"""
from models.data_loader import DataLoader

# Для обратной совместимости создаём алиас на Calculator
# который использует DataLoader
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from core.calculator import Calculator as _Calculator

class DataLoaderWithCalc(DataLoader):
    """DataLoader с методами расчёта для обратной совместимости."""
    
    def __init__(self):
        super().__init__()
        self._calculator = _Calculator(self)
    
    # Делегируем методы расчёта калькулятору
    def calculate(self, selected_calib=None):
        return self._calculator.calculate(selected_calib)
    
    def calculate_all_channels(self, selected_calib=None):
        return self._calculator.calculate_all_channels(selected_calib)
    
    def calculate_per_layer(self):
        return self._calculator.calculate_per_layer()
    
    def calculate_per_layer_magnet(self):
        return self._calculator.calculate_per_layer_magnet()
    
    def set_manual_zero(self, value):
        self._calculator.set_manual_zero(value)
    
    def clear_manual_zero(self):
        self._calculator.clear_manual_zero()
    
    def set_layer_manual(self, layer_name, sensor=None, range_left=None, range_right=None):
        self._calculator.set_layer_manual(layer_name, sensor, range_left, range_right)
    
    def clear_layer_manual(self, layer_name):
        self._calculator.clear_layer_manual(layer_name)
    
    def set_global_manual(self, sensor=None, range_left=None, range_right=None):
        self._calculator.set_global_manual(sensor, range_left, range_right)
    
    def clear_global_manual(self):
        self._calculator.clear_global_manual()


# Алиас для старого имени класса
DataLoader = DataLoaderWithCalc

__all__ = ['DataLoader']
