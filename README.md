# Moorttys Voice PWA — versión web inicial

Aplicación web responsive e instalable (PWA) para Android/Chrome, con backend Python que conserva el enfoque de conexión a TikTok LIVE y YouTube LIVE del proyecto Windows. Incluye interfaz móvil, WebSocket para eventos, bienvenida configurable, sonidos por tipo de entrada, chat, lectura de mensajes, filtros básicos y ajustes guardados en `settings.json`.

## Importante antes de publicar

- Esta es una **base funcional inicial**, no una conversión 1:1 de toda la interfaz de Windows. Hay que probar conexiones en directos reales.
- TikTok LIVE depende de la biblioteca comunitaria `TikTokLive`; no es una integración oficial y puede cambiar si TikTok cambia sus servicios. En esta edición web no se implementan cookies de sesión.
- YouTube usa YouTube Data API v3. Configura tu propia API key y el ID del canal. El sondeo de chat consume cuota; no sondees innecesariamente.
- La PWA requiere HTTPS para instalarse y usar el service worker. El servidor debe permanecer activo para recibir eventos; cerrar la pestaña o suspender el navegador puede impedir el audio en segundo plano. La PWA por sí sola no garantiza ejecución con pantalla apagada.
- Los navegadores móviles pueden exigir una primera interacción de usuario antes de permitir voz/audio.
- Para uso público, establece obligatoriamente `APP_PASSWORD`. Todos los usuarios autorizados comparten la misma instancia/configuración; no compartas el enlace/contraseña. Para una app multiusuario se necesitaría aislamiento por cuenta.
- Los ajustes (incluida la API key de YouTube) se guardan en el servidor. No alojes una instancia pública sin contraseña y no introduzcas credenciales en servidores que no controles.

## Ejecutar localmente para probar

Requiere Python 3.11 o 3.12.

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
# Recomendado incluso en red local: define una contraseña
# Windows PowerShell: $env:APP_PASSWORD="una-contraseña-larga"
# Linux/macOS: export APP_PASSWORD="una-contraseña-larga"
uvicorn app:app --host 0.0.0.0 --port 8000
```

Abre `http://localhost:8000` en el PC para pruebas. Para instalar en Android desde Chrome, publica el servicio con HTTPS, abre el enlace en Chrome y selecciona **Instalar aplicación** o **Añadir a pantalla de inicio**.

## Publicar gratis con Render (Docker)

1. Sube el contenido de esta carpeta a la raíz de un repositorio GitHub.
2. En Render, selecciona **New → Blueprint** y conecta ese repositorio.
3. Este `render.yaml` selecciona el plan `free` y no solicita un disco persistente.
4. Configura `APP_PASSWORD` con una contraseña fuerte cuando Render lo solicite. No la pongas en el repositorio.
5. Abre el dominio HTTPS asignado desde Chrome en PC y Android. En Android puedes usar **Instalar aplicación** o **Añadir a pantalla de inicio**.

**Limitaciones del plan gratuito:** el servicio puede entrar en suspensión tras un período sin actividad y tardar en despertar. No es adecuado para garantizar alertas ininterrumpidas durante un LIVE. La configuración y los sonidos guardados en el servidor usan almacenamiento efímero y pueden perderse al reiniciar o redeplegar; este ZIP no solicita un disco de pago.

## Incluido

- TikTok LIVE: comentarios, entradas, regalos, follows y compartidos (según eventos recibidos por la biblioteca).
- YouTube LIVE: búsqueda de directo activo y lectura del chat mediante Data API v3.
- Bienvenida editable con `{nombre}` / `{name}`.
- Sonidos WAV predeterminados para suscriptor confirmado, visitante confirmado y estado sin verificar; carga de WAV/MP3/OGG.
- Cola de voz con prioridad para entradas; opción “Solo el mensaje”.
- PWA responsive, manifest, icono y caché básica de interfaz.

## Límites conocidos

- El estado de suscripción de una persona puede no venir en el evento de entrada de TikTok. Si no hay un booleano explícito, se clasifica como **sin verificar**; no se adivina.
- La voz web usa la síntesis de voz disponible en el navegador Android, que puede diferir del motor Edge TTS de Windows.
- Esta primera versión es de una sola instancia. La conexión al LIVE vive en el servidor; el sonido y la voz se reproducen en el navegador conectado. Mantén la página abierta y activa para mejor fiabilidad.
- Antes de depender de ella en directo, valida TikTok y YouTube con un evento real y confirma los límites de cuota/API.
