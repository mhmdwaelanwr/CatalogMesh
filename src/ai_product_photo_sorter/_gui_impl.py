#!/usr/bin/env python3
"""Tkinter interface for the shared Product Sorter engine."""
from __future__ import annotations
import csv, os, queue, re, signal, subprocess, sys, tempfile, threading, webbrowser
from pathlib import Path
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk
except ImportError as exc:
    raise SystemExit("Tkinter is not installed. On Ubuntu/Debian: sudo apt install python3-tk") from exc

from i18n import detect_language
from model_catalog import default_model, models_for, refresh_catalog_for_keys
from professional import VERSION
from set_data import ENV_FILE, read_env, save_env

ROOT=Path(__file__).resolve().parent
def branding_file(name:str) -> Path:
    candidates=(ROOT/"assets"/"branding"/name,Path(sys.prefix)/"assets"/"branding"/name)
    return next((path for path in candidates if path.is_file()),candidates[0])

KEY_NAMES=[f"{provider}_API_KEY_{i}" for provider in ("GEMINI","OPENAI","ANTHROPIC") for i in range(1,5)]
L={
"en":{"title":"Product Sorter Pro","subtitle":"AI workspace for clean, resumable product catalogs","workspace":"WORKSPACE","source":"Photos folder","output":"Output folder","prices":"Price file (optional)","providers":"Provider priority","sample":"Photo count (blank = all)","start":"Start sorting","stop":"Stop safely","resume":"Resume","save":"Save settings","open":"Open output","progress":"CURRENT OPERATION","completed":"Completed","pending":"Pending","failed":"Failed","logs":"Live activity","status":"Status","ready":"Ready to process","saved":"Settings saved","running":"Processing photos","stopped":"Stop requested","settings":"Operation setup","credentials":"Models & API keys","results":"Results & activity","clear":"Clear log","model":"Vision model","refresh":"Refresh models","file":"Filename","state":"Status","light":"Light mode","dark":"Dark mode","about":"About","developer":"Developed and maintained by Mohamed Anwar","open_source":"Open-source software · MIT License","copy_contact":"Copy contact details","copied":"Contact details copied"},
"ar":{"title":"منظم صور المنتجات","subtitle":"مساحة ذكية لبناء كتالوج منتجات مرتب وقابل للاستكمال","workspace":"مساحة العمل","source":"مجلد صور المنتجات","output":"مجلد النتائج","prices":"ملف الأسعار (اختياري)","providers":"أولوية المزودات","sample":"عدد الصور (فارغ = الكل)","start":"ابدأ الترتيب","stop":"إيقاف آمن","resume":"استكمال","save":"حفظ الإعدادات","open":"فتح النتائج","progress":"العملية الحالية","completed":"مكتمل","pending":"متبقي","failed":"فشل","logs":"النشاط المباشر","status":"الحالة","ready":"جاهز للمعالجة","saved":"تم حفظ الإعدادات","running":"جاري معالجة الصور","stopped":"تم طلب الإيقاف","settings":"إعداد العملية","credentials":"الموديلات ومفاتيح API","results":"النتائج والنشاط","clear":"مسح السجل","model":"موديل الرؤية","refresh":"تحديث الموديلات","file":"اسم الملف","state":"الحالة","light":"الوضع الفاتح","dark":"الوضع الداكن","about":"حول البرنامج","developer":"تطوير وصيانة محمد أنور","open_source":"برنامج مفتوح المصدر · ترخيص MIT","copy_contact":"نسخ بيانات التواصل","copied":"تم نسخ بيانات التواصل"},
"zh":{"title":"产品图片整理器","subtitle":"用于构建整洁且可恢复产品目录的 AI 工作区","workspace":"工作区","source":"产品图片文件夹","output":"输出文件夹","prices":"价格文件（可选）","providers":"提供商优先级","sample":"图片数量（留空=全部）","start":"开始整理","stop":"安全停止","resume":"继续","save":"保存设置","open":"打开输出","progress":"当前任务","completed":"已完成","pending":"待处理","failed":"失败","logs":"实时活动","status":"状态","ready":"准备处理","saved":"设置已保存","running":"正在处理图片","stopped":"已请求停止","settings":"任务设置","credentials":"模型和 API 密钥","results":"结果与活动","clear":"清除日志","model":"视觉模型","refresh":"刷新模型","file":"文件名","state":"状态","light":"浅色模式","dark":"深色模式","about":"关于","developer":"由 Mohamed Anwar 开发和维护","open_source":"开源软件 · MIT 许可证","copy_contact":"复制联系方式","copied":"联系方式已复制"}}

