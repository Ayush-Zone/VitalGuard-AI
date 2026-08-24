import os,numpy as np,pandas as pd,tkinter as tk
from tkinter import filedialog
from scipy.signal import butter,filtfilt
from sklearn.preprocessing import StandardScaler
import joblib

FS,CUTOFF,ORDER=50.,6.,4
WINDOW,STEP=int(FS*4),int(FS*2)
SENSOR=["accel_x","accel_y","accel_z","gyro_x","gyro_y","gyro_z"]
FEATURES=SENSOR+["accel_mag","gyro_mag"]
REQUIRED=["esp_timestamp_ms",*SENSOR,"temperature","label"]
LABELS={1:"Falling",2:"Sitting",3:"Sleeping",4:"Standing",5:"Walking"}

r=tk.Tk();r.withdraw()
INPUT=filedialog.askopenfilename(title="Select Labeled Sensor CSV",filetypes=[("CSV files","*.csv"),("All files","*.*")])
r.destroy()
if not INPUT:raise SystemExit("No CSV selected.")

OUT=os.path.join(os.path.dirname(INPUT),"preprocessed_dataset");os.makedirs(OUT,exist_ok=True)

df=pd.read_csv(INPUT)
missing=[c for c in REQUIRED if c not in df.columns]
if missing:raise ValueError(f"Missing columns: {missing}")
for c in REQUIRED:df[c]=pd.to_numeric(df[c],errors="coerce")
df=df.dropna(subset=REQUIRED).sort_values("esp_timestamp_ms").drop_duplicates().reset_index(drop=True)
df["label"]=df["label"].astype(int);df=df[df.label.isin(LABELS)].reset_index(drop=True)

print("\n"+"="*55+"\nVITALGUARD AI - PREPROCESSING\n"+"="*55)
print(f"Input rows: {len(df):,}")

t=(df.esp_timestamp_ms.to_numpy()-df.esp_timestamp_ms.iloc[0])/1000
dt=np.diff(t);dt=dt[dt>0]
print(f"Measured rate: {1/np.median(dt):.2f} Hz" if len(dt) else "Measured rate: unknown")
print(f"Target rate: {FS:.0f} Hz")

nt=np.arange(0,t[-1]+1/FS,1/FS)
p=pd.DataFrame({"time_sec":nt})
for c in SENSOR+["temperature"]:p[c]=np.interp(nt,t,df[c].to_numpy())

idx=np.clip(np.searchsorted(t,nt),0,len(df)-1)
p["label"]=df.label.to_numpy()[idx]

b,a=butter(ORDER,CUTOFF/(FS/2),btype="low")
for c in SENSOR:p[c]=filtfilt(b,a,p[c].to_numpy())

p["accel_mag"]=np.sqrt(p.accel_x**2+p.accel_y**2+p.accel_z**2)
p["gyro_mag"]=np.sqrt(p.gyro_x**2+p.gyro_y**2+p.gyro_z**2)
p["esp_timestamp_ms"]=np.round(df.esp_timestamp_ms.iloc[0]+nt*1000).astype(np.int64)
p=p[REQUIRED+["accel_mag","gyro_mag"]]

processed=os.path.join(OUT,"sensor_preprocessed.csv")
p.to_csv(processed,index=False)

# ==================== WINDOWS ====================

data=p[FEATURES].to_numpy(np.float32)
labels=p.label.to_numpy(np.int64)
X=[];y=[];times=[]

for s in range(0,len(data)-WINDOW+1,STEP):
    e=s+WINDOW;u,c=np.unique(labels[s:e],return_counts=True)
    X.append(data[s:e]);y.append(int(u[np.argmax(c)]));times.append(p.esp_timestamp_ms.iloc[s])

if not X:raise ValueError("Not enough data for a 4-second window.")

X=np.asarray(X,np.float32);y=np.asarray(y,np.int64);times=np.asarray(times,np.int64)

# ==================== SPLIT ====================

n=len(X);a=int(n*.70);b=int(n*.85)
X_train,y_train=X[:a],y[:a]
X_val,y_val=X[a:b],y[a:b]
X_test,y_test=X[b:],y[b:]

# ==================== Z-SCORE ====================

scaler=StandardScaler().fit(X_train.reshape(-1,X_train.shape[-1]))

def scale(x):
    s=x.shape
    return scaler.transform(x.reshape(-1,s[-1])).reshape(s).astype(np.float32)

X_train,X_val,X_test=scale(X_train),scale(X_val),scale(X_test)

# ==================== SAVE ====================

for name,value in {"X_train":X_train,"y_train":y_train,"X_val":X_val,"y_val":y_val,"X_test":X_test,"y_test":y_test}.items():
    np.save(os.path.join(OUT,name+".npy"),value)

joblib.dump(scaler,os.path.join(OUT,"scaler.pkl"))

pd.DataFrame({
    "window_id":np.arange(len(y)),
    "start_timestamp_ms":times,
    "label":y,
    "label_name":[LABELS[int(v)] for v in y]
}).to_csv(os.path.join(OUT,"window_metadata.csv"),index=False)

print("\n"+"="*55)
print("PREPROCESSING COMPLETE")
print("="*55)
print(f"Processed CSV : {processed}")
print(f"Filter        : Butterworth {ORDER}th order / {CUTOFF} Hz")
print(f"Window        : 4 sec / {WINDOW} samples")
print(f"Step          : 2 sec / {STEP} samples")
print(f"Features      : {FEATURES}")
print(f"Total windows : {len(X):,}")
print(f"Train         : {X_train.shape}")
print(f"Validation    : {X_val.shape}")
print(f"Test          : {X_test.shape}")
print(f"Output folder : {OUT}")
print("\nLabel distribution:")
for k,v in LABELS.items():print(f"{k} - {v}: {np.sum(y==k):,}")
print("="*55)