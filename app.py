"""
Grabador de ventanas (por ejemplo, una ventana del navegador), con audio,
pausa y vista previa en vivo.

Permite elegir una ventana abierta de la lista, grabarla en video (.mp4)
junto con el audio del sistema, pausar/reanudar la grabación, ver una
vista previa mientras se graba, y reproducir el resultado al finalizar.

Nota sobre el audio: Windows no permite capturar el audio de UNA sola
ventana/pestaña de forma sencilla. Lo que se graba es el audio de salida
del dispositivo de sonido predeterminado (loopback), es decir, todo lo
que se está reproduciendo en el equipo mientras grabas. Si solo quieres
el audio del navegador, evita reproducir otros sonidos mientras grabas.

Requisitos: pip install -r requirements.txt
Uso: python app.py
"""

import datetime
import os
import subprocess
import threading
import time
import tkinter as tk
import wave
from tkinter import messagebox, ttk

import cv2
import imageio_ffmpeg
import mss
import numpy as np
import pygetwindow as gw
import win32gui
from PIL import Image, ImageDraw, ImageTk

try:
    import pyaudiowpatch as pyaudio

    HAS_AUDIO = True
except ImportError:
    HAS_AUDIO = False

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recordings")
FPS = 15
AUDIO_CHUNK = 1024
PREVIEW_SIZE = (480, 270)  # 16:9
PREVIEW_INTERVAL_MS = 200


def get_loopback_device(p):
    """Devuelve el dispositivo de loopback WASAPI del altavoz predeterminado."""
    try:
        wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    except OSError:
        return None

    try:
        default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
    except OSError:
        return None

    if default_speakers.get("isLoopbackDevice", False):
        return default_speakers

    for loopback in p.get_loopback_device_info_generator():
        if default_speakers["name"] in loopback["name"]:
            return loopback

    return None


class RecorderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Grabador de ventana")
        self.root.geometry("520x560")
        self.root.resizable(False, False)

        self.windows = []
        self.recording = False
        self.paused = False
        self.record_thread = None
        self.audio_thread = None
        self.output_path = None
        self._video_tmp = None
        self._audio_tmp = None
        self._recording_audio = False

        self._frame_lock = threading.Lock()
        self._latest_frame = None  # último frame BGR capturado (para el preview)
        self._preview_photo = None  # referencia viva para que Tkinter no la recolecte

        self._build_ui()
        self.refresh_windows()
        self._show_placeholder_preview("Sin grabación en curso")
        self.root.after(PREVIEW_INTERVAL_MS, self._update_preview)

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill="x", **pad)

        ttk.Label(top_frame, text="Ventana a grabar:").pack(anchor="w")

        row = ttk.Frame(top_frame)
        row.pack(fill="x", pady=(4, 0))

        self.combo = ttk.Combobox(row, state="readonly", width=48)
        self.combo.pack(side="left", fill="x", expand=True)

        ttk.Button(row, text="Actualizar", command=self.refresh_windows).pack(
            side="left", padx=(6, 0)
        )

        self.audio_var = tk.BooleanVar(value=HAS_AUDIO)
        audio_check = ttk.Checkbutton(
            self.root,
            text="Grabar también el audio del sistema",
            variable=self.audio_var,
        )
        audio_check.pack(anchor="w", padx=10)
        if not HAS_AUDIO:
            audio_check.config(state="disabled")
            self.audio_var.set(False)

        # --- Vista previa ---
        preview_frame = ttk.Frame(self.root)
        preview_frame.pack(padx=10, pady=(8, 4))

        self.preview_label = tk.Label(
            preview_frame,
            width=PREVIEW_SIZE[0],
            height=PREVIEW_SIZE[1],
            bg="black",
        )
        self.preview_label.pack()

        # --- Botones ---
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", **pad)

        self.start_btn = ttk.Button(
            btn_frame, text="Iniciar grabación", command=self.start_recording
        )
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0, 4))

        self.pause_btn = ttk.Button(
            btn_frame, text="Pausar", command=self.toggle_pause, state="disabled"
        )
        self.pause_btn.pack(side="left", expand=True, fill="x", padx=4)

        self.stop_btn = ttk.Button(
            btn_frame, text="Detener", command=self.stop_recording, state="disabled"
        )
        self.stop_btn.pack(side="left", expand=True, fill="x", padx=4)

        self.play_btn = ttk.Button(
            btn_frame, text="Reproducir", command=self.play_recording, state="disabled"
        )
        self.play_btn.pack(side="left", expand=True, fill="x", padx=(4, 0))

        # --- Estado (texto grande para que se note bien) ---
        self.status_var = tk.StringVar(value="Listo.")
        tk.Label(
            self.root,
            textvariable=self.status_var,
            font=("Segoe UI", 13, "bold"),
            fg="#1a4d7a",
            wraplength=480,
            justify="left",
        ).pack(anchor="w", padx=10, pady=(4, 6))

        if not HAS_AUDIO:
            ttk.Label(
                self.root,
                text="(No se encontró PyAudioWPatch: instala las dependencias para grabar audio)",
                foreground="#a33",
                wraplength=480,
            ).pack(anchor="w", padx=10)

    # ------------------------------------------------------------------
    # Vista previa
    # ------------------------------------------------------------------
    def _show_placeholder_preview(self, text):
        img = Image.new("RGB", PREVIEW_SIZE, color=(24, 24, 24))
        draw = ImageDraw.Draw(img)
        bbox = draw.textbbox((0, 0), text)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        draw.text(
            ((PREVIEW_SIZE[0] - text_w) / 2, (PREVIEW_SIZE[1] - text_h) / 2),
            text,
            fill=(160, 160, 160),
        )
        self._preview_photo = ImageTk.PhotoImage(img)
        self.preview_label.config(image=self._preview_photo)

    def _update_preview(self):
        if self.recording:
            with self._frame_lock:
                frame = self._latest_frame

            if frame is not None:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(rgb).resize(PREVIEW_SIZE, Image.LANCZOS)

                if self.paused:
                    draw = ImageDraw.Draw(img)
                    draw.rectangle([0, 0, PREVIEW_SIZE[0], 28], fill=(0, 0, 0))
                    draw.text((8, 6), "PAUSADO", fill=(255, 210, 0))

                self._preview_photo = ImageTk.PhotoImage(img)
                self.preview_label.config(image=self._preview_photo)

        self.root.after(PREVIEW_INTERVAL_MS, self._update_preview)

    # ------------------------------------------------------------------
    # Ventanas
    # ------------------------------------------------------------------
    def refresh_windows(self):
        all_windows = gw.getAllWindows()
        self.windows = [
            w for w in all_windows if w.title.strip() and w.width > 0 and w.height > 0
        ]
        titles = [w.title for w in self.windows]
        self.combo["values"] = titles
        if titles:
            self.combo.current(0)
        else:
            self.combo.set("")
        self.status_var.set(f"{len(titles)} ventana(s) encontradas.")

    # ------------------------------------------------------------------
    # Grabación
    # ------------------------------------------------------------------
    def start_recording(self):
        idx = self.combo.current()
        if idx < 0 or idx >= len(self.windows):
            messagebox.showwarning("Aviso", "Selecciona una ventana primero.")
            return

        win = self.windows[idx]

        try:
            if win.isMinimized:
                win.restore()
            win.activate()
        except Exception:
            pass

        time.sleep(0.3)

        try:
            left, top, right, bottom = win32gui.GetWindowRect(win._hWnd)
        except Exception as exc:
            messagebox.showerror("Error", f"No se pudo leer la ventana: {exc}")
            return

        width = right - left
        height = bottom - top
        if width <= 0 or height <= 0:
            messagebox.showerror("Error", "La ventana seleccionada no es válida.")
            return

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_path = os.path.join(OUTPUT_DIR, f"recording_{stamp}.mp4")

        want_audio = self.audio_var.get() and HAS_AUDIO
        self._recording_audio = False

        self._video_tmp = os.path.join(OUTPUT_DIR, f".tmp_video_{stamp}.mp4")
        self._audio_tmp = (
            os.path.join(OUTPUT_DIR, f".tmp_audio_{stamp}.wav") if want_audio else None
        )

        self.paused = False
        self.recording = True

        self.record_thread = threading.Thread(
            target=self._record_video_loop,
            args=(left, top, width, height, self._video_tmp),
            daemon=True,
        )
        self.record_thread.start()

        if want_audio:
            self.audio_thread = threading.Thread(
                target=self._record_audio_loop,
                args=(self._audio_tmp,),
                daemon=True,
            )
            self.audio_thread.start()
        else:
            self.audio_thread = None
            if self.audio_var.get() and not HAS_AUDIO:
                self.status_var.set(
                    "Aviso: no se pudo activar audio (falta PyAudioWPatch). Grabando solo video..."
                )

        self.start_btn.config(state="disabled")
        self.pause_btn.config(state="normal", text="Pausar")
        self.stop_btn.config(state="normal")
        self.play_btn.config(state="disabled")
        self.combo.config(state="disabled")
        if not (self.audio_var.get() and not HAS_AUDIO):
            self.status_var.set(
                f"Grabando '{win.title}'... no la cubras con otra ventana."
            )

    def toggle_pause(self):
        if not self.recording:
            return
        self.paused = not self.paused
        if self.paused:
            self.pause_btn.config(text="Reanudar")
            self.status_var.set("Grabación en pausa.")
        else:
            self.pause_btn.config(text="Pausar")
            self.status_var.set("Grabando...")

    def _record_video_loop(self, left, top, width, height, filename):
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(filename, fourcc, FPS, (width, height))
        monitor = {"left": left, "top": top, "width": width, "height": height}
        frame_interval = 1.0 / FPS

        try:
            with mss.mss() as sct:
                next_time = time.time()
                while self.recording:
                    if self.paused:
                        time.sleep(0.1)
                        next_time = time.time()
                        continue

                    img = np.array(sct.grab(monitor))
                    frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                    writer.write(frame)

                    with self._frame_lock:
                        self._latest_frame = frame

                    next_time += frame_interval
                    sleep_time = next_time - time.time()
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    else:
                        next_time = time.time()
        finally:
            writer.release()

    def _record_audio_loop(self, audio_path):
        p = pyaudio.PyAudio()
        stream = None
        try:
            device = get_loopback_device(p)
            if device is None:
                return

            channels = max(1, int(device["maxInputChannels"]))
            rate = int(device["defaultSampleRate"])

            stream = p.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=device["index"],
                frames_per_buffer=AUDIO_CHUNK,
            )

            self._recording_audio = True
            frames = []
            while self.recording:
                try:
                    data = stream.read(AUDIO_CHUNK, exception_on_overflow=False)
                except Exception:
                    break
                # Mientras está en pausa seguimos leyendo el stream (para que no
                # se desborde el buffer) pero descartamos el audio capturado.
                if not self.paused:
                    frames.append(data)

            with wave.open(audio_path, "wb") as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
                wf.setframerate(rate)
                wf.writeframes(b"".join(frames))
        finally:
            if stream is not None:
                stream.stop_stream()
                stream.close()
            p.terminate()

    def stop_recording(self):
        if not self.recording:
            return
        self.recording = False
        self.paused = False

        if self.record_thread:
            self.record_thread.join()
        if self.audio_thread:
            self.status_var.set("Finalizando audio...")
            self.root.update_idletasks()
            self.audio_thread.join()

        self.start_btn.config(state="normal")
        self.pause_btn.config(state="disabled", text="Pausar")
        self.stop_btn.config(state="disabled")
        self.combo.config(state="readonly")
        self._show_placeholder_preview("Sin grabación en curso")

        has_audio_file = (
            self._audio_tmp
            and os.path.exists(self._audio_tmp)
            and os.path.getsize(self._audio_tmp) > 44
            and self._recording_audio
        )
        audio_path = self._audio_tmp if has_audio_file else None

        self.status_var.set("Comprimiendo video...")
        self.root.update_idletasks()

        if self._encode_output(self._video_tmp, audio_path, self.output_path):
            self._cleanup_temp_files()
        else:
            # Si falla la compresión, nos quedamos con el video sin comprimir
            # para no perder la grabación.
            self.output_path = self._video_tmp
            self.status_var.set(
                "No se pudo comprimir el video; se guardó la versión sin comprimir."
            )
            self.play_btn.config(state="normal")
            return

        if self.output_path and os.path.exists(self.output_path):
            size_mb = os.path.getsize(self.output_path) / (1024 * 1024)
            self.play_btn.config(state="normal")
            self.status_var.set(
                f"Grabación guardada en: {self.output_path} ({size_mb:.1f} MB)"
            )
        else:
            self.status_var.set("La grabación no se guardó correctamente.")

    def _encode_output(self, video_path, audio_path, out_path):
        """Recomprime el video capturado (mp4v sin comprimir) a H.264,
        opcionalmente muxeando el audio, para reducir el tamaño del archivo
        conservando buena calidad visual."""
        try:
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            cmd = [ffmpeg_exe, "-y", "-i", video_path]
            if audio_path:
                cmd += ["-i", audio_path]

            cmd += [
                "-c:v", "libx264",
                "-preset", "slow",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
            ]

            if audio_path:
                cmd += ["-c:a", "aac", "-b:a", "128k", "-shortest"]

            cmd += [out_path]

            result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            return result.returncode == 0 and os.path.exists(out_path)
        except Exception:
            return False

    def _cleanup_temp_files(self):
        for path in (self._video_tmp, self._audio_tmp):
            if path and path != self.output_path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    def play_recording(self):
        if self.output_path and os.path.exists(self.output_path):
            os.startfile(self.output_path)
        else:
            messagebox.showwarning("Aviso", "No hay ninguna grabación para reproducir.")


def main():
    root = tk.Tk()
    RecorderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
