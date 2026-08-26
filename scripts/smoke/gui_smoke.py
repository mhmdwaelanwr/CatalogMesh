#!/usr/bin/env python3
"""Visual smoke test: opens the GUI, updates widgets, then closes after 2s."""
import tkinter as tk
from product_sorter_gui import App
root=tk.Tk(); app=App(root); app.status.set("GUI smoke test OK"); root.after(2000,root.destroy); root.mainloop()
