#!/usr/bin/env python3
"""Tkinter interface for the shared Product Sorter engine."""
from __future__ import annotations
import csv, os, queue, re, signal, subprocess, sys, tempfile, threading
from pathlib import Path
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk
except ImportError as exc:
    raise SystemExit("Tkinter is not installed. On Ubuntu/Debian: sudo apt install python3-tk") from exc

from i18n import detect_language
from set_data import ENV_FILE, read_env, save_env

ROOT=Path(__file__).resolve().parent
KEY_NAMES=[f"{provider}_API_KEY_{i}" for provider in ("GEMINI","OPENAI","ANTHROPIC") for i in range(1,5)]
L={
"en":{"title":"Product Sorter Pro","source":"Photos folder","output":"Output folder","prices":"Price file","providers":"Providers order","sample":"Photo count (blank = all)","start":"Start","stop":"Stop","resume":"Resume","save":"Save settings","open":"Open output","progress":"Progress","completed":"Completed","pending":"Pending","failed":"Failed","logs":"Live log","status":"Status","ready":"Ready","saved":"Settings saved","running":"Running","stopped":"Stopped"},
"ar":{"title":"منظم صور المنتجات الاحترافي","source":"مجلد الصور","output":"مجلد النتائج","prices":"ملف الأسعار","providers":"ترتيب المزودات","sample":"عدد الصور (فارغ = الكل)","start":"بدء","stop":"إيقاف","resume":"استكمال","save":"حفظ الإعدادات","open":"فتح النتائج","progress":"التقدم","completed":"تم","pending":"متبقي","failed":"فشل","logs":"السجل المباشر","status":"الحالة","ready":"جاهز","saved":"تم حفظ الإعدادات","running":"جاري التشغيل","stopped":"متوقف"},
"zh":{"title":"产品图片整理器专业版","source":"图片文件夹","output":"输出文件夹","prices":"价格文件","providers":"提供商顺序","sample":"图片数量（留空=全部）","start":"开始","stop":"停止","resume":"继续","save":"保存设置","open":"打开输出","progress":"进度","completed":"已完成","pending":"待处理","failed":"失败","logs":"实时日志","status":"状态","ready":"就绪","saved":"设置已保存","running":"运行中","stopped":"已停止"}}

