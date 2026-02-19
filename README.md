# Live Camera Layer (Krita 5.x)

Plugin Python para Krita que actualiza una capa de pintura con frames de:

- URL HTTP de snapshot JPEG/MJPEG
- Archivo local de imagen (`.jpg`, `.png`, etc.) que se sobrescribe en disco

## Archivos del plugin

- `live_camera_layer.desktop`
- `live_camera_layer/__init__.py`
- `live_camera_layer/live_camera_layer.py`

## Instalacion en Krita

1. Empaqueta estos archivos en un `.zip` con esta estructura en la raiz:

```
live_camera_layer.desktop
live_camera_layer/
  __init__.py
  live_camera_layer.py
```

2. En Krita: `Tools > Scripts > Import Python Plugin from File...`
3. Selecciona el `.zip`.
4. Reinicia Krita.
5. Activa el plugin en `Settings > Configure Krita > Python Plugin Manager` si es necesario.
6. Abre el docker desde `Settings > Dockers > Live Camera Layer`.

## Uso del docker

1. Elige `Source type`:
- `HTTP snapshot URL`
- `Local file path`

2. Configura input:
- URL, por ejemplo:
  - `http://192.168.1.50:8080/shot.jpg`
  - `http://192.168.1.50:8080/jpg/image.jpg`
- O archivo local con `Browse...`

3. Ajusta `FPS` (1..30, default 10).
4. Define `Create/Use layer name` (default `LiveCam`).
5. Ajusta `Rotate` (0, 90, 180, 270) si necesitas girar la imagen.
6. Activa `Flip horizontal` y/o `Flip vertical` si necesitas espejar.
7. Marca `Fit to canvas` si quieres que el frame cubra todo el canvas manteniendo aspecto.
8. Pulsa `Start` para iniciar; el boton cambia a `Stop`.
9. Si quieres cambiar transparencia, usa la opacidad de la capa `LiveCam` desde el panel de capas de Krita.

## Estado y robustez

- Muestra estado: `OK`, `Timeout`, `Disconnected`, `Stopped`.
- Networking asincrono con `QNetworkAccessManager` para no bloquear UI.
- Timeout corto (~1s) por request HTTP.
- `Stop` corta timer y requests en curso.
- Si no hay documento activo, el stream se detiene.

## Android: obtener URL de snapshot

Puedes usar apps de camara IP para Android que expongan endpoints HTTP tipo snapshot o MJPEG.

Ejemplos comunes:
- `/shot.jpg`
- `/jpg/image.jpg`
- endpoint MJPEG (segun la app)

En muchas apps el esquema es: `http://IP_DEL_TELEFONO:PUERTO/ruta`.

## Crear zip desde PowerShell

Desde la carpeta del proyecto:

```powershell
Compress-Archive -Path live_camera_layer.desktop, live_camera_layer -DestinationPath live_camera_layer.zip -Force
```

## Licencia

Este proyecto usa licencia MIT. Ver `LICENSE`.

## Subir a GitHub

Desde esta carpeta:

```powershell
git init -b main
git add .
git commit -m "Initial commit: Live Camera Layer plugin for Krita"
git remote add origin https://github.com/TU_USUARIO/TU_REPO.git
git push -u origin main
```

Nota: `live_camera_layer.zip` y `__pycache__` estan ignorados por `.gitignore`.
