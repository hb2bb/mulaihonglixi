#!/usr/bin/env python3
"""Start the offline-storage companion demo (DeepSeek is the only required API)."""
import argparse
import json
import os
import secrets
import threading
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from companion.store import Store, clean, default_card, texts
from companion.engine import Engine
from deepseek_skill_client import DeepSeekError
from web_server import load_dotenv

HERE = Path(__file__).resolve().parent
STATIC = HERE / 'companion/static'


class Server(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, store, engine, access_secret=None, save_key=None):
        super().__init__(address, Handler)
        self.store, self.engine = store, engine
        self.token = secrets.token_urlsafe(32)
        self.access_secret, self.save_key = access_secret, save_key


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, data, status=200, content_type='application/json; charset=utf-8'):
        raw = data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('X-Frame-Options','SAMEORIGIN')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'")
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError):
            pass

    def valid_host(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')

    def valid_app(self):
        if not self.server.access_secret:
            return True
        try:
            cookies = SimpleCookie(self.headers.get('Cookie', ''))
            value = cookies['qiyu_access'].value if 'qiyu_access' in cookies else ''
            return secrets.compare_digest(value, self.server.access_secret)
        except Exception:
            return False

    def do_GET(self):
        if not self.valid_app():
            return self.respond(dict(error='仅允许应用内访问'),403)
        if not self.valid_host():
            return self.respond(dict(error='只允许本机访问'),403)
        u = urlparse(self.path)
        q = parse_qs(u.query)
        store, engine = self.server.store, self.server.engine
        try:
            if u.path == '/api/bootstrap':
                return self.respond(dict(token=self.server.token, **store.snapshot(), ready=bool(engine.api_key), model=engine.model,
                                         selection_enabled=store.setting('selection_enabled') is not False,
                                         secure_key_storage=bool(self.server.save_key), weather=store.setting('weather') or dict(enabled=False), database=str(store.path)))
            if u.path.startswith('/api/') and not secrets.compare_digest(self.headers.get('X-Local-Token',''),self.server.token):
                return self.respond(dict(error='请刷新页面后重试'),403)
            if u.path == '/api/messages':
                cid=q.get('id',[''])[0]
                return self.respond(dict(conversation=store.conversation(cid),messages=store.messages(cid)))
            if u.path == '/api/memories':
                cid=q.get('id',[''])[0]
                memories=store.memories(cid)
                with store.db() as db:
                    sources={str(r['id']):dict(r) for r in db.execute('SELECT m.id,m.content,m.created FROM messages m JOIN conversations c ON c.id=m.conversation_id WHERE c.card_id=? AND m.role=\'user\'',(cid,))}
                return self.respond(dict(memories=memories,sources=sources))
            if u.path == '/api/versions':
                cid=q.get('id',[''])[0]
                store.card(cid)
                with store.db() as db:
                    rows=[dict(r) for r in db.execute('SELECT * FROM versions WHERE card_id=? ORDER BY version DESC',(cid,))]
                return self.respond(dict(versions=rows))
            if u.path == '/api/design':
                return self.respond(engine.designer(q.get('id',[''])[0]))
            if u.path == '/api/designs':
                with store.db() as db:
                    rows = [dict(r) for r in db.execute('SELECT * FROM designs ORDER BY created DESC LIMIT 50')]
                return self.respond(dict(designs=[dict(id=r['id'], created=r['created'], name=(json.loads(r['draft']) or {}).get('name', '未完成的定制')) for r in rows]))
            if u.path == '/api/export':
                return self.respond(store.export())
            files={'/':('index.html','text/html'),'/app.js':('app.js','text/javascript'),'/style.css':('style.css','text/css')}
            if u.path in files:
                name, mime=files[u.path]
                return self.respond((STATIC/name).read_bytes(),content_type=mime+'; charset=utf-8')
            return self.respond(dict(error='页面不存在'),404)
        except (ValueError,KeyError) as exc:
            return self.respond(dict(error=str(exc)),400)

    def do_POST(self):
        if not self.valid_app() or not self.valid_host() or not secrets.compare_digest(self.headers.get('X-Local-Token',''),self.server.token):
            return self.respond(dict(error='本地请求校验失败，请刷新页面'),403)
        origin=self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'):
            return self.respond(dict(error='不允许跨站请求'),403)
        try:
            size=int(self.headers.get('Content-Length','0'))
            limit=32_000_000 if self.path=='/api/import' else 150_000
            if size<=0 or size>limit:
                raise ValueError('请求为空或过大')
            body=json.loads(self.rfile.read(size))
            if not isinstance(body,dict):
                raise ValueError('请求格式不正确')
            result=self.dispatch(body)
            self.respond(result)
        except DeepSeekError as exc:
            message=f'DeepSeek 请求失败（HTTP {exc.status_code}）。请检查 Key、余额与模型名称。' if exc.status_code else '无法连接 DeepSeek 或请求超时，请检查网络后重试。'
            self.respond(dict(error=message),502)
        except (ValueError,KeyError,TypeError) as exc:
            self.respond(dict(error=str(exc) if isinstance(exc,ValueError) else '请求字段不完整或格式错误'),400)
        except Exception:
            self.respond(dict(error='本地处理失败；请检查数据或重试，原有数据不会被替换。'),500)

    def dispatch(self,b):
        store,engine=self.server.store,self.server.engine
        p=self.path
        if p=='/api/chat':
            return engine.chat(b['conversation_id'],b['content'],b['request_id'])
        if p=='/api/card/save':
            return dict(card=store.update_card(b['id'],b) if b.get('id') else store.create_card(b))
        if p=='/api/card/style':
            return engine.character_style(b)
        if p=='/api/card/default':
            return dict(card=store.create_card(default_card()))
        if p=='/api/card/copy':
            card=store.card(b['id'])
            card['name']=card['name']+' · 副本'
            return dict(card=store.create_card(card))
        if p=='/api/card/delete':
            store.card(b['id'])
            with store.db() as db:
                db.execute('DELETE FROM cards WHERE id=?',(b['id'],))
            return dict(ok=True)
        if p=='/api/conversation/create':
            return dict(conversation=store.create_conversation(b['card_id'],b.get('title','新的对话'),b.get('trial',False)))
        if p=='/api/conversation/delete':
            store.delete_conversation(b['id'])
            return dict(ok=True)
        if p=='/api/memory/save':
            return dict(id=store.edit_memory(b['card_id'],b))
        if p=='/api/memory/delete':
            store.delete_memory(b['card_id'],b['id'])
            return dict(ok=True)
        if p=='/api/memory/reset':
            cid=b['card_id']
            store.card(cid)
            with store.db() as db:
                db.execute('DELETE FROM memories WHERE card_id=?',(cid,))
                db.execute('UPDATE messages SET forgotten=1 WHERE conversation_id IN (SELECT id FROM conversations WHERE card_id=?)',(cid,))
                store._invalidate(db,cid)
            return dict(ok=True)
        if p=='/api/jobs/retry':
            cid=b['card_id']
            store.card(cid)
            with store.db() as db:
                db.execute("UPDATE jobs SET status='pending',attempts=0,error='' WHERE status='failed' AND conversation_id IN (SELECT id FROM conversations WHERE card_id=?)",(cid,))
            return dict(ok=True)
        if p=='/api/design':
            return engine.designer(b.get('id'),b.get('content'))
        if p=='/api/settings':
            model=clean(b.get('model',engine.model),100)
            if not re_model(model):
                raise ValueError('模型名只能包含字母、数字、点、下划线或连字符')
            key=clean(b.get('api_key',''),300)
            if key:
                if self.server.save_key:
                    self.server.save_key(key)
                engine.api_key=key
            engine.model=model
            store.setting('model',model)
            store.setting('selection_enabled',bool(b.get('selection_enabled',True)))
            return dict(ready=bool(engine.api_key),model=engine.model)
        if p=='/api/test-key':
            # Test only the connection; no character or user data are sent.
            result=engine.call('test',[dict(role='user',content='Hi')],30)
            return dict(ok=bool(result))
        if p=='/api/weather':
            return dict(weather=engine.weather(b))
        if p=='/api/import':
            return dict(count=store.import_data(b))
        raise ValueError('未知操作')


def re_model(value):
    import re
    return bool(re.fullmatch(r'[a-zA-Z0-9._-]{1,100}',value))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--data',type=Path,default=HERE/'.local-data/companion.sqlite3')
    args=parser.parse_args()
    load_dotenv(HERE/'.env')
    texts()
    store=Store(args.data)
    engine=Engine(store)
    engine.start_worker()
    # Weather is opt-in and refreshes independently; it never blocks message generation.
    def weather_worker():
        while not engine.stopping.is_set():
            config=store.setting('weather')
            if config and config.get('enabled'):
                engine.weather(config)
            engine.stopping.wait(1800)
    threading.Thread(target=weather_worker,daemon=True).start()
    server=Server(('127.0.0.1',args.port),store,engine)
    print(f'伴侣 · 本地 Demo：http://127.0.0.1:{args.port}',flush=True)
    print('本地数据：'+str(args.data),flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        engine.stopping.set()
        server.server_close()


if __name__=='__main__':
    main()
