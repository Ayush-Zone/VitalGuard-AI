import tkinter as tk
from tkinter import filedialog,messagebox
import cv2,pandas as pd,os
from PIL import Image,ImageTk

W,H=854,480
WINDOW,STEP=4.0,2.0
COLUMNS=["esp_timestamp_ms","accel_x","accel_y","accel_z","gyro_x","gyro_y","gyro_z","temperature"]
LABELS=["Falling","Sitting","Sleeping","Walking"]
KEYS={"1":"Falling","2":"Sitting","3":"Sleeping","4":"Walking"}
ENCODING={"Falling":1,"Sitting":2,"Sleeping":3,"Walking":4}

class Labeler:
    def __init__(self,root):
        self.root=root; root.title("VitalGuardAI - Data Labeler"); root.geometry("1100x760")
        self.cap=None; self.df=None; self.csv_path=None; self.video_duration=0; self.video_fps=30
        self.window_start=0; self.window_end=WINDOW; self.segments={}; self.playing=False; self.after_id=None
        self.ui(); root.bind("<KeyPress>",self.key); root.protocol("WM_DELETE_WINDOW",self.close)

    def ui(self):
        top=tk.Frame(self.root,padx=10,pady=8); top.pack(fill="x")
        for text,cmd,width in [("Open Video",self.open_video,15),("Open CSV",self.open_csv,15),("Save Labels",self.save_labels,15),("Save Labeled CSV",self.save_csv,18)]:
            tk.Button(top,text=text,width=width,command=cmd).pack(side="left",padx=4)
        box=tk.Frame(self.root,width=W,height=H,bg="black"); box.pack(pady=5); box.pack_propagate(False)
        self.video=tk.Label(box,bg="black",fg="white",text="Open video"); self.video.pack(fill="both",expand=True)
        self.time=tk.Label(self.root,text="00:00.00 / 00:00.00",font=("Consolas",14,"bold")); self.time.pack()
        info=tk.Frame(self.root,padx=10); info.pack(fill="x")
        self.window=tk.Label(info,text="Window: -- → --",font=("Arial",12,"bold")); self.window.pack(side="left")
        self.progress=tk.Label(info,text="Segment: --"); self.progress.pack(side="right")
        self.timeline=tk.Scale(self.root,from_=0,to=100,resolution=.01,orient="horizontal",showvalue=False,command=self.timeline_changed); self.timeline.pack(fill="x",padx=15)
        controls=tk.Frame(self.root,pady=5); controls.pack()
        tk.Button(controls,text="◀ Previous",width=15,command=self.previous).pack(side="left",padx=5)
        tk.Button(controls,text="Next ▶",width=15,command=self.next).pack(side="left",padx=5)
        tk.Label(self.root,text="Label current 4-second window",font=("Arial",12,"bold")).pack(pady=3)
        buttons=tk.Frame(self.root); buttons.pack()
        for label in LABELS:
            tk.Button(buttons,text=label,width=14,height=2,command=lambda x=label:self.label(x)).pack(side="left",padx=4)
        tk.Button(self.root,text="SKIP  [SPACE]",width=20,height=2,command=self.skip).pack(pady=6)
        tk.Label(self.root,text="1 Falling | 2 Sitting | 3 Sleeping | 4 Walking | SPACE Skip").pack()
        self.status=tk.Label(self.root,text="Open video and CSV to begin.",anchor="w",padx=10); self.status.pack(fill="x")

    def fmt(self,t):
        t=max(0,float(t)); return f"{int(t//60):02d}:{t%60:05.2f}"

    def open_video(self):
        p=filedialog.askopenfilename(filetypes=[("Video","*.mp4 *.avi *.mov *.mkv"),("All","*.*")])
        if not p:return
        if self.cap:self.cap.release()
        self.cap=cv2.VideoCapture(p)
        if not self.cap.isOpened(): messagebox.showerror("Error","Could not open video."); return
        self.video_fps=self.cap.get(cv2.CAP_PROP_FPS) or 30
        frames=int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)); self.video_duration=frames/self.video_fps
        self.timeline.config(to=max(0,self.video_duration-WINDOW)); self.window_start=0
        self.update_window(); self.start()
        self.status.config(text=f"Video: {os.path.basename(p)} | {self.video_fps:.2f} FPS | {self.video_duration:.2f}s")

    def open_csv(self):
        p=filedialog.askopenfilename(filetypes=[("CSV","*.csv"),("All","*.*")])
        if not p:return
        try:df=pd.read_csv(p)
        except Exception as e:messagebox.showerror("CSV Error",str(e)); return
        missing=[c for c in COLUMNS if c not in df.columns]
        if missing:messagebox.showerror("Invalid CSV","Missing columns:\n\n"+"\n".join(missing)); return
        self.df=df[COLUMNS].copy()
        for c in COLUMNS:self.df[c]=pd.to_numeric(self.df[c],errors="coerce")
        self.df=self.df.dropna(subset=["esp_timestamp_ms"]).sort_values("esp_timestamp_ms").reset_index(drop=True)
        if len(self.df)<2:messagebox.showerror("Invalid CSV","Too few sensor rows."); return
        self.csv_path=p; start=self.df.esp_timestamp_ms.iloc[0]; end=self.df.esp_timestamp_ms.iloc[-1]
        duration=(end-start)/1000; rate=(len(self.df)-1)/duration if duration else 0
        print(f"\nCSV rows: {len(self.df):,}\nSensor duration: {duration:.3f}s\nSensor rate: {rate:.2f} Hz")
        self.status.config(text=f"CSV: {os.path.basename(p)} | {len(self.df):,} rows | {rate:.2f} Hz")

    def get_frame(self,t):
        if not self.cap:return None
        self.cap.set(cv2.CAP_PROP_POS_FRAMES,int(max(0,min(t,self.video_duration))*self.video_fps))
        ok,f=self.cap.read(); return f if ok else None

    def show(self,f,t):
        if f is None:return
        f=cv2.resize(f,(W,H)); cv2.rectangle(f,(12,12),(260,62),(0,0,0),-1)
        cv2.putText(f,f"{self.fmt(t)} / {self.fmt(self.video_duration)}",(22,47),cv2.FONT_HERSHEY_SIMPLEX,.75,(255,255,255),2)
        im=ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(f,cv2.COLOR_BGR2RGB)))
        self.video.config(image=im,text=""); self.video.image=im; self.time.config(text=f"{self.fmt(t)} / {self.fmt(self.video_duration)}")

    def update_window(self):
        if not self.cap:return
        max_start=max(0,self.video_duration-WINDOW)
        self.window_start=min(max(0,self.window_start),max_start); self.window_end=min(self.window_start+WINDOW,self.video_duration)
        self.timeline.set(self.window_start)
        total=max(1,int(max_start/STEP)+1); current=min(total,int(round(self.window_start/STEP))+1)
        self.window.config(text=f"Window: {self.fmt(self.window_start)} → {self.fmt(self.window_end)}")
        self.progress.config(text=f"Segment: {current} / {total}")
        self.show(self.get_frame(self.window_start),self.window_start)

    def start(self):
        if not self.cap:return
        self.stop(); self.playing=True
        self.cap.set(cv2.CAP_PROP_POS_FRAMES,int(self.window_start*self.video_fps)); self.play()

    def stop(self):
        self.playing=False
        if self.after_id:
            try:self.root.after_cancel(self.after_id)
            except:pass
            self.after_id=None

    def play(self):
        if not self.playing or not self.cap:return
        t=self.cap.get(cv2.CAP_PROP_POS_FRAMES)/self.video_fps
        if t>=self.window_end:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES,int(self.window_start*self.video_fps)); t=self.window_start
        ok,f=self.cap.read()
        if ok:self.show(f,t)
        self.after_id=self.root.after(max(1,int(1000/self.video_fps)),self.play)

    def label(self,label):
        if self.df is None or self.cap is None:
            messagebox.showwarning("Required","Open both video and CSV."); return
        self.stop()
        window_id=round(self.window_start/STEP)
        self.segments[window_id]=(self.window_start,self.window_end,label)
        self.status.config(text=f"Window {window_id}: {self.fmt(self.window_start)} → {self.fmt(self.window_end)} = {label}")
        self.next()

    def skip(self):
        if self.cap:self.stop(); self.next()

    def next(self):
        if not self.cap:return
        max_start=max(0,self.video_duration-WINDOW); total=max(1,int(max_start/STEP)+1)
        current=min(total,int(round(self.window_start/STEP))+1)
        if current>=total:
            self.window_start=max_start; self.update_window(); self.stop()
            if self.segments:self.finish_save()
            else:messagebox.showwarning("No Labels","No windows were labeled.")
            return
        self.window_start=min(current*STEP,max_start); self.update_window(); self.start()

    def previous(self):
        if not self.cap:return
        self.stop(); self.window_start=max(0,self.window_start-STEP); self.update_window(); self.start()

    def timeline_changed(self,value):
        if not self.cap:return
        try:self.window_start=float(value)
        except:return
        self.stop(); self.update_window(); self.start()

    def key(self,e):
        k=e.keysym.lower()
        if k in KEYS:self.label(KEYS[k])
        elif k=="space":self.skip()
        elif k=="right":self.next()
        elif k=="left":self.previous()

    def build_labels(self):
        return pd.DataFrame([[i,s,e,ENCODING[l]] for i,(s,e,l) in sorted(self.segments.items())],columns=["window_id","start_sec","end_sec","label"])

    def build_combined(self):
        sensor_start=float(self.df.esp_timestamp_ms.iloc[0]); parts=[]
        for i,(start,end,label) in sorted(self.segments.items()):
            a=sensor_start+start*1000; b=sensor_start+end*1000
            part=self.df[(self.df.esp_timestamp_ms>=a)&(self.df.esp_timestamp_ms<b)].copy()
            if len(part):
                part.insert(0,"window_id",i); part["label"]=ENCODING[label]; parts.append(part)
        return pd.concat(parts,ignore_index=True)[["window_id"]+COLUMNS+["label"]] if parts else pd.DataFrame()

    def finish_save(self):
        folder=os.path.dirname(self.csv_path)
        labels_path=os.path.join(folder,"labels.csv")
        combined_path=os.path.join(folder,"sensor_data_labeled.csv")
        try:
            labels=self.build_labels(); combined=self.build_combined()
            if combined.empty:
                messagebox.showwarning("No Data","No sensor samples found inside labeled windows."); return
            labels.to_csv(labels_path,index=False)
            combined.to_csv(combined_path,index=False)
            messagebox.showinfo("Dataset Saved",f"Labeling completed.\n\nWindow labels:\n{labels_path}\n\nCombined labeled CSV:\n{combined_path}\n\nWindows: {len(labels)}\nRows: {len(combined):,}")
            self.status.config(text=f"Saved labels.csv + sensor_data_labeled.csv | {len(labels)} windows | {len(combined):,} rows")
        except Exception as e:
            messagebox.showerror("Save Error",f"Could not save dataset:\n\n{e}")

    def save_labels(self):
        if not self.segments:
            messagebox.showwarning("No Labels","No labeled windows found."); return
        p=filedialog.asksaveasfilename(title="Save Window Labels",defaultextension=".csv",initialfile="labels.csv",filetypes=[("CSV","*.csv")])
        if not p:return
        try:self.build_labels().to_csv(p,index=False)
        except Exception as e:messagebox.showerror("Save Error",str(e)); return
        self.status.config(text=f"Labels saved: {os.path.basename(p)}")
        messagebox.showinfo("Saved",f"Window labels saved:\n{p}")

    def save_csv(self):
        if self.df is None or not self.segments:
            messagebox.showwarning("No Data","Open CSV and label at least one window."); return
        result=self.build_combined()
        if result.empty:
            messagebox.showwarning("No Data","No sensor samples found inside labeled windows."); return
        base=os.path.splitext(os.path.basename(self.csv_path))[0]
        p=filedialog.asksaveasfilename(title="Save Labeled CSV",defaultextension=".csv",initialfile=base+"_labeled.csv",filetypes=[("CSV","*.csv")])
        if not p:return
        try:result.to_csv(p,index=False)
        except Exception as e:messagebox.showerror("Save Error",str(e)); return
        messagebox.showinfo("Saved Successfully",f"Saved:\n{p}\n\nRows: {len(result):,}\nWindows: {len(self.segments)}")
        self.status.config(text=f"Saved: {os.path.basename(p)} | {len(result):,} rows")

    def close(self):
        self.stop()
        if self.cap:self.cap.release()
        self.root.destroy()

root=tk.Tk()
Labeler(root)
root.mainloop()