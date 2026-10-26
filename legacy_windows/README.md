# Moorttys Voice para Windows

Lector de comentarios para **YouTube LIVE y TikTok LIVE**, con interfaz de estudio gamer negra/roja, panel de control desplazable, tarjetas de estado, feed de chat y voces en español. Esta es una versión inicial de desarrollo, no un producto comercial terminado.

## Requisitos
- Windows 10/11
- Python 3.10 o posterior (recomendado Python 3.12 o 3.13)
- Conexión a internet
- Para YouTube: API key de Google Cloud con YouTube Data API v3 habilitada
- Para TikTok: el creador objetivo debe tener un LIVE público activo

## Inicio rápido
1. Descomprime el ZIP en una carpeta.
2. Ejecuta `start.bat`.
3. En el selector **PLATAFORMA**, elige TikTok LIVE o YouTube LIVE.
4. Para TikTok, introduce el nombre del creador que está en directo (con o sin `@`). No hace falta iniciar sesión para directos públicos normales.
5. Para YouTube, introduce la API key y el ID del canal.
6. Guarda la configuración y pulsa **INICIAR LECTOR**.
7. Pulsa **PROBAR VOZ** para probar el audio sin conectar un directo.

## Funciones de TikTok
- Conexión por nombre de usuario para directos públicos.
- Lectura de comentarios.
- Opciones para leer regalos, follows y compartidos.
- Alertas de entrada con sonidos predeterminados para suscriptor confirmado, no suscrito confirmado y estado sin verificar.
- Permite elegir sonidos propios (WAV, MP3 u OGG), preescucharlos y ajustar el volumen por separado.
- Interruptores independientes para sonidos, notificaciones en el chat y bienvenida hablada al entrar.
- Bienvenida automática por la voz configurada; frase editable con `{nombre}` (también admite `{name}`). Ejemplo: `¡Bienvenido al directo, {nombre}!`.
- Antiduplicado de entradas de la misma cuenta durante 30 segundos.
- El estado de suscripción solo se clasifica si el evento expone explícitamente un valor booleano; de lo contrario se usa la alerta neutral.
- Campos de sesión opcionales en configuración avanzada para situaciones que realmente la requieran.

**Importante sobre sesión/cookies:** los campos `sessionid` y `tt-target-idc` son credenciales sensibles. No los compartas ni los subas a GitHub. No son necesarios para la mayoría de directos públicos. No introduzcas tu contraseña de TikTok en esta aplicación.

## Sonidos de entrada
La carpeta `sounds` incluye tres efectos WAV que funcionan como predeterminados. Puedes escoger archivos propios desde la sección **ALERTAS DE ENTRADA**. Los archivos elegidos se guardan como rutas locales en `settings.json`, así que si mueves el programa a otra carpeta tendrás que volver a seleccionarlos si la ruta cambia.

## Funciones de YouTube
- Busca directos públicos activos del canal por API.
- Lee mensajes nuevos del chat del directo.
- Permite seleccionar voz española, velocidad y si anuncia el nombre del autor.

## Limitaciones
- La conexión TikTok usa la biblioteca no oficial TikTokLive, que se basa en el protocolo interno de TikTok. TikTok puede cambiarlo o limitar las conexiones, y algunos eventos pueden no estar disponibles en todos los directos o regiones. No se garantiza conexión a todos los LIVE.
- La opción de sesión avanzada solo sirve para los casos compatibles con la biblioteca; no equivale a un inicio de sesión oficial de TikTok.
- La API de YouTube puede tener límites de cuota.
- La voz de Edge TTS requiere internet. Revisa las condiciones del servicio y licencias antes de distribuir o vender el programa.
- Esta versión no está empaquetada como instalador y todavía requiere pruebas reales en el PC.

## Privacidad
Los ajustes normales se guardan en `settings.json` dentro de la carpeta del programa. Los campos de sesión de TikTok se mantienen solo en memoria y no se guardan en ese archivo. Las cookies siguen siendo credenciales sensibles durante el uso; no las compartas ni las introduzcas si no confías en el método de conexión. Para uso comercial, revisa términos y licencias de cada dependencia.


## Filtros y lectura de mensajes nuevos
- Al iniciar el lector se limpia la cola de audio pendiente y se omite el historial de YouTube anterior al inicio de la sesión.
- La cola inteligente conserva prioridad para mensajes recientes cuando se acumulan comentarios.
- Filtro anti-spam para evitar repetir el mismo comentario del mismo usuario durante 20 segundos.
- Longitud máxima configurable (20–1000 caracteres).
- Lista de usuarios bloqueados configurable, separada por comas.
- La voz y la velocidad configuradas se conservan.
