from __future__ import annotations
import asyncio, json, os, time, uuid
from collections import deque
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE = Path(__file__).resolve().parent
STATIC = BASE / 'static'
DATA_DIR = Path(os.environ.get('MOORTTYS_DATA_DIR', str(BASE / 'data'))).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / 'sounds').mkdir(parents=True, exist_ok=True)
CONFIG = DATA_DIR / 'settings.json'
DEFAULTS = {
    'platform':'TikTok LIVE','api_key':'','channel_id':'','tiktok_username':'',
    'voice':'es-MX-DaliaNeural','rate':'+0%','read_comments':True,'speak_author':True,
    'read_gifts':False,'read_social_events':False,'max_message_length':220,
    'blocked_users':'','anti_spam':True,'join_alerts_enabled':True,'join_notifications_enabled':True,
    'join_sound_volume':75,'join_welcome_enabled':True,
    'join_welcome_template':'¡Bienvenido al directo, {nombre}!',
    'subscriber_sound':'','visitor_sound':'','unknown_sound':'',
    'solo_message':False
}

def load_settings():
    try:
        data=json.loads(CONFIG.read_text('utf-8'))
        # Session cookies are deliberately not supported by this web edition or persisted.
        data.pop('tiktok_session_id',None); data.pop('tiktok_target_idc',None)
        return {**DEFAULTS, **data}
    except Exception: return DEFAULTS.copy()

def save_settings(data):
    safe={**DEFAULTS, **data}
    safe.pop('tiktok_session_id',None); safe.pop('tiktok_target_idc',None)
    CONFIG.write_text(json.dumps(safe,ensure_ascii=False,indent=2),encoding='utf-8')
    return safe

app=FastAPI(title='Moorttys Voice PWA', version='0.1.0')
APP_PASSWORD=os.environ.get('APP_PASSWORD','').strip()

@app.middleware('http')
async def protect_api(request, call_next):
    if APP_PASSWORD and request.url.path.startswith('/api/') and request.url.path != '/api/auth-required':
        if request.headers.get('x-app-password','') != APP_PASSWORD:
            return PlainTextResponse('Contraseña incorrecta o sesión no autorizada.',status_code=401)
    return await call_next(request)
app.mount('/static', StaticFiles(directory=STATIC), name='static')
settings=load_settings(); clients:set[WebSocket]=set(); state={'running':False,'status':'LISTO','detail':'Configura una plataforma y pulsa Conectar.','platform':settings['platform']}
chat=deque(maxlen=150); stop_event=asyncio.Event(); worker_task=None; tiktok_client=None; seen_ids=set(); recent_joins={}; recent_text=deque(maxlen=10)
# Batch join welcomes so viewer bursts cannot flood the voice queue.
pending_join_names=[]; pending_join_count=0; join_welcome_task=None

async def broadcast(payload:dict[str,Any]):
    stale=[]
    for ws in list(clients):
        try: await ws.send_json(payload)
        except Exception: stale.append(ws)
    for ws in stale: clients.discard(ws)

async def set_status(status, detail):
    state.update(status=status,detail=detail)
    await broadcast({'type':'status','state':state})

async def log_event(author,text,kind='CHAT',speak=None,priority=False,sound=None):
    item={'id':str(uuid.uuid4()),'time':time.strftime('%H:%M:%S'),'author':str(author or ''),'text':str(text),'kind':kind,'priority':priority,'sound':sound}
    chat.append(item)
    await broadcast({'type':'event','event':item})
    if speak:
        await broadcast({'type':'speak','text':speak,'priority':priority,'sound':sound,'kind':kind})

def is_blocked(author):
    blocked=[x.strip().casefold() for x in str(settings.get('blocked_users','')).split(',') if x.strip()]
    return str(author).casefold() in blocked

async def handle_message(author, message, kind='CHAT'):
    if not message or is_blocked(author): return
    message=str(message).strip()[:max(20,min(500,int(settings.get('max_message_length',220))))]
    if settings.get('anti_spam',True):
        key=(str(author).casefold(),message.casefold())
        if key in recent_text: return
        recent_text.append(key)
    speak=message if settings.get('solo_message') else (f'{author} dice: {message}' if settings.get('speak_author',True) else message)
    if kind=='CHAT' and not settings.get('read_comments',True): speak=None
    if kind=='REGALO' and not settings.get('read_gifts',False): speak=None
    if kind in ('FOLLOW','COMPARTIDO') and not settings.get('read_social_events',False): speak=None
    await log_event(author,message,kind,speak=speak)

