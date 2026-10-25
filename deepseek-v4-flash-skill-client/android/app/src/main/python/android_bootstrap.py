"""Phone-local runtime. The activity supplies an app-private, authenticated origin."""
import sys
import threading
from pathlib import Path
_server = None

def start(runtime_root, data_root, secret):
    global _server
    if _server is not None:
        return _server.server_port
    sys.path.insert(0,str(Path(runtime_root)/'client'))
    from java import jclass
    from companion.store import Store
    from companion.engine import Engine
    from local_demo import Server
    vault = jclass('app.qiyu.local.KeyVault')
    store = Store(Path(data_root)/'companion.sqlite3')
    engine = Engine(store)
    try:
        engine.api_key = str(vault.load())
    except Exception:
        engine.api_key = ''  # Allow re-entry if Android invalidated the encryption key.
    _server = Server(('127.0.0.1',0),store,engine,access_secret=str(secret),save_key=vault.save)
    engine.start_worker()
    def weather():
        while not engine.stopping.is_set():
            config = store.setting('weather')
            if config and config.get('enabled'):
                try: engine.weather(config)
                except Exception: pass
            engine.stopping.wait(1800)
    threading.Thread(target=weather,daemon=True).start()
    threading.Thread(target=_server.serve_forever,daemon=True).start()
    return _server.server_port
