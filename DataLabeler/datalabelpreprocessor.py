import tkinter as tk
from tkinter import filedialog,messagebox
import cv2,pandas as pd,numpy as np,os,joblib
from PIL import Image,ImageTk
from scipy.signal import butter,filtfilt
from sklearn.preprocessing import StandardScaler

# ============================== CONFIGURATION ==============================
W,H=854,480
VIDEO_WINDOW=4.0
VIDEO_STEP=2.0
FS=50.0
CUTOFF=6.0
FILTER_ORDER=4
WINDOW=int(FS*4)
STEP=int(FS*2)
SENSOR=["accel_x","accel_y","accel_z","gyro_x","gyro_y","gyro_z"]
FEATURES=SENSOR+["accel_mag","gyro_mag"]
LABELS=["Falling","Sitting","Sleeping","Standing","Walking"]
KEYS={"1":"Falling","2":"Sitting","3":"Sleeping","4":"Standing","5":"Walking"}
ENCODING={"Falling":1,"Sitting":2,"Sleeping":3,"Standing":4,"Walking":5}
LABEL_NAMES={1:"Falling",2:"Sitting",3:"Sleeping",4:"Standing",5:"Walking"}
INPUT_COLUMNS=["pc_timestamp","relative_time_sec","esp_timestamp_ms","accel_x","accel_y","accel_z","gyro_x","gyro_y","gyro_z","temperature"]
OUTPUT_COLUMNS=["esp_timestamp_ms","accel_x","accel_y","accel_z","gyro_x","gyro_y","gyro_z","temperature","label"]
# ============================================================================