async def flush_join_welcomes():
    # Collect joins for a short window and announce them together.
    global pending_join_names, pending_join_count, join_welcome_task
    await asyncio.sleep(2.2)
    count=pending_join_count
    names=pending_join_names[:]
    pending_join_names=[]
    pending_join_count=0
    join_welcome_task=None
    if count and settings.get('join_welcome_enabled',True):
        template=str(settings.get('join_welcome_template') or '¡Bienvenido al directo, {nombre}!')
        if count == 1:
            names_text=names[0] if names else 'Usuario'
            welcome=template.replace('{nombre}',names_text).replace('{name}',names_text).strip()
        elif count <= 3:
            names_text=(' y '.join(names) if len(names)==2 else f'{names[0]}, {names[1]} y {names[2]}')
            welcome=template.replace('{nombre}',names_text).replace('{name}',names_text).strip()
        else:
            welcome=f'¡Han entrado {count} personas al directo!'
        if welcome:
            await broadcast({'type':'speak','text':welcome,'priority':True,'kind':'JOIN_BATCH'})
    # If more joins arrived while broadcasting, start another small batch.
    if pending_join_count and join_welcome_task is None:
        join_welcome_task=asyncio.create_task(flush_join_welcomes())

async def handle_join(user):
    global pending_join_count, join_welcome_task
    name=str(getattr(user,'nickname',None) or getattr(user,'unique_id',None) or 'Usuario').strip()
    username=str(getattr(user,'unique_id',None) or name).strip().casefold()
    now=time.monotonic()
    if now-recent_joins.get(username,-1000)<30: return
    recent_joins[username]=now
    status=None
    for attr in ('is_subscriber','is_subscribed','subscribed'):
        value=getattr(user,attr,None)
        if isinstance(value,bool): status=value; break
    sound='subscriber' if status is True else ('visitor' if status is False else 'unknown')
    label='suscriptor confirmado' if status is True else ('no suscrito confirmado' if status is False else 'suscripción sin verificar')
    await log_event(name,f'Se unió al directo ({label})','ENTRADA',priority=True,sound=sound)
    if settings.get('join_welcome_enabled',True):
        pending_join_count += 1
        # Store only a few display names. Large bursts are announced as a count.
        if len(pending_join_names) < 3:
            pending_join_names.append(name)
        if join_welcome_task is None:
            join_welcome_task=asyncio.create_task(flush_join_welcomes())

async def run_tiktok(username):
    global tiktok_client
    try:
        from TikTokLive import TikTokLiveClient
        from TikTokLive.events import CommentEvent, GiftEvent, FollowEvent, ShareEvent, JoinEvent
        username=username.strip()
        if username.startswith('https://www.tiktok.com/@'): username=username.split('@',1)[1].split('/',1)[0]
        username=username.lstrip('@')
        if not username: raise ValueError('Escribe el usuario de TikTok LIVE.')
        client=TikTokLiveClient(unique_id=username); tiktok_client=client
        @client.on(JoinEvent)
        async def on_join(event):
            if not stop_event.is_set() and getattr(event,'user',None) is not None: await handle_join(event.user)
        @client.on(CommentEvent)
        async def on_comment(event):
            if stop_event.is_set(): return
            user=getattr(event,'user',None); author=getattr(user,'nickname',None) or getattr(user,'unique_id',None) or 'Usuario'
            await handle_message(author,getattr(event,'comment',None) or getattr(event,'content',None) or '')
        @client.on(GiftEvent)
        async def on_gift(event):
            if stop_event.is_set(): return
            user=getattr(event,'user',None); gift=getattr(event,'gift',None)
            await handle_message(getattr(user,'nickname',None) or 'Alguien',f'envió {getattr(event,"repeat_count",1) or 1} {getattr(gift,"name",None) or "regalo"}','REGALO')
        @client.on(FollowEvent)
        async def on_follow(event):
            if stop_event.is_set(): return
            await handle_message(getattr(getattr(event,'user',None),'nickname',None) or 'Alguien','ahora te sigue','FOLLOW')
        @client.on(ShareEvent)
        async def on_share(event):
            if stop_event.is_set(): return
            await handle_message(getattr(getattr(event,'user',None),'nickname',None) or 'Alguien','compartió el directo','COMPARTIDO')
        await set_status('CONECTANDO',f'Conectando con el LIVE de @{username}…')
        await client.connect()
    except asyncio.CancelledError: pass
    except Exception as e: await set_status('ERROR',f'TikTok no pudo conectar: {str(e)[:240]}')
    finally:
        tiktok_client=None
        if state.get('running'): state['running']=False

async def run_youtube(api_key, channel_id):
    try:
        from googleapiclient.discovery import build
        youtube=build('youtube','v3',developerKey=api_key,cache_discovery=False)
        response=youtube.search().list(part='id,snippet',channelId=channel_id,type='video',eventType='live',maxResults=10).execute()
        live_id=None
        for item in response.get('items',[]):
            vid=item.get('id',{}).get('videoId')
            if not vid: continue
            videos=youtube.videos().list(part='liveStreamingDetails',id=vid).execute()
            for v in videos.get('items',[]):
                live_id=v.get('liveStreamingDetails',{}).get('activeLiveChatId')
                if live_id: break
            if live_id: break
        if not live_id: await set_status('SIN DIRECTO','No se encontró un directo público activo con chat habilitado.'); return
        await set_status('CONECTADO','YouTube conectado. Esperando comentarios…')
        page_token=None
        while not stop_event.is_set():
            # Run blocking Google API calls in a worker thread to keep WebSocket responsive.
            response=await asyncio.to_thread(lambda: youtube.liveChatMessages().list(liveChatId=live_id,part='snippet,authorDetails',pageToken=page_token,maxResults=200).execute())
            page_token=response.get('nextPageToken',page_token)
            for item in response.get('items',[]):
                msg_id=item.get('id')
                if msg_id in seen_ids: continue
                if msg_id: seen_ids.add(msg_id)
                sn=item.get('snippet',{}); published=sn.get('publishedAt','')
                # First-page historical messages are ignored by timestamp when possible.
                if published:
                    try:
                        from datetime import datetime, timezone
                        if datetime.fromisoformat(published.replace('Z','+00:00')).timestamp() < started_at: continue
                    except Exception: pass
                author=item.get('authorDetails',{}).get('displayName','Usuario'); text=sn.get('displayMessage','')
                if text: await handle_message(author,text)
            await asyncio.sleep(max(1,min(15,response.get('pollingIntervalMillis',5000)/1000)))
    except asyncio.CancelledError: pass
    except Exception as e: await set_status('ERROR',f'Error de YouTube API: {str(e)[:240]}')
    finally:
        if state.get('running'): state['running']=False

