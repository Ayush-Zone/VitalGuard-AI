import cv2,socket,threading,time,csv,os

CAMERA_ID=0
WIDTH,HEIGHT=854,480
UDP_PORT=5000
DATASET_DIR="dataset"
TARGET_HZ=50
INTERVAL_MS=1000/TARGET_HZ

running=True
sensor_ready=False
recording_active=False
sensor_buffer=[]
lock=threading.Lock()
received_count=0

def create_dataset_folder():
    os.makedirs(DATASET_DIR,exist_ok=True)
    i=0
    while os.path.exists(folder:=os.path.join(DATASET_DIR,f"data{i}")): i+=1
    os.makedirs(folder)
    return folder

def receive_sensor_data():
    global sensor_ready,received_count
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    sock.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,4*1024*1024)
    sock.bind(("0.0.0.0",UDP_PORT))
    sock.settimeout(0.01)
    print(f"Listening on UDP port {UDP_PORT}...")
    while running:
        try: packet,_=sock.recvfrom(1024)
        except socket.timeout: continue
        except OSError: break
        try:
            v=packet.decode().strip().split(",")
            if len(v)!=8: continue
            row=[int(v[0]),float(v[1]),float(v[2]),float(v[3]),float(v[4]),float(v[5]),float(v[6]),float(v[7])]
            sensor_ready=True
            if recording_active:
                with lock:
                    sensor_buffer.append(row)
                    received_count+=1
        except (ValueError,UnicodeDecodeError): continue
    sock.close()

thread=threading.Thread(target=receive_sensor_data,daemon=True)
thread.start()

print("\n=============================================")
print("       VITALGUARD AI DATA CAPTURE")
print("=============================================\n")
print("Waiting for ESP8266 sensor data...")

while not sensor_ready: time.sleep(0.001)
print("Sensor data received.")

folder=create_dataset_folder()
video_file=os.path.join(folder,"video.mp4")
csv_file=os.path.join(folder,"sensor_data.csv")
print(f"\nDataset folder: {folder}")

cap=cv2.VideoCapture(CAMERA_ID)
cap.set(cv2.CAP_PROP_FRAME_WIDTH,WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT,HEIGHT)

if not cap.isOpened():
    print("Camera could not be opened.")
    running=False
    thread.join(timeout=1)
    exit()

print("Camera opened.")
print(f"Resolution: {WIDTH} x {HEIGHT}")
print("\nPress Q or ESC to stop recording.")

with lock:
    sensor_buffer.clear()
    received_count=0

frames=[]
recording_active=True
recording_start=time.perf_counter()
last_report=recording_start
last_received=0

print("\n==============================")
print("RECORDING STARTED")
print("==============================")

while True:
    ret,frame=cap.read()
    if not ret: break

    now=time.perf_counter()
    elapsed=now-recording_start
    frame=cv2.resize(frame,(WIDTH,HEIGHT))
    cv2.putText(frame,f"Time: {elapsed:.2f}s",(10,30),cv2.FONT_HERSHEY_SIMPLEX,0.8,(0,255,0),2)
    cv2.putText(frame,"RECORDING",(10,65),cv2.FONT_HERSHEY_SIMPLEX,0.8,(0,0,255),2)
    frames.append(frame.copy())
    cv2.imshow("VitalGuardAI - Recording",frame)

    if now-last_report>=1:
        with lock: current=received_count
        print(f"Received in last second: {current-last_received:3d} | Total: {current}")
        last_received=current
        last_report=now

    if cv2.waitKey(1)&0xFF in (ord("q"),ord("Q"),27): break

recording_duration=time.perf_counter()-recording_start
recording_active=False
cap.release()
cv2.destroyAllWindows()
time.sleep(0.05)
running=False
thread.join(timeout=1)

with lock: raw_sensor=list(sensor_buffer)
received_count=len(raw_sensor)

# ============================================================
# SELECT 50 Hz USING ESP TIMESTAMPS
# ============================================================

sensor_rows=[]

if raw_sensor:
    next_ts=raw_sensor[0][0]
    for row in raw_sensor:
        if row[0]>=next_ts:
            sensor_rows.append(row)
            next_ts+=INTERVAL_MS

# ============================================================
# VIDEO STATISTICS
# ============================================================

frame_count=len(frames)
video_fps=frame_count/recording_duration if recording_duration>0 else 0
video_duration=(frame_count-1)/video_fps if video_fps>0 else 0

# ============================================================
# SENSOR STATISTICS
# ============================================================

sensor_count=len(sensor_rows)

if sensor_count>=2:
    first_timestamp=sensor_rows[0][0]
    last_timestamp=sensor_rows[-1][0]
    sensor_duration=(last_timestamp-first_timestamp)/1000
    sensor_rate=(sensor_count-1)/sensor_duration if sensor_duration>0 else 0
else:
    first_timestamp=last_timestamp=0
    sensor_duration=sensor_rate=0

# ============================================================
# TIMESTAMP GAP CHECK ON RAW DATA
# ============================================================

largest_gap_ms=0
gaps_over_5ms=0

for i in range(1,len(raw_sensor)):
    gap=raw_sensor[i][0]-raw_sensor[i-1][0]
    largest_gap_ms=max(largest_gap_ms,gap)
    if gap>5: gaps_over_5ms+=1

# ============================================================
# SAVE VIDEO
# ============================================================

print("\nCreating video...")

writer=cv2.VideoWriter(video_file,cv2.VideoWriter_fourcc(*"mp4v"),video_fps,(WIDTH,HEIGHT))

if writer.isOpened():
    for frame in frames: writer.write(frame)
    writer.release()

# ============================================================
# SAVE 50 Hz CSV
# ============================================================

print("Creating CSV...")

with open(csv_file,"w",newline="") as file:
    writer=csv.writer(file)
    writer.writerow(["esp_timestamp_ms","accel_x","accel_y","accel_z","gyro_x","gyro_y","gyro_z","temperature"])
    writer.writerows(sensor_rows)

# ============================================================
# RESULT
# ============================================================

print("\n=============================================")
print("           RECORDING FINISHED")
print("=============================================")
print(f"\nDataset folder     : {folder}")
print(f"Video file         : {video_file}")
print(f"CSV file           : {csv_file}")

print("\nVIDEO")
print("---------------------------------------------")
print(f"Frames recorded    : {frame_count}")
print(f"Recording time     : {recording_duration:.3f} sec")
print(f"Actual FPS         : {video_fps:.3f}")
print(f"Video duration     : {video_duration:.3f} sec")

print("\nSENSOR")
print("---------------------------------------------")
print(f"ESP packets received : {received_count}")
print(f"Raw sensor samples   : {len(raw_sensor)}")
print(f"CSV rows             : {sensor_count}")
print(f"Sensor duration      : {sensor_duration:.3f} sec")
print(f"CSV output rate      : {sensor_rate:.3f} Hz")

print("\nESP TIMESTAMP CHECK")
print("---------------------------------------------")
if raw_sensor:
    print(f"First ESP timestamp  : {raw_sensor[0][0]} ms")
    print(f"Last ESP timestamp   : {raw_sensor[-1][0]} ms")
    print(f"Largest timestamp gap: {largest_gap_ms} ms")
    print(f"Gaps greater than 5ms: {gaps_over_5ms}")
else:
    print("No sensor data received.")

print("\nNOTE")
print("---------------------------------------------")
print("ESP timestamp is the sensor time reference.")
print("All received packets were captured before 50 Hz selection.")
print("Final CSV is reduced to approximately 50 Hz.")
print("Video is reference footage only.")

print("\n=============================================")
print("Dataset saved successfully.")
print("=============================================")
