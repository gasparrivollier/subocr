# Subtitle extractor — guía rápida / quick guide

## Español

**Qué hace:** lee una grabación de pantalla de un video con subtítulos (pantalla negra con subtítulos blancos)
y crea un archivo `.srt` con el texto y los tiempos exactos de cada subtítulo.

1. Descomprime la carpeta `subocr` donde quieras (no hace falta instalar nada).
2. Haz doble clic en `subocr.exe`.
3. Si Windows muestra **"Windows protegió su PC"**: pulsa **Más información → Ejecutar de todas formas**
   (la aplicación no está firmada; es normal).
4. Arrastra tu video a la ventana, o pulsa **Choose video…**.
5. Espera a que termine la barra de progreso. Puedes pulsar **Cancel** en cualquier momento.
6. Al terminar, pulsa **Show in folder**: se abre la carpeta `<nombre del video>_subtitles` con:
   * `subs.srt` — los subtítulos, para abrir en tu editor de subtítulos.
   * `events.csv` — una tabla con tiempos, fotogramas, texto y confianza (se abre en Excel).
   * `frame_index.csv` — el tiempo exacto de cada fotograma.

**Notas**
* Si vuelves a procesar el mismo video, se crea otra carpeta (`… (2)`); nunca se sobrescribe lo anterior.
* Si algo falla, la ventana lo explica y guarda un archivo `subocr.log`: pulsa **Show log** y envíamelo.
* Pensado para pantalla negra con subtítulos blancos, en español. El programa **no edita** los subtítulos:
  corrígelos en tu editor.

## English

**What it does:** reads a screen recording of subtitled video (black screen, white subtitles) and writes an
`.srt` file with each subtitle's text and exact timing.

1. Unzip the `subocr` folder anywhere (nothing to install).
2. Double-click `subocr.exe`.
3. If Windows shows **"Windows protected your PC"**, click **More info → Run anyway** (the app is unsigned;
   this is expected).
4. Drag your video onto the window, or click **Choose video…**.
5. Wait for the progress bar. **Cancel** works at any time.
6. When done, click **Show in folder**: the `<video name>_subtitles` folder opens with `subs.srt`,
   `events.csv` (opens in Excel) and `frame_index.csv`.

**Notes:** re-running the same video creates a new folder (`… (2)`), never overwriting earlier results.
On an error the window explains it and saves `subocr.log` (**Show log**). Built for black-screen footage with
white Spanish subtitles; the app does not edit subtitles.