class VitalGuardLabeler:
    def __init__(self,root):
        self.root=root
        self.root.title("VitalGuard AI - Video + Sensor Labeler + Preprocessor")
        self.root.geometry("1100x800")
        self.root.minsize(950,740)
        self.cap=None
        self.df=None
        self.video_path=None
        self.csv_path=None
        self.output_path=None
        self.video_fps=30.0
        self.video_frames=0
        self.video_duration=0.0
        self.sensor_start=0.0
        self.sensor_end=0.0
        self.sensor_duration=0.0
        self.window_start=0.0
        self.window_end=VIDEO_WINDOW
        self.segments=[]
        self.playing=False
        self.after_id=None
        self.build_ui()
        self.root.bind("<KeyPress>",self.key_pressed)
        self.root.protocol("WM_DELETE_WINDOW",self.close)

    def build_ui(self):
        top=tk.Frame(self.root,padx=10,pady=8)
        top.pack(fill="x")
        for text,cmd,width in [("Open Video",self.open_video,15),("Open Sensor CSV",self.open_csv,18),("Generate Dataset",self.generate_dataset,20)]:
            tk.Button(top,text=text,width=width,command=cmd).pack(side="left",padx=4)
        video=tk.Frame(self.root,width=W,height=H,bg="black")
        video.pack(pady=5)
        video.pack_propagate(False)
        self.video_label=tk.Label(video,bg="black",fg="white",text="Open video")
        self.video_label.pack(fill="both",expand=True)
        self.time_label=tk.Label(self.root,text="00:00.00 / 00:00.00",font=("Consolas",14,"bold"))
        self.time_label.pack(pady=2)
        info=tk.Frame(self.root,padx=10)
        info.pack(fill="x")
        self.window_label=tk.Label(info,text="Window: -- → --",font=("Arial",12,"bold"))
        self.window_label.pack(side="left")
        self.progress_label=tk.Label(info,text="Segment: --",font=("Arial",11))
        self.progress_label.pack(side="right")
        self.timeline=tk.Scale(self.root,from_=0,to=100,resolution=0.01,orient="horizontal",showvalue=False,command=self.timeline_changed)
        self.timeline.pack(fill="x",padx=15)
        controls=tk.Frame(self.root,pady=5)
        controls.pack()
        tk.Button(controls,text="◀ Previous",width=15,command=self.previous_window).pack(side="left",padx=5)
        tk.Button(controls,text="Next ▶",width=15,command=self.next_window).pack(side="left",padx=5)
        frame=tk.Frame(self.root,pady=5)
        frame.pack()
        tk.Label(frame,text="Label current 4-second window",font=("Arial",12,"bold")).pack()
        buttons=tk.Frame(frame)
        buttons.pack(pady=6)
        for label in LABELS:
            tk.Button(buttons,text=label,width=14,height=2,command=lambda x=label:self.label_window(x)).pack(side="left",padx=4)
        tk.Button(frame,text="SKIP  [SPACE]",width=20,height=2,command=self.skip_window).pack(pady=3)
        tk.Label(self.root,text="1 Falling | 2 Sitting | 3 Sleeping | 4 Standing | 5 Walking | SPACE Skip | ← Previous | → Next",font=("Arial",10)).pack(pady=3)
        self.status=tk.Label(self.root,text="Open video and sensor CSV to begin.",anchor="w",padx=10)
        self.status.pack(fill="x")

    @staticmethod
    def fmt(t):
        t=max(0,float(t))
        return f"{int(t//60):02d}:{t%60:05.2f}"

    def set_status(self,text):
        self.status.config(text=text)
        self.root.update_idletasks()

    def open_video(self):
        path=filedialog.askopenfilename(title="Select Video",filetypes=[("Video files","*.mp4 *.avi *.mov *.mkv"),("All files","*.*")])
        if not path:return
        self.stop()
        if self.cap:self.cap.release()
        self.cap=cv2.VideoCapture(path)
        if not self.cap.isOpened():
            messagebox.showerror("Error","Could not open video.")
            self.cap=None
            return
        self.video_path=path
        self.video_fps=self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.video_frames=int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.video_duration=self.video_frames/self.video_fps
        self.timeline.config(to=max(0,self.video_duration-VIDEO_WINDOW))
        self.window_start=0
        self.segments=[]
        self.set_status(f"Video: {os.path.basename(path)} | {self.video_fps:.2f} FPS | {self.video_duration:.2f}s")
        self.update_window()
        self.start()

    def open_csv(self):
        path=filedialog.askopenfilename(title="Select Raw Sensor CSV",filetypes=[("CSV files","*.csv"),("All files","*.*")])
        if not path:return
        try:df=pd.read_csv(path)
        except Exception as e:
            messagebox.showerror("CSV Error",str(e))
            return
        missing=[c for c in INPUT_COLUMNS if c not in df.columns]
        if missing:
            messagebox.showerror("Invalid CSV","Missing columns:\n\n"+"\n".join(missing))
            return
        df["relative_time_sec"]=pd.to_numeric(df["relative_time_sec"],errors="coerce")
        df["esp_timestamp_ms"]=pd.to_numeric(df["esp_timestamp_ms"],errors="coerce")
        for c in SENSOR+["temperature"]:df[c]=pd.to_numeric(df[c],errors="coerce")
        df=df.dropna(subset=["relative_time_sec"]+SENSOR+["temperature"]).sort_values("relative_time_sec").reset_index(drop=True)
        if len(df)<2:
            messagebox.showerror("Invalid CSV","CSV contains too few sensor rows.")
            return
        self.df=df
        self.csv_path=path
        self.sensor_start=float(df["relative_time_sec"].iloc[0])
        self.sensor_end=float(df["relative_time_sec"].iloc[-1])
        self.sensor_duration=self.sensor_end-self.sensor_start
        rate=(len(df)-1)/self.sensor_duration if self.sensor_duration>0 else 0
        print("\n"+"="*60)
        print("SENSOR DATA INFORMATION")
        print("="*60)
        print(f"CSV rows          : {len(df):,}")
        print(f"Relative start    : {self.sensor_start:.3f}s")
        print(f"Relative end      : {self.sensor_end:.3f}s")
        print(f"Sensor duration   : {self.sensor_duration:.3f}s")
        print(f"Effective rate    : {rate:.2f} Hz")
        esp=df["esp_timestamp_ms"].dropna()
        if len(esp):
            print(f"ESP start         : {esp.iloc[0]:.0f} ms")
            print(f"ESP end           : {esp.iloc[-1]:.0f} ms")
            print(f"ESP duration      : {(esp.iloc[-1]-esp.iloc[0])/1000:.3f}s")
        if self.video_duration:
            diff=abs(self.video_duration-self.sensor_duration)
            print(f"Video duration    : {self.video_duration:.3f}s")
            print(f"Difference        : {diff:.3f}s")
        print("="*60)
        self.set_status(f"CSV: {os.path.basename(path)} | {len(df):,} rows | {self.sensor_duration:.2f}s | {rate:.2f} Hz")

    def get_frame(self,t):
        if not self.cap:return None
        frame_no=int(max(0,min(t,self.video_duration))*self.video_fps)
        self.cap.set(cv2.CAP_PROP_POS_FRAMES,frame_no)
        ok,frame=self.cap.read()
        return frame if ok else None

    def display(self,frame,t):
        if frame is None:return
        frame=cv2.resize(frame,(W,H),interpolation=cv2.INTER_AREA)
        text=f"{self.fmt(t)} / {self.fmt(self.video_duration)}"
        cv2.rectangle(frame,(12,12),(250,62),(0,0,0),-1)
        cv2.putText(frame,text,(22,47),cv2.FONT_HERSHEY_SIMPLEX,.75,(255,255,255),2,cv2.LINE_AA)
        frame=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
        photo=ImageTk.PhotoImage(Image.fromarray(frame))
        self.video_label.config(image=photo,text="")
        self.video_label.image=photo
        self.time_label.config(text=text)

    def update_window(self):
        if not self.cap:return
        self.window_end=min(self.window_start+VIDEO_WINDOW,self.video_duration)
        self.timeline.set(self.window_start)
        self.window_label.config(text=f"Window: {self.fmt(self.window_start)} → {self.fmt(self.window_end)}")
        total=max(1,int((self.video_duration-VIDEO_WINDOW)/VIDEO_STEP)+1)
        current=int(self.window_start/VIDEO_STEP)+1
        self.progress_label.config(text=f"Segment: {current} / {total}")
        self.display(self.get_frame(self.window_start),self.window_start)

    def start(self):
        if not self.cap:return
        self.stop()
        self.playing=True
        self.cap.set(cv2.CAP_PROP_POS_FRAMES,int(self.window_start*self.video_fps))
        self.play()

    def stop(self):
        self.playing=False
        if self.after_id:
            try:self.root.after_cancel(self.after_id)
            except:pass
            self.after_id=None

    def play(self):
        if not self.playing or not self.cap:return
        frame_no=self.cap.get(cv2.CAP_PROP_POS_FRAMES)
        t=frame_no/self.video_fps
        if t>=self.window_end:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES,int(self.window_start*self.video_fps))
            t=self.window_start
        ok,frame=self.cap.read()
        if ok:self.display(frame,t)
        self.after_id=self.root.after(max(1,int(1000/self.video_fps)),self.play)

    def label_window(self,label):
        if self.df is None:
            messagebox.showwarning("CSV Required","Open the sensor CSV first.")
            return
        if not self.cap:
            messagebox.showwarning("Video Required","Open the video first.")
            return
        self.stop()
        self.segments=[x for x in self.segments if not(abs(x[0]-self.window_start)<.001 and abs(x[1]-self.window_end)<.001)]
        self.segments.append((self.window_start,self.window_end,label))
        self.set_status(f"{self.fmt(self.window_start)} → {self.fmt(self.window_end)} = {label} ({ENCODING[label]})")
        self.next_window()

    def skip_window(self):
        if not self.cap:return
        self.stop()
        self.set_status(f"Skipped {self.fmt(self.window_start)} → {self.fmt(self.window_end)}")
        self.next_window()

    def next_window(self):
        if not self.cap:return
        new_start=self.window_start+VIDEO_STEP
        if new_start+0.001>=self.video_duration:
            self.window_start=max(0,self.video_duration-VIDEO_WINDOW)
            self.update_window()
            self.stop()
            self.finish()
            return
        self.window_start=new_start
        self.update_window()
        self.start()

    def previous_window(self):
        if not self.cap:return
        self.stop()
        self.window_start=max(0,self.window_start-VIDEO_STEP)
        self.update_window()
        self.start()

    def timeline_changed(self,value):
        if not self.cap:return
        try:self.window_start=float(value)
        except:return
        self.stop()
        self.update_window()
        self.start()

    def key_pressed(self,event):
        key=event.keysym.lower()
        if key in KEYS:self.label_window(KEYS[key])
        elif key=="space":self.skip_window()
        elif key=="right":self.next_window()
        elif key=="left":self.previous_window()

    # ============================== LABEL CREATION ==============================

    def sensor_mask(self,start,end):
        if self.df is None:return None
        start+=self.sensor_start
        end+=self.sensor_start
        t=self.df["relative_time_sec"]
        return (t>=start)&(t<end)

    def labeled_data(self):
        if self.df is None:return None
        parts=[]
        for start,end,label in sorted(self.segments,key=lambda x:x[0]):
            part=self.df.loc[self.sensor_mask(start,end)].copy()
            if len(part):
                part["label"]=ENCODING[label]
                parts.append(part)
        if not parts:return None
        result=pd.concat(parts,ignore_index=True)
        return result[OUTPUT_COLUMNS]

    # ============================== AUTOMATIC PREPROCESSING ==============================

    def preprocess(self,labeled):
        print("\n"+"="*60)
        print("VITALGUARD AI - PREPROCESSING")
        print("="*60)
        print(f"Input labeled rows : {len(labeled):,}")
        df=labeled.copy()
        required=["esp_timestamp_ms",*SENSOR,"temperature","label"]
        missing=[c for c in required if c not in df.columns]
        if missing:raise ValueError(f"Missing columns: {missing}")
        for c in required:df[c]=pd.to_numeric(df[c],errors="coerce")
        df=df.dropna(subset=required).sort_values("esp_timestamp_ms").drop_duplicates().reset_index(drop=True)
        df["label"]=df["label"].astype(int)
        df=df[df.label.isin(LABEL_NAMES)].reset_index(drop=True)
        if len(df)<2:raise ValueError("Not enough valid labeled sensor data.")
        t=(df.esp_timestamp_ms.to_numpy()-df.esp_timestamp_ms.iloc[0])/1000
        dt=np.diff(t)
        dt=dt[dt>0]
        measured_rate=1/np.median(dt) if len(dt) else 0
        print(f"Measured rate      : {measured_rate:.2f} Hz")
        print(f"Target rate        : {FS:.0f} Hz")
        if t[-1]<4:raise ValueError("Labeled data is shorter than 4 seconds.")
        nt=np.arange(0,t[-1]+1/FS,1/FS)
        p=pd.DataFrame({"time_sec":nt})
        for c in SENSOR+["temperature"]:p[c]=np.interp(nt,t,df[c].to_numpy())
        idx=np.clip(np.searchsorted(t,nt),0,len(df)-1)
        p["label"]=df.label.to_numpy()[idx]
        b,a=butter(FILTER_ORDER,CUTOFF/(FS/2),btype="low")
        for c in SENSOR:p[c]=filtfilt(b,a,p[c].to_numpy())
        p["accel_mag"]=np.sqrt(p.accel_x**2+p.accel_y**2+p.accel_z**2)
        p["gyro_mag"]=np.sqrt(p.gyro_x**2+p.gyro_y**2+p.gyro_z**2)
        p["esp_timestamp_ms"]=np.round(df.esp_timestamp_ms.iloc[0]+nt*1000).astype(np.int64)
        p=p[["esp_timestamp_ms"]+SENSOR+["temperature","label","accel_mag","gyro_mag"]]
        data=p[FEATURES].to_numpy(np.float32)
        labels=p.label.to_numpy(np.int64)
        X=[];y=[];times=[]
        for s in range(0,len(data)-WINDOW+1,STEP):
            e=s+WINDOW
            u,c=np.unique(labels[s:e],return_counts=True)
            X.append(data[s:e])
            y.append(int(u[np.argmax(c)]))
            times.append(p.esp_timestamp_ms.iloc[s])
        if not X:raise ValueError("Not enough data for a 4-second window.")
        X=np.asarray(X,np.float32)
        y=np.asarray(y,np.int64)
        times=np.asarray(times,np.int64)
        n=len(X)
        if n<3:raise ValueError(f"Only {n} windows were created. At least 3 windows are required for Train/Validation/Test.")
        a=max(1,int(n*.70))
        b=max(a+1,int(n*.85))
        b=min(b,n-1)
        X_train,y_train=X[:a],y[:a]
        X_val,y_val=X[a:b],y[a:b]
        X_test,y_test=X[b:],y[b:]
        scaler=StandardScaler().fit(X_train.reshape(-1,X_train.shape[-1]))
        def scale(x):
            s=x.shape
            return scaler.transform(x.reshape(-1,s[-1])).reshape(s).astype(np.float32)
        X_train,X_val,X_test=scale(X_train),scale(X_val),scale(X_test)
        out=os.path.join(os.path.dirname(self.csv_path),"preprocessed_dataset")
        os.makedirs(out,exist_ok=True)
        processed=os.path.join(out,"sensor_preprocessed.csv")
        p.to_csv(processed,index=False)
        for name,value in {"X_train":X_train,"y_train":y_train,"X_val":X_val,"y_val":y_val,"X_test":X_test,"y_test":y_test}.items():np.save(os.path.join(out,name+".npy"),value)
        joblib.dump(scaler,os.path.join(out,"scaler.pkl"))
        pd.DataFrame({"window_id":np.arange(len(y)),"start_timestamp_ms":times,"label":y,"label_name":[LABEL_NAMES[int(v)] for v in y]}).to_csv(os.path.join(out,"window_metadata.csv"),index=False)
        print("\n"+"="*60)
        print("PREPROCESSING COMPLETE")
        print("="*60)
        print(f"Processed CSV     : {processed}")
        print(f"Filter            : Butterworth {FILTER_ORDER}th order / {CUTOFF} Hz")
        print(f"Target rate       : {FS:.0f} Hz")
        print(f"Window            : 4 sec / {WINDOW} samples")
        print(f"Step              : 2 sec / {STEP} samples")
        print(f"Features          : {FEATURES}")
        print(f"Total windows     : {len(X):,}")
        print(f"Train             : {X_train.shape}")
        print(f"Validation        : {X_val.shape}")
        print(f"Test              : {X_test.shape}")
        print(f"Output folder     : {out}")
        print("\nLabel distribution:")
        for k,v in LABEL_NAMES.items():print(f"{k} - {v}: {np.sum(y==k):,}")
        print("="*60)
        return out,processed,X_train,y_train,X_val,y_val,X_test,y_test

    # ============================== GENERATE DATASET ==============================

    def generate_dataset(self):
        if self.df is None:
            messagebox.showwarning("CSV Required","Open the raw sensor CSV first.")
            return
        if self.cap is None:
            messagebox.showwarning("Video Required","Open the video first.")
            return
        if not self.segments:
            messagebox.showwarning("No Labels","Label at least one video window first.")
            return
        self.stop()
        try:
            labeled=self.labeled_data()
            if labeled is None or labeled.empty:
                raise ValueError("No sensor data exists inside the labeled windows.")
            base=os.path.splitext(os.path.basename(self.csv_path))[0]
            default=os.path.join(os.path.dirname(self.csv_path),base+"_labeled.csv")
            output=filedialog.asksaveasfilename(title="Save Labeled Sensor CSV",initialfile=os.path.basename(default),initialdir=os.path.dirname(default),defaultextension=".csv",filetypes=[("CSV files","*.csv")])
            if not output:return
            labeled.to_csv(output,index=False)
            self.output_path=output
            self.set_status("Labeled CSV saved. Preprocessing dataset...")
            out,processed,Xtr,ytr,Xv,yv,Xte,yte=self.preprocess(labeled)
            counts=labeled["label"].value_counts()
            stats="\n".join(f"{LABEL_NAMES[k]} ({k}): {counts.get(k,0):,}" for k in LABEL_NAMES)
            messagebox.showinfo("Dataset Complete",f"Labeled CSV:\n{output}\n\nPreprocessed folder:\n{out}\n\nTotal windows: {len(Xtr)+len(Xv)+len(Xte):,}\nTrain: {Xtr.shape}\nValidation: {Xv.shape}\nTest: {Xte.shape}\n\nLabel rows:\n{stats}")
            self.set_status(f"Dataset complete | Train {Xtr.shape} | Validation {Xv.shape} | Test {Xte.shape}")
        except Exception as e:
            messagebox.showerror("Processing Error",str(e))
            self.set_status(f"Processing error: {e}")

    def finish(self):
        if not self.segments:
            if messagebox.askyesno("No Labels","No windows were labeled.\n\nExit?"):self.close()
            return
        labeled=self.labeled_data()
        if labeled is None or labeled.empty:
            messagebox.showwarning("No Data","No sensor data found in labeled windows.")
            return
        answer=messagebox.askyesno("Labeling Complete",f"Labeling is complete.\n\nLabeled windows: {len(self.segments)}\nSensor rows: {len(labeled):,}\n\nGenerate the complete ML dataset now?")
        if answer:self.generate_dataset()

    def close(self):
        self.stop()
        if self.cap:
            self.cap.release()
            self.cap=None
        self.root.destroy()

if __name__=="__main__":
    root=tk.Tk()
    app=VitalGuardLabeler(root)
    root.mainloop()