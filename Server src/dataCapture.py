import socket
import threading
import time
import csv
from datetime import datetime

# ==============================
# CONFIG
# ==============================

UDP_PORT = 5000
SAMPLE_INTERVAL = 0.02       # 50 Hz = 20 ms
OUTPUT_FILE = "sensor_data_50hz.csv"

latest_data = None
running = True


# ==============================
# UDP RECEIVER
# ==============================

def receive_data():

    global latest_data

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", UDP_PORT))

    print(f"Listening on UDP port {UDP_PORT}...")

    while running:

        data, address = sock.recvfrom(1024)

        try:
            values = data.decode().strip().split(",")

            if len(values) != 8:
                continue

            # Convert received data
            latest_data = [
                int(values[0]),      # ESP timestamp
                float(values[1]),    # Accel X
                float(values[2]),    # Accel Y
                float(values[3]),    # Accel Z
                float(values[4]),    # Gyro X
                float(values[5]),    # Gyro Y
                float(values[6]),    # Gyro Z
                float(values[7])     # Temperature
            ]

        except ValueError:
            continue


# ==============================
# START UDP THREAD
# ==============================

thread = threading.Thread(target=receive_data, daemon=True)
thread.start()


# ==============================
# WAIT FOR FIRST DATA
# ==============================

print("Waiting for ESP8266 data...")

while latest_data is None:
    time.sleep(0.001)

print("Data received.")
print("Recording at 50 Hz...\n")


# ==============================
# CSV
# ==============================

with open(OUTPUT_FILE, "w", newline="") as file:

    writer = csv.writer(file)

    writer.writerow([
        "pc_timestamp",
        "esp_timestamp_ms",
        "accel_x",
        "accel_y",
        "accel_z",
        "gyro_x",
        "gyro_y",
        "gyro_z",
        "temperature"
    ])

    next_time = time.perf_counter()

    try:

        while True:

            # --------------------------
            # Wait for next 20 ms
            # --------------------------

            next_time += SAMPLE_INTERVAL

            sleep_time = next_time - time.perf_counter()

            if sleep_time > 0:
                time.sleep(sleep_time)

            # --------------------------
            # Get latest sensor data
            # --------------------------

            data = latest_data

            # --------------------------
            # PC timestamp
            # --------------------------

            pc_timestamp = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S.%f"
            )

            # --------------------------
            # Save to CSV
            # --------------------------

            writer.writerow([
                pc_timestamp,
                data[0],
                data[1],
                data[2],
                data[3],
                data[4],
                data[5],
                data[6],
                data[7]
            ])

            file.flush()

    except KeyboardInterrupt:

        running = False

        print("\nRecording stopped.")
        print(f"Saved: {OUTPUT_FILE}")