import tkinter as tk
from tkinter import filedialog, messagebox
import cv2
import pandas as pd
from PIL import Image, ImageTk
import os

# Settings
W, H = 854, 480
WINDOW, STEP = 4.0, 2.0

LABELS = ["Falling", "Sitting", "Sleeping", "Standing", "Walking"]
KEYS = {"1": "Falling", "2": "Sitting", "3": "Sleeping", "4": "Standing", "5": "Walking"}
ENCODING = {"Falling": 1, "Sitting": 2, "Sleeping": 3, "Standing": 4, "Walking": 5}

INPUT_COLUMNS = [
    "pc_timestamp", "relative_time_sec", "esp_timestamp_ms",
    "accel_x", "accel_y", "accel_z",
    "gyro_x", "gyro_y", "gyro_z", "temperature"
]

OUTPUT_COLUMNS = [
    "esp_timestamp_ms", "accel_x", "accel_y", "accel_z",
    "gyro_x", "gyro_y", "gyro_z", "temperature", "label"
]


class VideoCSVLabeler:
    def __init__(self, root):
        self.root = root
        self.root.title("Video + Sensor CSV Labeler")
        self.root.geometry("1100x760")
        self.root.minsize(950, 700)

        self.cap = self.df = None
        self.video_path = self.csv_path = self.output_path = None
        self.video_fps, self.video_frames, self.video_duration = 30.0, 0, 0.0
        self.sensor_start = self.sensor_end = self.sensor_duration = 0.0
        self.window_start, self.window_end = 0.0, WINDOW
        self.segments = []
        self.playing, self.after_id = False, None

        self.build_ui()
        self.root.bind("<KeyPress>", self.key_pressed)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    # UI
    def build_ui(self):
        top = tk.Frame(self.root, padx=10, pady=8)
        top.pack(fill="x")

        for text, command, width in [
            ("Open Video", self.open_video, 15),
            ("Open CSV", self.open_csv, 15),
            ("Save Labeled CSV", self.save_csv, 18)
        ]:
            tk.Button(top, text=text, width=width, command=command).pack(side="left", padx=4)

        video = tk.Frame(self.root, width=W, height=H, bg="black")
        video.pack(pady=5)
        video.pack_propagate(False)

        self.video_label = tk.Label(video, bg="black", fg="white", text="Open video")
        self.video_label.pack(fill="both", expand=True)

        self.time_label = tk.Label(
            self.root, text="00:00.00 / 00:00.00",
            font=("Consolas", 14, "bold")
        )
        self.time_label.pack(pady=2)

        info = tk.Frame(self.root, padx=10)
        info.pack(fill="x")

        self.window_label = tk.Label(
            info, text="Window: -- → --",
            font=("Arial", 12, "bold")
        )
        self.window_label.pack(side="left")

        self.progress_label = tk.Label(
            info, text="Segment: --",
            font=("Arial", 11)
        )
        self.progress_label.pack(side="right")

        self.timeline = tk.Scale(
            self.root, from_=0, to=100, resolution=0.01,
            orient="horizontal", showvalue=False,
            command=self.timeline_changed
        )
        self.timeline.pack(fill="x", padx=15)

        controls = tk.Frame(self.root, pady=5)
        controls.pack()

        tk.Button(
            controls, text="◀ Previous", width=15,
            command=self.previous_window
        ).pack(side="left", padx=5)

        tk.Button(
            controls, text="Next ▶", width=15,
            command=self.next_window
        ).pack(side="left", padx=5)

        frame = tk.Frame(self.root, pady=5)
        frame.pack()

        tk.Label(
            frame, text="Label current 4-second window",
            font=("Arial", 12, "bold")
        ).pack()

        buttons = tk.Frame(frame)
        buttons.pack(pady=6)

        for label in LABELS:
            tk.Button(
                buttons, text=label, width=14, height=2,
                command=lambda x=label: self.label_window(x)
            ).pack(side="left", padx=4)

        tk.Button(
            frame, text="SKIP  [SPACE]",
            width=20, height=2,
            command=self.skip_window
        ).pack(pady=3)

        tk.Label(
            self.root,
            text="1 Falling | 2 Sitting | 3 Sleeping | 4 Standing | 5 Walking | SPACE Skip",
            font=("Arial", 10)
        ).pack(pady=3)

        self.status = tk.Label(
            self.root, text="Open video and CSV to begin.",
            anchor="w", padx=10
        )
        self.status.pack(fill="x")

    # Helpers
    @staticmethod
    def fmt(t):
        t = max(0, float(t))
        m, s = int(t // 60), t % 60
        return f"{m:02d}:{s:05.2f}"

    def set_status(self, text):
        self.status.config(text=text)

    # Video
    def open_video(self):
        path = filedialog.askopenfilename(
            title="Select Video",
            filetypes=[
                ("Video files", "*.mp4 *.avi *.mov *.mkv"),
                ("All files", "*.*")
            ]
        )
        if not path:
            return

        self.stop()
        if self.cap:
            self.cap.release()

        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            messagebox.showerror("Error", "Could not open video.")
            return

        self.video_path = path
        self.video_fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.video_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.video_duration = self.video_frames / self.video_fps

        self.timeline.config(to=max(0, self.video_duration - WINDOW))
        self.window_start = 0

        self.set_status(
            f"Video: {os.path.basename(path)} | "
            f"{self.video_fps:.2f} FPS | {self.video_duration:.2f}s"
        )
        self.update_window()
        self.start()

    # CSV
    def open_csv(self):
        path = filedialog.askopenfilename(
            title="Select Sensor CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if not path:
            return

        try:
            df = pd.read_csv(path)
        except Exception as e:
            messagebox.showerror("CSV Error", str(e))
            return

        missing = [c for c in INPUT_COLUMNS if c not in df.columns]
        if missing:
            messagebox.showerror(
                "Invalid CSV",
                "Missing columns:\n\n" + "\n".join(missing)
            )
            return

        df["relative_time_sec"] = pd.to_numeric(
            df["relative_time_sec"], errors="coerce"
        )
        df["esp_timestamp_ms"] = pd.to_numeric(
            df["esp_timestamp_ms"], errors="coerce"
        )

        df = df.dropna(
            subset=["relative_time_sec"]
        ).sort_values(
            "relative_time_sec"
        ).reset_index(drop=True)

        if len(df) < 2:
            messagebox.showerror(
                "Invalid CSV",
                "CSV contains too few sensor rows."
            )
            return

        self.df, self.csv_path = df, path
        self.sensor_start = float(df["relative_time_sec"].iloc[0])
        self.sensor_end = float(df["relative_time_sec"].iloc[-1])
        self.sensor_duration = self.sensor_end - self.sensor_start

        rate = (
            (len(df) - 1) / self.sensor_duration
            if self.sensor_duration > 0 else 0
        )

        self.set_status(
            f"CSV: {os.path.basename(path)} | "
            f"{len(df):,} rows | {self.sensor_duration:.2f}s | "
            f"{rate:.2f} Hz"
        )

        print("\n" + "=" * 50)
        print("DATASET INFORMATION")
        print("=" * 50)
        print(f"CSV rows          : {len(df):,}")
        print(f"Relative start    : {self.sensor_start:.3f}s")
        print(f"Relative end      : {self.sensor_end:.3f}s")
        print(f"Sensor duration   : {self.sensor_duration:.3f}s")
        print(f"Effective rate    : {rate:.2f} Hz")

        esp = df["esp_timestamp_ms"].dropna()
        if len(esp):
            print(f"ESP start         : {esp.iloc[0]:.0f} ms")
            print(f"ESP end           : {esp.iloc[-1]:.0f} ms")
            print(
                f"ESP duration      : "
                f"{(esp.iloc[-1] - esp.iloc[0]) / 1000:.3f}s"
            )

        if self.video_duration:
            diff = abs(self.video_duration - self.sensor_duration)
            print(f"Video duration    : {self.video_duration:.3f}s")
            print(f"Difference        : {diff:.3f}s")

            if diff > 2:
                messagebox.showwarning(
                    "Duration Difference",
                    f"Video: {self.video_duration:.2f}s\n"
                    f"CSV: {self.sensor_duration:.2f}s\n\n"
                    f"Difference: {diff:.2f}s"
                )

        print("=" * 50)

    # Frame
    def get_frame(self, t):
        if not self.cap:
            return None

        frame_no = int(
            max(0, min(t, self.video_duration)) * self.video_fps
        )
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
        ok, frame = self.cap.read()
        return frame if ok else None

    # Display
    def display(self, frame, t):
        if frame is None:
            return

        frame = cv2.resize(
            frame, (W, H), interpolation=cv2.INTER_AREA
        )

        text = f"{self.fmt(t)} / {self.fmt(self.video_duration)}"

        cv2.rectangle(
            frame, (12, 12), (250, 62),
            (0, 0, 0), -1
        )

        cv2.putText(
            frame, text, (22, 47),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75, (255, 255, 255), 2,
            cv2.LINE_AA
        )

        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        photo = ImageTk.PhotoImage(Image.fromarray(frame))

        self.video_label.config(image=photo, text="")
        self.video_label.image = photo
        self.time_label.config(text=text)

    # Window
    def update_window(self):
        if not self.cap:
            return

        self.window_end = min(
            self.window_start + WINDOW,
            self.video_duration
        )

        self.timeline.set(self.window_start)

        self.window_label.config(
            text=(
                f"Window: {self.fmt(self.window_start)} → "
                f"{self.fmt(self.window_end)}"
            )
        )

        total = max(
            1,
            int((self.video_duration - WINDOW) / STEP) + 1
        )
        current = int(self.window_start / STEP) + 1

        self.progress_label.config(
            text=f"Segment: {current} / {total}"
        )

        self.display(
            self.get_frame(self.window_start),
            self.window_start
        )

    # Playback
    def start(self):
        if not self.cap:
            return

        self.stop()
        self.playing = True

        self.cap.set(
            cv2.CAP_PROP_POS_FRAMES,
            int(self.window_start * self.video_fps)
        )
        self.play()

    def stop(self):
        self.playing = False

        if self.after_id:
            try:
                self.root.after_cancel(self.after_id)
            except:
                pass
            self.after_id = None

    def play(self):
        if not self.playing or not self.cap:
            return

        frame_no = self.cap.get(cv2.CAP_PROP_POS_FRAMES)
        t = frame_no / self.video_fps

        if t >= self.window_end:
            self.cap.set(
                cv2.CAP_PROP_POS_FRAMES,
                int(self.window_start * self.video_fps)
            )
            t = self.window_start

        ok, frame = self.cap.read()
        if ok:
            self.display(frame, t)

        self.after_id = self.root.after(
            max(1, int(1000 / self.video_fps)),
            self.play
        )

    # Label
    def label_window(self, label):
        if self.df is None:
            messagebox.showwarning("CSV Required", "Open the CSV first.")
            return

        if not self.cap:
            messagebox.showwarning("Video Required", "Open the video first.")
            return

        self.stop()

        # Replace only the exact same window
        self.segments = [
            x for x in self.segments
            if not (
                abs(x[0] - self.window_start) < 0.001 and
                abs(x[1] - self.window_end) < 0.001
            )
        ]

        self.segments.append(
            (self.window_start, self.window_end, label)
        )

        self.set_status(
            f"{self.fmt(self.window_start)} → "
            f"{self.fmt(self.window_end)} = "
            f"{label} ({ENCODING[label]})"
        )

        self.next_window()

    # Skip
    def skip_window(self):
        if not self.cap:
            return

        self.stop()
        self.set_status(
            f"Skipped {self.fmt(self.window_start)} → "
            f"{self.fmt(self.window_end)}"
        )
        self.next_window()

    # Navigation
    def next_window(self):
        if not self.cap:
            return

        new_start = self.window_start + STEP

        if new_start + 0.001 >= self.video_duration:
            self.window_start = max(
                0, self.video_duration - WINDOW
            )
            self.update_window()
            self.stop()
            self.finish()
            return

        self.window_start = new_start
        self.update_window()
        self.start()

    def previous_window(self):
        if not self.cap:
            return

        self.stop()
        self.window_start = max(
            0, self.window_start - STEP
        )
        self.update_window()
        self.start()

    def timeline_changed(self, value):
        if not self.cap:
            return

        try:
            self.window_start = float(value)
        except:
            return

        self.stop()
        self.update_window()
        self.start()

    # Keyboard
    def key_pressed(self, event):
        key = event.keysym.lower()

        if key in KEYS:
            self.label_window(KEYS[key])
        elif key == "space":
            self.skip_window()
        elif key == "right":
            self.next_window()
        elif key == "left":
            self.previous_window()

    # Sensor synchronization
    def sensor_mask(self, start, end):
        if self.df is None:
            return None

        start += self.sensor_start
        end += self.sensor_start
        t = self.df["relative_time_sec"]

        return (t >= start) & (t < end)

    # Create labeled data
    def labeled_data(self):
        if self.df is None:
            return None

        parts = []

        for start, end, label in sorted(
            self.segments, key=lambda x: x[0]
        ):
            part = self.df.loc[
                self.sensor_mask(start, end)
            ].copy()

            if len(part):
                part["label"] = label
                parts.append(part)

        return (
            pd.concat(parts, ignore_index=True)
            if parts else None
        )

    # Finish
    def finish(self):
        if not self.segments:
            if messagebox.askyesno(
                "No Labels",
                "No windows were labeled.\n\nExit?"
            ):
                self.close()
            return

        if messagebox.askyesno(
            "Labeling Complete",
            "Generate the labeled CSV now?"
        ):
            self.save_csv()

    # Save
    def save_csv(self):
        if self.df is None:
            messagebox.showwarning("No CSV", "Open a CSV first.")
            return

        if not self.segments:
            messagebox.showwarning(
                "No Labels",
                "No labeled windows found."
            )
            return

        result = self.labeled_data()

        if result is None or result.empty:
            messagebox.showwarning(
                "No Data",
                "No sensor data found in labeled windows."
            )
            return

        rows_before = len(result)

        # Encode labels
        result["label"] = result["label"].map(ENCODING)

        result = result[OUTPUT_COLUMNS]

        base = (
            os.path.splitext(
                os.path.basename(self.csv_path)
            )[0]
            if self.csv_path else "data"
        )

        output = filedialog.asksaveasfilename(
            title="Save Labeled CSV",
            defaultextension=".csv",
            initialfile=base + "_labeled.csv",
            filetypes=[("CSV files", "*.csv")]
        )

        if not output:
            return

        try:
            result.to_csv(output, index=False)
        except Exception as e:
            messagebox.showerror("Save Error", str(e))
            return

        self.output_path = output
        counts = result["label"].value_counts()

        stats = "\n".join(
            f"{label} ({ENCODING[label]}): "
            f"{counts.get(ENCODING[label], 0):,}"
            for label in LABELS
        )

        messagebox.showinfo(
            "Saved Successfully",
            f"Saved:\n{output}\n\n"
            f"Rows saved: {len(result):,}\n\n"
            f"Rows by label:\n{stats}"
        )

        self.set_status(
            f"Saved: {os.path.basename(output)} | "
            f"{len(result):,} rows"
        )

    # Close
    def close(self):
        self.stop()

        if self.cap:
            self.cap.release()
            self.cap = None

        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = VideoCSVLabeler(root)
    root.mainloop()