started_at=time.time()
class SettingsBody(BaseModel):
    settings: dict[str,Any]

@app.get('/')
async def index(): return FileResponse(STATIC/'index.html')
@app.get('/manifest.webmanifest')
async def manifest(): return FileResponse(STATIC/'manifest.webmanifest',media_type='application/manifest+json')
@app.get('/api/auth-required')
async def auth_required(): return {'required':bool(APP_PASSWORD)}

@app.get('/api/store')
async def store_config():
    # Checkout is hosted by the payment provider; never expose secret API keys here.
    checkout=os.environ.get('MOORTTYS_PACK_CHECKOUT_URL','').strip()
    if not checkout.startswith('https://'):
        checkout=''
    return {'pack':{'name':'Pack de sonidos de bienvenida','price':'$2.99','checkout_url':checkout,'available':bool(checkout)}}
@app.get('/api/state')
async def get_state(): return {'state':state,'settings':settings,'chat':list(chat)}
@app.post('/api/settings')
async def update_settings(body:SettingsBody):
    global settings
    settings=save_settings(body.settings)
    await broadcast({'type':'settings','settings':settings})
    return {'ok':True,'settings':settings}
@app.post('/api/connect')
async def connect():
    global worker_task,started_at
    if state.get('running'): return {'ok':True,'message':'Ya está conectado o intentando conectar.'}
    stop_event.clear(); state['running']=True; started_at=time.time(); state['platform']=settings.get('platform','TikTok LIVE')
    if state['platform']=='YouTube LIVE':
        if not settings.get('api_key') or not settings.get('channel_id'):
            state['running']=False; raise HTTPException(400,'Introduce la API key y el ID del canal de YouTube.')
        worker_task=asyncio.create_task(run_youtube(settings['api_key'],settings['channel_id']))
    else:
        if not settings.get('tiktok_username'):
            state['running']=False; raise HTTPException(400,'Introduce el usuario de TikTok LIVE.')
        worker_task=asyncio.create_task(run_tiktok(settings['tiktok_username']))
    await set_status('CONECTANDO','Preparando conexión…')
    return {'ok':True}
@app.post('/api/disconnect')
async def disconnect():
    global worker_task
    stop_event.set()
    if tiktok_client is not None:
        try: await tiktok_client.disconnect()
        except Exception: pass
    if worker_task and not worker_task.done(): worker_task.cancel()
    state['running']=False
    await set_status('LISTO','Lector detenido.')
    return {'ok':True}
@app.websocket('/ws')
async def websocket_endpoint(ws:WebSocket):
    if APP_PASSWORD and ws.query_params.get('password','') != APP_PASSWORD:
        await ws.close(code=1008); return
    await ws.accept(); clients.add(ws)
    try:
        await ws.send_json({'type':'initial','state':state,'settings':settings,'chat':list(chat)})
        while True: await ws.receive_text()
    except WebSocketDisconnect: clients.discard(ws)
    except Exception: clients.discard(ws)

from fastapi import UploadFile, File
@app.post('/api/upload-sound')
async def upload_sound(file: UploadFile = File(...)):
    name=Path(file.filename or 'sound.wav').name
    suffix=Path(name).suffix.lower()
    if suffix not in ('.wav','.mp3','.ogg'): raise HTTPException(400,'Usa un archivo WAV, MP3 u OGG.')
    data=await file.read()
    if len(data)>8*1024*1024: raise HTTPException(413,'El sonido debe pesar menos de 8 MB.')
    dest=DATA_DIR/'sounds'/f'custom_{uuid.uuid4().hex[:10]}{suffix}'
    dest.write_bytes(data)
    return {'ok':True,'url':'/custom-sounds/'+dest.name,'filename':name}

@app.get('/custom-sounds/{filename}')
async def custom_sound(filename: str):
    name=Path(filename).name
    if name != filename or not name.startswith('custom_'): raise HTTPException(404,'Sonido no encontrado.')
    path=DATA_DIR/'sounds'/name
    if not path.is_file(): raise HTTPException(404,'Sonido no encontrado.')
    return FileResponse(path)