class App:
    def __init__(self,root:tk.Tk):
        self.root=root; self.values=read_env(ENV_FILE); self.lang=self.values.get("APP_LANGUAGE") or detect_language(); self.lang=self.lang if self.lang in L else "en"; self.p=None; self.q=queue.Queue(); self.vars={}; self.table_signature=None; self.key_response_file=None
        root.geometry("1120x780"); root.minsize(900,650); self.build(); self.apply_language(); self.load_values(); root.after(100,self.poll); root.protocol("WM_DELETE_WINDOW",self.close)
    def t(self,k): return L[self.lang][k]
    def build(self):
        self.header=ttk.Frame(self.root,padding=12); self.header.pack(fill="x")
        self.title=ttk.Label(self.header,font=("Sans",18,"bold")); self.title.pack(side="left")
        self.langbox=ttk.Combobox(self.header,values=["العربية","English","中文"],state="readonly",width=12); self.langbox.pack(side="right"); self.langbox.bind("<<ComboboxSelected>>",self.change_lang)
        cfg=ttk.LabelFrame(self.root,padding=10); cfg.pack(fill="x",padx=12)
        fields=[("source",True),("output",True),("prices",True),("providers",False),("sample",False)]
        for row,(key,browse) in enumerate(fields):
            label=ttk.Label(cfg); label.grid(row=row,column=0,sticky="w",padx=4,pady=4); self.vars[key]=tk.StringVar(); entry=ttk.Entry(cfg,textvariable=self.vars[key]); entry.grid(row=row,column=1,sticky="ew",padx=4)
            if browse: ttk.Button(cfg,text="…",width=4,command=lambda k=key:self.browse(k)).grid(row=row,column=2)
            setattr(self,key+"_label",label)
        cfg.columnconfigure(1,weight=1)
        keys=ttk.Notebook(cfg); keys.grid(row=5,column=0,columnspan=3,sticky="ew",pady=5)
        for provider in ("GEMINI","OPENAI","ANTHROPIC"):
            page=ttk.Frame(keys,padding=6); keys.add(page,text=provider)
            for i in range(1,5):
                name=f"{provider}_API_KEY_{i}"; ttk.Label(page,text=f"API key {i}").grid(row=i-1,column=0,sticky="w",padx=4,pady=2)
                self.vars[name]=tk.StringVar(); ttk.Entry(page,textvariable=self.vars[name],show="•").grid(row=i-1,column=1,sticky="ew",padx=4,pady=2)
            page.columnconfigure(1,weight=1)
        actions=ttk.Frame(self.root,padding=(12,8)); actions.pack(fill="x")
        self.buttons={k:ttk.Button(actions,command=getattr(self,k)) for k in ("start","stop","resume","save","open")}
        for b in self.buttons.values(): b.pack(side="left",padx=3)
        self.status=tk.StringVar(); ttk.Label(actions,textvariable=self.status).pack(side="right")
        prog=ttk.LabelFrame(self.root,padding=8); prog.pack(fill="x",padx=12); self.progress_label=prog
        self.bar=ttk.Progressbar(prog,maximum=100); self.bar.pack(fill="x"); self.progress_text=tk.StringVar(); ttk.Label(prog,textvariable=self.progress_text).pack(anchor="w")
        pan=ttk.Panedwindow(self.root,orient="vertical"); pan.pack(fill="both",expand=True,padx=12,pady=8)
        table_frame=ttk.Frame(pan); log_frame=ttk.Frame(pan); pan.add(table_frame,weight=2); pan.add(log_frame,weight=1)
        self.tabs=ttk.Notebook(table_frame); self.tabs.pack(fill="both",expand=True); self.trees={}
        for key in ("completed","pending","failed"):
            frame=ttk.Frame(self.tabs); tree=ttk.Treeview(frame,columns=("file","state"),show="headings"); tree.heading("file",text="Filename"); tree.heading("state",text="Status"); tree.pack(fill="both",expand=True); self.tabs.add(frame,text=key); self.trees[key]=tree
        self.log=tk.Text(log_frame,height=10,wrap="word",state="disabled"); self.log.pack(fill="both",expand=True)
    def apply_language(self):
        self.root.title(self.t("title")); self.title.config(text=self.t("title")); self.langbox.set({"ar":"العربية","en":"English","zh":"中文"}[self.lang])
        for k in ("source","output","prices","providers","sample"): getattr(self,k+"_label").config(text=self.t(k))
        for k,b in self.buttons.items(): b.config(text=self.t(k))
        self.progress_label.config(text=self.t("progress")); self.status.set(self.t("ready"))
        for i,k in enumerate(("completed","pending","failed")): self.tabs.tab(i,text=self.t(k))
    def change_lang(self,event=None): self.lang={"العربية":"ar","English":"en","中文":"zh"}[self.langbox.get()]; self.apply_language()
    def load_values(self):
        mapping={"source":"PRODUCT_SOURCE","output":"PRODUCT_OUTPUT","prices":"PRICES_FILE","providers":"AI_PROVIDERS","sample":"PHOTO_LIMIT"}
        for gui,env in mapping.items(): self.vars[gui].set(self.values.get(env,""))
        for k in KEY_NAMES:
            legacy=k.rsplit("_",1)[0] if k.endswith("_1") else ""
            self.vars[k].set(self.values.get(k,"") or self.values.get(legacy,""))
    def browse(self,key):
        value=filedialog.askopenfilename() if key=="prices" else filedialog.askdirectory()
        if value:self.vars[key].set(value)
    def collect(self):
        v=dict(self.values); v.update({"APP_LANGUAGE":self.lang,"PRODUCT_SOURCE":self.vars["source"].get(),"PRODUCT_OUTPUT":self.vars["output"].get(),"PRICES_FILE":self.vars["prices"].get(),"AI_PROVIDERS":self.vars["providers"].get() or "gemini","PHOTO_LIMIT":self.vars["sample"].get()})
        for k in KEY_NAMES: v[k]=self.vars[k].get()
        return v
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
        self.p=subprocess.Popen(self.command(),cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=0,creationflags=flags); self.status.set(self.t("running")); threading.Thread(target=self.reader,daemon=True).start()
    def resume(self): self.start()
    def stop(self):
        if self.p and self.p.poll() is None:
            try:self.p.send_signal(signal.CTRL_BREAK_EVENT if os.name=="nt" else signal.SIGINT)
            except (OSError,ValueError):self.p.terminate()
            self.status.set(self.t("stopped"))
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
                if line=="__DONE__": self.status.set(self.t("ready")); self.refresh_tables(); continue
                if line.startswith("__PRODUCT_SORTER_KEY_REQUEST__:"):
                    self.ask_replacement_key(line.split(":",1)[1]); continue
                self.append_log(line); m=re.search(r"(\d+)%.*?(\d+)/(\d+)",line)
                if m:self.bar["value"]=int(m.group(1)); self.progress_text.set(line)
        except queue.Empty:pass
        self.refresh_tables(); self.root.after(500,self.poll)
    def append_log(self,line): self.log.config(state="normal"); self.log.insert("end",line+"\n"); self.log.see("end"); self.log.config(state="disabled")
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
