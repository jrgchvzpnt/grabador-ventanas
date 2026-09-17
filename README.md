# Grabador de ventanas

Aplicación de escritorio en Python (Tkinter) para **Windows** que permite
seleccionar una ventana abierta (por ejemplo, una ventana o pestaña del
navegador), grabarla en video, capturar el audio del sistema, pausar y
reanudar la grabación, ver una vista previa en vivo mientras grabas, y
reproducir el resultado al finalizar.

## Características

- **Selección de ventana**: lista todas las ventanas abiertas del sistema y
  permite elegir cuál grabar.
- **Abrir video por URL (opcional)**: un campo para pegar un link (por
  ejemplo, un video de Google Drive) que se abre con tu navegador y tu
  sesión normal. La app **no maneja usuarios ni contraseñas**: solo llama
  a `webbrowser.open()`, así que inicias sesión tú mismo si hace falta.
- **Grabación de video**: captura la región de pantalla donde está la
  ventana seleccionada usando [`mss`](https://pypi.org/project/mss/) y
  [`OpenCV`](https://pypi.org/project/opencv-python/).
- **Grabación de audio del sistema**: captura el audio de salida del
  dispositivo predeterminado (loopback WASAPI) usando
  [`PyAudioWPatch`](https://pypi.org/project/PyAudioWPatch/), de forma
  simultánea al video.
- **Control de volumen de la PC**: una barra deslizante controla el
  volumen general de salida de Windows (usando
  [`pycaw`](https://pypi.org/project/pycaw/)) sin salir de la app ni
  interrumpir el video que estás viendo/grabando.
- **Pausa / reanudar**: pausa la grabación (video y audio) sin detenerla;
  el tiempo en pausa no queda incluido en el archivo final.
- **Guardar como...**: permite elegir la carpeta y el nombre del archivo
  antes de grabar. La extensión queda siempre forzada a `.mp4`, sin
  importar lo que se escriba en el diálogo.
- **Vista previa en vivo**: muestra en la propia ventana de la app el
  contenido que se está grabando en tiempo real, con un indicador
  "PAUSADO" superpuesto cuando corresponde.
- **Compresión automática**: al detener la grabación, el video (capturado
  internamente sin comprimir) se recodifica a **H.264** (`libx264`,
  `crf 23`, `preset slow`) usando `ffmpeg`, reduciendo bastante el tamaño
  del archivo sin pérdida notable de calidad. El audio se mezcla en el
  mismo paso (AAC).
- **Reproducción**: botón para abrir la grabación resultante con el
  reproductor de video predeterminado de Windows.

## Requisitos

- Windows (usa APIs específicas de Windows: `pywin32`, `pygetwindow`,
  WASAPI loopback).
- Python 3.9 o superior.
- No necesitas instalar `ffmpeg` por separado: se incluye automáticamente
  mediante el paquete `imageio-ffmpeg`.

## Instalación

```bash
pip install -r requirements.txt
```

Dependencias incluidas en `requirements.txt`:

| Paquete           | Uso                                                   |
|-------------------|--------------------------------------------------------|
| `pygetwindow`     | Listar y manipular ventanas abiertas                   |
| `pywin32`         | Obtener el rectángulo exacto de la ventana (WinAPI)    |
| `opencv-python`   | Escritura de frames a video                            |
| `mss`             | Captura rápida de pantalla/región                      |
| `numpy`           | Manipulación de los frames capturados                  |
| `PyAudioWPatch`   | Captura de audio del sistema vía loopback WASAPI       |
| `imageio-ffmpeg`  | Binario de `ffmpeg` listo para usar (sin instalación aparte) |
| `Pillow`          | Generar la imagen de la vista previa en la interfaz    |
| `pycaw`           | Leer y ajustar el volumen general de Windows           |
| `comtypes`        | Dependencia de `pycaw` para llamar a las APIs COM de Windows |

## Uso

```bash
python app.py
```

1. Abre la ventana/pestaña del navegador (o cualquier otra) que quieras
   grabar. Si es un video con link (por ejemplo de Google Drive), puedes
   pegarlo en el campo **"Abrir video (URL, opcional)"** y pulsar
   **Abrir**: se abrirá con tu navegador y tu sesión ya iniciada. Si Drive
   te pide iniciar sesión, hazlo tú mismo en esa pestaña (la app nunca ve
   ni guarda tu usuario o contraseña).
2. En la app, pulsa **Actualizar** si la ventana no aparece en la lista, y
   selecciónala en el desplegable.
3. (Opcional) Marca o desmarca **"Grabar también el audio del sistema"**.
4. (Opcional) Ajusta la barra **"Volumen de la PC"** para subir o bajar
   el volumen general de Windows sin interrumpir el video ni salir de la
   app.
5. (Opcional) Pulsa **Guardar como...** para elegir en qué carpeta y con
   qué nombre se guardará el video. El diálogo siempre fuerza la
   extensión `.mp4`, aunque escribas otra (por ejemplo, `video.avi` se
   guardará igualmente como `video.mp4`). Si no eliges nada, el video se
   guarda automáticamente en `recordings/` con un nombre basado en la
   fecha y hora.
6. Pulsa **Iniciar grabación**. La ventana seleccionada se traerá al frente
   y comenzará la captura; la vista previa mostrará lo que se está
   grabando.
7. Usa **Pausar / Reanudar** para pausar temporalmente sin cortar la
   grabación.
8. Pulsa **Detener** para finalizar. La app recomprime automáticamente el
   video (esto puede tardar unos segundos según la duración) y muestra la
   ruta del archivo final junto con su tamaño en MB.
9. Pulsa **Reproducir** para abrir el video con el reproductor
   predeterminado de Windows.

Si no usaste "Guardar como...", los videos se guardan en la carpeta
`recordings/` dentro del proyecto, con nombre
`recording_AAAAMMDD_HHMMSS.mp4`. Esa carpeta está excluida del
control de versiones (ver `.gitignore`).

## Generar un ejecutable (.exe)

Si prefieres no instalar Python, puedes empaquetar la app en un único
`.exe` para Windows con [PyInstaller](https://pyinstaller.org/):

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name GrabadorVentanas app.py
```

El ejecutable resultante queda en `dist/GrabadorVentanas.exe` y no requiere
tener Python ni las dependencias instaladas (todo, incluido `ffmpeg`,
queda embebido dentro del `.exe`). Las carpetas `build/`, `dist/` y el
archivo `.spec` generados por PyInstaller no se versionan (ver
`.gitignore`).

## Limitaciones importantes

- **Captura por región de pantalla, no por ventana real**: si otra
  ventana se superpone sobre la que estás grabando, se capturará lo que
  esté visible encima (limitación de las APIs de captura usadas). Evita
  tapar la ventana mientras grabas.
- **El audio es del sistema, no de la ventana específica**: Windows no
  ofrece una forma sencilla de capturar el audio de una sola
  ventana/pestaña sin usar APIs de bajo nivel más complejas (Process
  Loopback Capture). Lo que se graba es *todo* el audio que sale por el
  dispositivo de salida predeterminado. Si necesitas que el audio
  corresponda solo al navegador, evita reproducir otros sonidos mientras
  grabas.
- Solo funciona en **Windows**, por las librerías utilizadas
  (`pywin32`, `pygetwindow`, WASAPI).
- Si `PyAudioWPatch` no se pudo instalar o inicializar, la app sigue
  funcionando pero solo grabará video (el checkbox de audio aparece
  deshabilitado y se muestra un aviso en la interfaz).
- Si `pycaw` no se pudo instalar o inicializar, la barra de volumen
  aparece deshabilitada y se muestra un aviso; el resto de la app sigue
  funcionando con normalidad.
- **La app no automatiza inicios de sesión**: el campo "Abrir video (URL)"
  solo abre el link en tu navegador (`webbrowser.open`); no guarda,
  escribe ni gestiona usuarios o contraseñas de ningún servicio (Google
  Drive, Teams, etc.). Cualquier inicio de sesión lo haces tú manualmente
  en la pestaña que se abre.

## Estructura del proyecto

```
appvideo/
├── app.py              # Aplicación principal (interfaz + lógica de grabación)
├── requirements.txt    # Dependencias de Python
├── .gitignore
├── README.md
└── recordings/         # Videos generados (no versionado)
```

## Cómo funciona internamente (resumen técnico)

1. Al iniciar la grabación, se obtiene el rectángulo de la ventana
   (`win32gui.GetWindowRect`) y se lanza un hilo que captura esa región de
   pantalla cuadro a cuadro con `mss`, escribiéndolos sin comprimir a un
   archivo de video temporal (`.tmp_video_*.mp4`, códec `mp4v`).
2. Si el audio está activado, un segundo hilo abre un stream WASAPI en
   modo *loopback* con `PyAudioWPatch` y guarda el audio capturado en un
   `.wav` temporal (`.tmp_audio_*.wav`).
3. Cada cuadro capturado se comparte con la interfaz mediante una
   variable protegida por un `Lock`, y un bucle periódico de Tkinter
   (`root.after`) la usa para actualizar la vista previa sin bloquear la
   grabación.
4. Al pausar, ambos hilos siguen vivos pero dejan de escribir datos
   (video) o de acumularlos (audio), por lo que el contenido en pausa no
   queda en el resultado final.
5. Al detener, se espera a que ambos hilos terminen y se invoca `ffmpeg`
   (vía `imageio-ffmpeg`) para recodificar el video temporal a H.264 y
   mezclar el audio, generando el archivo final en `recordings/`. Los
   archivos temporales se eliminan al terminar.
