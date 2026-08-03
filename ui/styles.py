"""Стили приложения."""
import tkinter as tk
from tkinter import ttk
from matplotlib import rcParams

# Цветовая схема
BG = "#f0f2f5"
FG = "#1a1a2e"
ACCENT = "#2563eb"
ACCENT_HOVER = "#1d4ed8"
PANEL_BG = "#ffffff"
HEADER_BG = "#e8eaf0"
GRID_COLOR = "#d1d5db"
CHART_BG = "#fafbfc"

CHANNEL_COLORS = ["#4CAF50", "#2196F3", "#FF9800", "#E91E63", "#9C27B0", "#00BCD4", "#FF5722"]


def apply_styles():
    """Применяет стили ко всему приложению."""
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

    return {
        'BG': BG, 'FG': FG, 'ACCENT': ACCENT, 'ACCENT_HOVER': ACCENT_HOVER,
        'PANEL_BG': PANEL_BG, 'HEADER_BG': HEADER_BG, 'GRID_COLOR': GRID_COLOR,
        'CHART_BG': CHART_BG, 'CHANNEL_COLORS': CHANNEL_COLORS
    }