class App:
    def __init__(self,root:tk.Tk):
        self.root=root; self.values=read_env(ENV_FILE); self.lang=self.values.get("APP_LANGUAGE") or detect_language(); self.lang=self.lang if self.lang in L else "en"; self.theme=self.values.get("APP_THEME","dark"); self.theme=self.theme if self.theme in {"dark","light"} else "dark"; self.p=None; self.q=queue.Queue(); self.vars={}; self.model_boxes={}; self.table_signature=None; self.key_response_file=None
        root.geometry("1240x860"); root.minsize(980,700); self.load_window_icon(); self.configure_styles(); self.build(); self.apply_language(); self.load_values(); self.set_running(False); root.after(100,self.poll); root.protocol("WM_DELETE_WINDOW",self.close)
        root.bind("<Control-Return>",lambda event:self.start()); root.bind("<F5>",lambda event:self.refresh_tables())
    def t(self,k): return L[self.lang][k]
    def load_window_icon(self):
        self.window_icon=None
        try:
            self.window_icon=tk.PhotoImage(file=str(branding_file("product-sorter-64.png")))
            self.root.iconphoto(True,self.window_icon)
        except (tk.TclError,OSError):
            pass
    def configure_styles(self):
        palettes={
            "dark":{"bg":"#0b1220","panel":"#111c2e","panel2":"#162338","field":"#0d1728","log":"#09111f","text":"#e8eef8","muted":"#94a3b8","accent":"#4f8cff","accent_hover":"#6aa0ff","soft_hover":"#213552","green":"#21c98b","red":"#ff647c","border":"#26364f","trough":"#1d2b42"},
            "light":{"bg":"#eef3f9","panel":"#ffffff","panel2":"#f4f7fb","field":"#ffffff","log":"#f7f9fc","text":"#172033","muted":"#64748b","accent":"#2563eb","accent_hover":"#3977ef","soft_hover":"#e5edf8","green":"#059669","red":"#dc4663","border":"#d9e2ef","trough":"#dbe5f2"},
        }
        self.colors=palettes[self.theme]
        self.root.configure(bg=self.colors["bg"])
        style=ttk.Style(self.root); style.theme_use("clam" if "clam" in style.theme_names() else style.theme_use())
        style.configure("App.TFrame",background=self.colors["bg"]); style.configure("Panel.TFrame",background=self.colors["panel"]); style.configure("Card.TFrame",background=self.colors["panel2"]); style.configure("AppImage.TLabel",background=self.colors["bg"]); style.configure("CardImage.TLabel",background=self.colors["panel2"])
        style.configure("Hero.TLabel",background=self.colors["bg"],foreground=self.colors["text"],font=("Sans",22,"bold")); style.configure("Subtitle.TLabel",background=self.colors["bg"],foreground=self.colors["muted"],font=("Sans",10))
        style.configure("Section.TLabel",background=self.colors["panel"],foreground=self.colors["muted"],font=("Sans",9,"bold")); style.configure("Panel.TLabel",background=self.colors["panel"],foreground=self.colors["text"])
        style.configure("Metric.TLabel",background=self.colors["panel2"],foreground=self.colors["text"],font=("Sans",20,"bold")); style.configure("MetricName.TLabel",background=self.colors["panel2"],foreground=self.colors["muted"])
        style.configure("Accent.TButton",font=("Sans",10,"bold"),foreground="#fff",background=self.colors["accent"],padding=(16,9)); style.map("Accent.TButton",background=[("active",self.colors["accent_hover"]),("disabled",self.colors["border"])])
        style.configure("Soft.TButton",foreground=self.colors["text"],background=self.colors["panel2"],padding=(12,8)); style.map("Soft.TButton",background=[("active",self.colors["soft_hover"])]); style.configure("Danger.TButton",foreground="#fff",background="#c83c59",padding=(12,8))
        style.configure("TNotebook",background=self.colors["panel"],borderwidth=0); style.configure("TNotebook.Tab",background=self.colors["panel2"],foreground=self.colors["muted"],padding=(14,8)); style.map("TNotebook.Tab",background=[("selected",self.colors["accent"])],foreground=[("selected","#fff")])
        style.configure("TEntry",fieldbackground=self.colors["field"],foreground=self.colors["text"],insertcolor=self.colors["text"],bordercolor=self.colors["border"],padding=7); style.configure("TCombobox",fieldbackground=self.colors["field"],foreground=self.colors["text"],arrowcolor=self.colors["text"],padding=6)
        style.configure("Treeview",background=self.colors["field"],fieldbackground=self.colors["field"],foreground=self.colors["text"],rowheight=28,borderwidth=0); style.configure("Treeview.Heading",background=self.colors["panel2"],foreground=self.colors["muted"],font=("Sans",9,"bold"),relief="flat")
        style.configure("Horizontal.TProgressbar",background=self.colors["accent"],troughcolor=self.colors["trough"],borderwidth=0,thickness=12)
    def build(self):
        shell=ttk.Frame(self.root,style="App.TFrame",padding=(24,18)); shell.pack(fill="both",expand=True)
        self.header=ttk.Frame(shell,style="App.TFrame"); self.header.pack(fill="x",pady=(0,16))
        self.header_logo=None
        try:
            self.header_logo=tk.PhotoImage(file=str(branding_file("product-sorter-48.png")))
            ttk.Label(self.header,image=self.header_logo,style="AppImage.TLabel").pack(side="left",padx=(0,12))
        except (tk.TclError,OSError):
            pass
        brand=ttk.Frame(self.header,style="App.TFrame"); brand.pack(side="left")
        self.title=ttk.Label(brand,style="Hero.TLabel"); self.title.pack(anchor="w")
        self.subtitle=ttk.Label(brand,style="Subtitle.TLabel"); self.subtitle.pack(anchor="w",pady=(2,0))
        self.langbox=ttk.Combobox(self.header,values=["العربية","English","中文"],state="readonly",width=12); self.langbox.pack(side="right",pady=8); self.langbox.bind("<<ComboboxSelected>>",self.change_lang)
        self.theme_button=ttk.Button(self.header,style="Soft.TButton",command=self.toggle_theme); self.theme_button.pack(side="right",padx=(0,8),pady=8)
        self.main_tabs=ttk.Notebook(shell); self.main_tabs.pack(fill="both",expand=True)
        setup_page=ttk.Frame(self.main_tabs,style="Panel.TFrame",padding=16); keys_page=ttk.Frame(self.main_tabs,style="Panel.TFrame",padding=16); results_page=ttk.Frame(self.main_tabs,style="Panel.TFrame",padding=16); about_page=ttk.Frame(self.main_tabs,style="Panel.TFrame",padding=28)
        self.main_tabs.add(setup_page,text="Setup"); self.main_tabs.add(keys_page,text="API"); self.main_tabs.add(results_page,text="Results"); self.main_tabs.add(about_page,text="About")
        cfg=ttk.Frame(setup_page,style="Panel.TFrame"); cfg.pack(fill="x")
        self.workspace_label=ttk.Label(cfg,style="Section.TLabel"); self.workspace_label.grid(row=0,column=0,columnspan=3,sticky="w",padx=4,pady=(0,10))
        fields=[("source",True),("output",True),("prices",True),("providers",False),("sample",False)]
        for row,(key,browse) in enumerate(fields):
            label=ttk.Label(cfg,style="Panel.TLabel"); label.grid(row=row+1,column=0,sticky="w",padx=4,pady=7); self.vars[key]=tk.StringVar(); entry=ttk.Entry(cfg,textvariable=self.vars[key]); entry.grid(row=row+1,column=1,sticky="ew",padx=8,pady=5)
            if browse: ttk.Button(cfg,text="Browse…",style="Soft.TButton",command=lambda k=key:self.browse(k)).grid(row=row+1,column=2,pady=5)
            setattr(self,key+"_label",label)
        cfg.columnconfigure(1,weight=1)
        keys=ttk.Notebook(keys_page); keys.pack(fill="both",expand=True)
        for provider in ("GEMINI","OPENAI","ANTHROPIC"):
            page=ttk.Frame(keys,style="Panel.TFrame",padding=16); keys.add(page,text=provider)
            for i in range(1,5):
                name=f"{provider}_API_KEY_{i}"; ttk.Label(page,text=f"API key {i}",style="Panel.TLabel").grid(row=i-1,column=0,sticky="w",padx=4,pady=7)
                self.vars[name]=tk.StringVar(); ttk.Entry(page,textvariable=self.vars[name],show="•").grid(row=i-1,column=1,columnspan=2,sticky="ew",padx=8,pady=5)
            model_name=f"{provider}_MODEL"; label=ttk.Label(page,style="Panel.TLabel"); label.grid(row=4,column=0,sticky="w",padx=4,pady=7); setattr(self,provider+"_model_label",label)
            self.vars[model_name]=tk.StringVar(); box=ttk.Combobox(page,textvariable=self.vars[model_name],values=models_for(provider.lower()))
            box.grid(row=4,column=1,sticky="ew",padx=8,pady=5); self.model_boxes[provider]=box
            button=ttk.Button(page,style="Soft.TButton",command=lambda p=provider:self.refresh_models(p)); button.grid(row=4,column=2,padx=4,pady=5); setattr(self,provider+"_refresh_button",button)
            page.columnconfigure(1,weight=1)
        actions=ttk.Frame(setup_page,style="Panel.TFrame"); actions.pack(fill="x",pady=(22,10))
        self.buttons={"start":ttk.Button(actions,style="Accent.TButton",command=self.start),"stop":ttk.Button(actions,style="Danger.TButton",command=self.stop),"resume":ttk.Button(actions,style="Soft.TButton",command=self.resume),"save":ttk.Button(actions,style="Soft.TButton",command=self.save),"open":ttk.Button(actions,style="Soft.TButton",command=self.open)}
        for b in self.buttons.values(): b.pack(side="left",padx=(0,7))
        self.status=tk.StringVar(); ttk.Label(actions,textvariable=self.status,style="Panel.TLabel",font=("Sans",10,"bold")).pack(side="right")
        prog=ttk.Frame(setup_page,style="Card.TFrame",padding=16); prog.pack(fill="x",pady=(8,0)); self.progress_label=ttk.Label(prog,style="MetricName.TLabel"); self.progress_label.pack(anchor="w")
        self.bar=ttk.Progressbar(prog,maximum=100); self.bar.pack(fill="x",pady=(10,8)); self.progress_text=tk.StringVar(value="0% · 0 / 0"); ttk.Label(prog,textvariable=self.progress_text,style="MetricName.TLabel").pack(anchor="w")
        metrics=ttk.Frame(results_page,style="Panel.TFrame"); metrics.pack(fill="x",pady=(0,12)); self.metric_values={}
        for index,key in enumerate(("completed","pending","failed")):
            card=ttk.Frame(metrics,style="Card.TFrame",padding=14); card.grid(row=0,column=index,sticky="ew",padx=6); metrics.columnconfigure(index,weight=1)
            self.metric_values[key]=tk.StringVar(value="0"); ttk.Label(card,textvariable=self.metric_values[key],style="Metric.TLabel").pack(anchor="w"); label=ttk.Label(card,style="MetricName.TLabel"); label.pack(anchor="w"); setattr(self,key+"_metric_label",label)
        pan=ttk.Panedwindow(results_page,orient="vertical"); pan.pack(fill="both",expand=True)
        table_frame=ttk.Frame(pan,style="Panel.TFrame"); log_frame=ttk.Frame(pan,style="Panel.TFrame"); pan.add(table_frame,weight=2); pan.add(log_frame,weight=1)
        self.tabs=ttk.Notebook(table_frame); self.tabs.pack(fill="both",expand=True); self.trees={}
        for key in ("completed","pending","failed"):
            frame=ttk.Frame(self.tabs,style="Panel.TFrame"); tree=ttk.Treeview(frame,columns=("file","state"),show="headings"); tree.heading("file",text="Filename"); tree.heading("state",text="Status"); tree.column("file",width=650); tree.column("state",width=180); tree.pack(fill="both",expand=True,pady=(4,0)); self.tabs.add(frame,text=key); self.trees[key]=tree
        log_header=ttk.Frame(log_frame,style="Panel.TFrame"); log_header.pack(fill="x",pady=(10,5)); self.log_label=ttk.Label(log_header,style="Section.TLabel"); self.log_label.pack(side="left"); self.clear_button=ttk.Button(log_header,style="Soft.TButton",command=self.clear_log); self.clear_button.pack(side="right")
        self.log=tk.Text(log_frame,height=9,wrap="word",state="disabled",bg=self.colors["log"],fg=self.colors["text"],insertbackground=self.colors["text"],selectbackground=self.colors["accent"],relief="flat",padx=10,pady=8,font=("Monospace",9)); self.log.pack(fill="both",expand=True)
        about_card=ttk.Frame(about_page,style="Card.TFrame",padding=24); about_card.pack(fill="both",expand=True)
        self.about_logo=None
        try:
            self.about_logo=tk.PhotoImage(file=str(branding_file("product-sorter-128.png")))
            ttk.Label(about_card,image=self.about_logo,style="CardImage.TLabel").pack(anchor="w",pady=(0,14))
        except (tk.TclError,OSError):
            pass
        ttk.Label(about_card,text="AI PRODUCT PHOTO SORTER",style="MetricName.TLabel").pack(anchor="w")
        ttk.Label(about_card,text="Product Sorter Pro",style="Metric.TLabel").pack(anchor="w",pady=(6,0))
        self.about_version=ttk.Label(about_card,style="MetricName.TLabel"); self.about_version.pack(anchor="w",pady=(3,18))
        self.developer_label=ttk.Label(about_card,style="MetricName.TLabel",font=("Sans",11)); self.developer_label.pack(anchor="w",pady=3)
        self.opensource_label=ttk.Label(about_card,style="MetricName.TLabel"); self.opensource_label.pack(anchor="w",pady=(0,18))
        social=ttk.Frame(about_card,style="Card.TFrame"); social.pack(fill="x",anchor="w")
        links=[("GitHub","https://github.com/mhmdwaelanwr"),("LinkedIn","https://linkedin.com/in/mhmdwaelanwr"),("X (Twitter)","https://x.com/mhmdwaelanwr"),("Facebook","https://facebook.com/mhmdwaelanwr"),("Instagram","https://instagram.com/mhmdwaelanwr"),("Telegram DM","https://t.me/Mhmdwaelanwer")]
        for index,(label,url) in enumerate(links):
            ttk.Button(social,text=label,style="Soft.TButton",command=lambda value=url:self.open_url(value)).grid(row=index//3,column=index%3,sticky="ew",padx=4,pady=4); social.columnconfigure(index%3,weight=1)
        self.copy_contact_button=ttk.Button(about_card,style="Accent.TButton",command=self.copy_contact); self.copy_contact_button.pack(anchor="w",pady=(20,0))
    def apply_language(self):
        self.root.title(self.t("title")); self.title.config(text=self.t("title")); self.subtitle.config(text=self.t("subtitle")); self.workspace_label.config(text=self.t("workspace")); self.langbox.set({"ar":"العربية","en":"English","zh":"中文"}[self.lang])
        for k in ("source","output","prices","providers","sample"): getattr(self,k+"_label").config(text=self.t(k))
        for k,b in self.buttons.items(): b.config(text=self.t(k))
        self.progress_label.config(text=self.t("progress")); self.status.set(self.t("ready")); self.log_label.config(text=self.t("logs")); self.clear_button.config(text=self.t("clear"))
        self.theme_button.config(text=("☀  "+self.t("light")) if self.theme=="dark" else ("☾  "+self.t("dark")))
        for p in ("GEMINI","OPENAI","ANTHROPIC"):
            getattr(self,p+"_model_label").config(text=self.t("model")); getattr(self,p+"_refresh_button").config(text=self.t("refresh"))
        for key in ("completed","pending","failed"): getattr(self,key+"_metric_label").config(text=self.t(key))
        for i,key in enumerate(("settings","credentials","results","about")): self.main_tabs.tab(i,text=self.t(key))
        self.about_version.config(text=f"Version {VERSION}"); self.developer_label.config(text=self.t("developer")); self.opensource_label.config(text=self.t("open_source")); self.copy_contact_button.config(text=self.t("copy_contact"))
        for i,k in enumerate(("completed","pending","failed")): self.tabs.tab(i,text=self.t(k))
        for tree in self.trees.values(): tree.heading("file",text=self.t("file")); tree.heading("state",text=self.t("state"))
    def change_lang(self,event=None): self.lang={"العربية":"ar","English":"en","中文":"zh"}[self.langbox.get()]; self.apply_language()
    def toggle_theme(self):
        self.theme="light" if self.theme=="dark" else "dark"; self.configure_styles()
        self.log.config(bg=self.colors["log"],fg=self.colors["text"],insertbackground=self.colors["text"],selectbackground=self.colors["accent"])
        self.theme_button.config(text=("☀  "+self.t("light")) if self.theme=="dark" else ("☾  "+self.t("dark")))
        self.values=self.collect(); save_env(self.values)
    @staticmethod
    def open_url(url): webbrowser.open(url,new=2)
    def copy_contact(self):
        details="GitHub: github.com/mhmdwaelanwr\nLinkedIn: linkedin.com/in/mhmdwaelanwr\nX: x.com/mhmdwaelanwr\nFacebook: facebook.com/mhmdwaelanwr\nInstagram: instagram.com/mhmdwaelanwr\nTelegram: t.me/Mhmdwaelanwer"
        self.root.clipboard_clear(); self.root.clipboard_append(details); self.root.update_idletasks(); self.status.set(self.t("copied"))
    def load_values(self):
        mapping={"source":"PRODUCT_SOURCE","output":"PRODUCT_OUTPUT","prices":"PRICES_FILE","providers":"AI_PROVIDERS","sample":"PHOTO_LIMIT"}
        for gui,env in mapping.items(): self.vars[gui].set(self.values.get(env,""))
        for k in KEY_NAMES:
            legacy=k.rsplit("_",1)[0] if k.endswith("_1") else ""
            self.vars[k].set(self.values.get(k,"") or self.values.get(legacy,""))
        for provider in ("GEMINI","OPENAI","ANTHROPIC"):
            name=f"{provider}_MODEL"; self.vars[name].set(self.values.get(name,"") or default_model(provider.lower()))
    def browse(self,key):
        value=filedialog.askopenfilename() if key=="prices" else filedialog.askdirectory()
        if value:self.vars[key].set(value)
    def collect(self):
        v=dict(self.values); v.update({"APP_LANGUAGE":self.lang,"APP_THEME":self.theme,"PRODUCT_SOURCE":self.vars["source"].get(),"PRODUCT_OUTPUT":self.vars["output"].get(),"PRICES_FILE":self.vars["prices"].get(),"AI_PROVIDERS":self.vars["providers"].get() or "gemini","PHOTO_LIMIT":self.vars["sample"].get()})
        for k in KEY_NAMES: v[k]=self.vars[k].get()
        for provider in ("GEMINI","OPENAI","ANTHROPIC"): v[f"{provider}_MODEL"]=self.vars[f"{provider}_MODEL"].get()
        return v
    def refresh_models(self,provider):
        keys=[self.vars[f"{provider}_API_KEY_{index}"].get().strip() for index in range(1,5)]
        keys=[key for key in keys if key]
        if not keys: messagebox.showerror("Models",f"Enter at least one {provider} API key first."); return
        try:
            models=refresh_catalog_for_keys(provider.lower(),keys,self.values.get("OPENAI_BASE_URL","")); self.model_boxes[provider]["values"]=models
            if self.vars[f"{provider}_MODEL"].get() not in models:self.vars[f"{provider}_MODEL"].set(models[0])
            messagebox.showinfo("Models",f"Downloaded {len(models)} models shared by all {len(keys)} {provider} keys.")
        except Exception as exc: messagebox.showerror("Models",f"Could not download models: {exc}")
    def save(self): self.values=self.collect(); save_env(self.values); self.status.set(self.t("saved"))
    def command(self):
        cmd=[sys.executable,str(ROOT/"product_sorter.py"),"--non-interactive","--source",self.vars["source"].get(),"--output",self.vars["output"].get()]
        if self.vars["prices"].get(): cmd += ["--prices",self.vars["prices"].get()]
        if self.vars["sample"].get(): cmd += ["--limit",self.vars["sample"].get()]
        return cmd
    def start(self):
        if self.p and self.p.poll() is None:return
        if not self.vars["source"].get() or not self.vars["output"].get(): messagebox.showerror(self.t("status"),"Source and output are required"); return
        self.save(); env=os.environ.copy(); env.update({k:str(v) for k,v in self.collect().items()}); env["PRODUCT_SORTER_NON_INTERACTIVE"]="1"; env["PYTHONUNBUFFERED"]="1"
        handle,path=tempfile.mkstemp(prefix="product-sorter-key-",suffix=".tmp"); os.close(handle); os.unlink(path); self.key_response_file=Path(path); env["PRODUCT_SORTER_KEY_RESPONSE_FILE"]=path
        flags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=="nt" else 0
        self.p=subprocess.Popen(self.command(),cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=0,creationflags=flags); self.status.set(self.t("running")); self.set_running(True); self.main_tabs.select(2); threading.Thread(target=self.reader,daemon=True).start()
    def resume(self): self.start()
    def stop(self):
        if self.p and self.p.poll() is None:
            try:self.p.send_signal(signal.CTRL_BREAK_EVENT if os.name=="nt" else signal.SIGINT)
            except (OSError,ValueError):self.p.terminate()
            self.status.set(self.t("stopped"))
    def set_running(self,running):
        self.buttons["start"].config(state="disabled" if running else "normal"); self.buttons["resume"].config(state="disabled" if running else "normal"); self.buttons["stop"].config(state="normal" if running else "disabled")
    def reader(self):
        buf=""
        while self.p and self.p.stdout:
            ch=self.p.stdout.read(1)
            if not ch:break
            if ch in "\r\n":
                if buf:self.q.put(buf); buf=""
            else:buf+=ch
        if buf:self.q.put(buf)
        self.q.put("__DONE__")
    def poll(self):
        try:
            while True:
                line=self.q.get_nowait()
                if line=="__DONE__": self.status.set(self.t("ready")); self.set_running(False); self.refresh_tables(); continue
                if line.startswith("__PRODUCT_SORTER_KEY_REQUEST__:"):
                    self.ask_replacement_key(line.split(":",1)[1]); continue
                self.append_log(line); m=re.search(r"(\d+)%.*?(\d+)/(\d+)",line)
                if m:self.bar["value"]=int(m.group(1)); self.progress_text.set(line)
        except queue.Empty:pass
        self.refresh_tables(); self.root.after(500,self.poll)
    def append_log(self,line): self.log.config(state="normal"); self.log.insert("end",line+"\n"); self.log.see("end"); self.log.config(state="disabled")
    def clear_log(self): self.log.config(state="normal"); self.log.delete("1.0","end"); self.log.config(state="disabled")
    def ask_replacement_key(self,provider):
        value=simpledialog.askstring("API key",f"All {provider} keys are exhausted. Enter a new key to continue:",show="•",parent=self.root) or ""
        if self.key_response_file:
            self.key_response_file.write_text(value,encoding="utf-8"); os.chmod(self.key_response_file,0o600)
    def refresh_tables(self):
        path=Path(self.vars["output"].get())/"processing_status.csv"
        if path.is_file():
            try:
                err=path.parent/"error_report.csv"; signature=(path.stat().st_mtime_ns,err.stat().st_mtime_ns if err.is_file() else 0)
                if signature==self.table_signature:return
                self.table_signature=signature
                with path.open(encoding="utf-8-sig") as h: rows=list(csv.DictReader(h))
                for tree in self.trees.values(): tree.delete(*tree.get_children())
                for r in rows:
                    key="completed" if r.get("status")=="completed" else "pending"; self.trees[key].insert("", "end", values=(r.get("filename"),r.get("status")))
                if err.is_file():
                    with err.open(encoding="utf-8-sig") as h:
                        for r in csv.DictReader(h): self.trees["failed"].insert("","end",values=(r.get("filenames"),r.get("error")))
                for key,tree in self.trees.items(): self.metric_values[key].set(str(len(tree.get_children())))
            except (OSError,csv.Error):pass
    def open(self):
        path=self.vars["output"].get()
        if path:
            if os.name=="nt": os.startfile(path)
            elif sys.platform=="darwin": subprocess.Popen(["open",path])
            else: subprocess.Popen(["xdg-open",path])
    def close(self):
        self.stop()
        if self.key_response_file:self.key_response_file.unlink(missing_ok=True)
        self.root.destroy()

def main():
    root=tk.Tk(); style=ttk.Style(); style.theme_use("clam" if "clam" in style.theme_names() else style.theme_use()); App(root); root.mainloop()
if __name__=="__main__": main()
