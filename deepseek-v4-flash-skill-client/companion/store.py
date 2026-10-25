"""Local-only persistence. Every query is scoped to a character or conversation."""
import json
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEXT_PATH = ROOT / 'skills/cangzhou-chat-runtime/references/runtime-text.json'
REQUIRED = ('local_profile', 'local_chat', 'local_rules', 'local_legacy_rules', 'local_style', 'local_select', 'local_extract', 'local_designer', 'local_designer_start', 'local_designer_options', 'local_quality', 'local_quality_retry', 'local_quality_choice')


def texts():
    data = json.loads(TEXT_PATH.read_text())
    if any(not isinstance(data.get(k), str) or not data[k] for k in REQUIRED):
        raise RuntimeError('本地运行时提示不完整，请检查 runtime-text.json')
    return data


def uid():
    return uuid.uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat()


def clean(value, limit=12000):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError('内容格式不正确或超过长度限制')
    return value.strip()


def default_card():
    base = ROOT / 'skills/cen-yexia-girlfriend/references'
    core = (base / 'persona-chat-template.md').read_text().strip()
    details = (base / 'local-demo-details.md').read_text().strip()
    return dict(name='岑野夏', tagline='热烈、聪明、有主见。一起把普通日子过得有趣。', core=core,
                details=details, rules=texts()['local_rules'],
                gender='女', relationship='已经明确建立恋爱关系，处于积累共同经历的早期稳定阶段。默认称呼“你”。尚无已确认共同事件；不预设纪念日、现实见面或旅行。')


def validate_card(body):
    limits = dict(name=60, tagline=200, core=16000, details=60000, rules=12000, relationship=4000, gender=40, style=6000)
    card = {key: clean(body.get(key, ''), limit) for key, limit in limits.items()}
    if not card['name'] or not card['core']:
        raise ValueError('请填写人物名称与核心设定')
    if not card['gender']:
        card['gender'] = '未设定'
    if not card['rules']:
        card['rules'] = texts()['local_rules']
    return card


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS cards (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, tagline TEXT, core TEXT, details TEXT,
              rules TEXT, relationship TEXT, version INTEGER DEFAULT 1, epoch INTEGER DEFAULT 0,
              mood TEXT DEFAULT '', mood_at TEXT DEFAULT '', created TEXT);
            CREATE TABLE IF NOT EXISTS versions (
              id TEXT PRIMARY KEY, card_id TEXT REFERENCES cards(id) ON DELETE CASCADE,
              version INTEGER, data TEXT, created TEXT);
            CREATE TABLE IF NOT EXISTS conversations (
              id TEXT PRIMARY KEY, card_id TEXT REFERENCES cards(id) ON DELETE CASCADE,
              title TEXT, trial INTEGER DEFAULT 0, topic TEXT DEFAULT '', cursor INTEGER DEFAULT 0, created TEXT);
            CREATE TABLE IF NOT EXISTS messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
              role TEXT, content TEXT, created TEXT, status TEXT DEFAULT 'ok',
              request_id TEXT UNIQUE, debug TEXT DEFAULT '{}', forgotten INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS memories (
              id TEXT PRIMARY KEY, card_id TEXT REFERENCES cards(id) ON DELETE CASCADE,
              key TEXT, kind TEXT, text TEXT, source_ids TEXT DEFAULT '[]', created TEXT, updated TEXT,
              UNIQUE(card_id,key));
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY, conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
              upto INTEGER, status TEXT DEFAULT 'pending', attempts INTEGER DEFAULT 0, error TEXT DEFAULT '', created TEXT,
              UNIQUE(conversation_id,upto));
            CREATE TABLE IF NOT EXISTS designs (id TEXT PRIMARY KEY, history TEXT, draft TEXT, created TEXT);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
            CREATE INDEX IF NOT EXISTS messages_conversation ON messages(conversation_id,id);
            CREATE INDEX IF NOT EXISTS memories_card ON memories(card_id);
            ''')
            if 'gender' not in {r['name'] for r in db.execute('PRAGMA table_info(cards)')}:
                db.execute("ALTER TABLE cards ADD COLUMN gender TEXT DEFAULT '未设定'")
                db.execute("UPDATE cards SET gender='女' WHERE name='岑野夏'")
            if 'style' not in {r['name'] for r in db.execute('PRAGMA table_info(cards)')}:
                db.execute("ALTER TABLE cards ADD COLUMN style TEXT NOT NULL DEFAULT ''")
            db.execute("UPDATE jobs SET status='pending' WHERE status='running'")
            db.execute("UPDATE messages SET status='failed' WHERE status='pending'")
            initialized = db.execute("SELECT 1 FROM settings WHERE key='initialized'").fetchone()
        if not initialized:
            self.create_card(default_card())
            self.setting('initialized', True)
        else:
            # Upgrade only the untouched built-in template, preserving user edits
            # and storing the old card as a restorable version.
            raw = (ROOT / 'skills/cen-yexia-girlfriend/references/character-card.md').read_text()
            section = raw.split('## 18. 可直接使用的运行时人格 Skill', 1)[1].split('## 19.', 1)[0]
            old_core = re.search(r'```text\s*(.*?)```', section, re.S).group(1).strip()
            old_compact = (ROOT / 'skills/cen-yexia-girlfriend/references/local-demo-core.md').read_text().strip()
            for c in self.snapshot()['cards']:
                if c['name']=='岑野夏' and c['core'] in (old_core, old_compact):
                    new = default_card()
                    self.update_card(c['id'], {**c, 'core': new['core'], 'details': new['details']})
            runtime = texts()
            for c in self.snapshot()['cards']:
                if c['rules']==runtime['local_legacy_rules']:
                    self.update_card(c['id'], {**c, 'rules':runtime['local_rules']})
        os.chmod(self.path, 0o600)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def setting(self, key, value=None):
        with self.db() as db:
            if value is not None:
                db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(value, ensure_ascii=False)))
            row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
            return json.loads(row['value']) if row else None

    def card(self, card_id):
        with self.db() as db:
            row = db.execute('SELECT * FROM cards WHERE id=?', (card_id,)).fetchone()
            if not row:
                raise ValueError('人物卡不存在')
            return dict(row)

    def create_card(self, data):
        card = validate_card(data)
        card_id = uid()
        with self.db() as db:
            db.execute('INSERT INTO cards(id,name,tagline,core,details,rules,relationship,gender,style,created) VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (card_id, *card.values(), now()))
        self.create_conversation(card_id)
        return self.card(card_id)

    def update_card(self, card_id, data):
        card = validate_card(data)
        with self.db() as db:
            old = db.execute('SELECT * FROM cards WHERE id=?', (card_id,)).fetchone()
            if not old:
                raise ValueError('人物卡不存在')
            if data.get('version') != old['version']:
                raise ValueError('人物卡已更新，请重新打开编辑')
            db.execute('INSERT INTO versions VALUES (?,?,?,?,?)', (uid(), card_id, old['version'], json.dumps(dict(old), ensure_ascii=False), now()))
            db.execute('UPDATE cards SET name=?,tagline=?,core=?,details=?,rules=?,relationship=?,gender=?,style=?,version=version+1,epoch=epoch+1 WHERE id=?', (*card.values(), card_id))
        return self.card(card_id)

    def create_conversation(self, card_id, title='新的对话', trial=False):
        self.card(card_id)
        cid = uid()
        with self.db() as db:
            db.execute('INSERT INTO conversations(id,card_id,title,trial,created) VALUES (?,?,?,?,?)',
                       (cid, card_id, clean(title, 100) or '新的对话', int(bool(trial)), now()))
        return self.conversation(cid)

    def conversation(self, cid):
        with self.db() as db:
            row = db.execute('SELECT * FROM conversations WHERE id=?', (cid,)).fetchone()
            if not row:
                raise ValueError('对话不存在')
            return dict(row)

    def memories(self, card_id):
        self.card(card_id)
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM memories WHERE card_id=? ORDER BY updated DESC', (card_id,))]

    def messages(self, cid, limit=None, for_context=False):
        self.conversation(cid)
        with self.db() as db:
            where = " AND status='ok' AND forgotten=0" if for_context else ''
            sql = 'SELECT * FROM messages WHERE conversation_id=?' + where + ' ORDER BY id DESC'
            args = [cid]
            if limit:
                sql += ' LIMIT ?'
                args.append(limit)
            return list(reversed([dict(r) for r in db.execute(sql, args)]))

    def snapshot(self):
        with self.db() as db:
            cards = [dict(r) for r in db.execute('SELECT * FROM cards ORDER BY created')]
            conversations = [dict(r) for r in db.execute('SELECT * FROM conversations ORDER BY created DESC')]
            jobs = [dict(r) for r in db.execute("SELECT j.*, c.card_id FROM jobs j JOIN conversations c ON c.id=j.conversation_id WHERE j.status!='done' ORDER BY j.created DESC LIMIT 20")]
            for c in cards:
                c['memory_count'] = db.execute('SELECT COUNT(*) FROM memories WHERE card_id=?', (c['id'],)).fetchone()[0]
        return dict(cards=cards, conversations=conversations, jobs=jobs)

    def edit_memory(self, card_id, body):
        self.card(card_id)
        kind = body.get('kind', 'fact')
        if kind not in ('fact', 'preference', 'boundary', 'relationship', 'event'):
            raise ValueError('无效记忆类型')
        value = clean(body.get('text', ''), 2000)
        if not value:
            raise ValueError('记忆不能为空')
        mid = body.get('id') or uid()
        with self.db() as db:
            old = db.execute('SELECT * FROM memories WHERE id=? AND card_id=?', (mid, card_id)).fetchone()
            if body.get('id') and not old:
                raise ValueError('记忆不存在')
            if old:
                self._forget_sources(db, old['source_ids'])
                db.execute('UPDATE memories SET text=?,kind=?,source_ids=\'[]\',updated=? WHERE id=?', (value, kind, now(), mid))
            else:
                db.execute('INSERT INTO memories VALUES (?,?,?,?,?,?,?,?)', (mid, card_id, mid, kind, value, '[]', now(), now()))
            self._invalidate(db, card_id, mid if old else None)
        return mid

    @staticmethod
    def _forget_sources(db, sources):
        for source in json.loads(sources):
            db.execute('UPDATE messages SET forgotten=1 WHERE id=?', (source,))
            reply = db.execute("SELECT id,role FROM messages WHERE conversation_id=(SELECT conversation_id FROM messages WHERE id=?) AND id>? ORDER BY id LIMIT 1", (source,source)).fetchone()
            if reply and reply['role']=='assistant':
                db.execute('UPDATE messages SET forgotten=1 WHERE id=?', (reply['id'],))

    @staticmethod
    def _invalidate(db, card_id, memory_id=None):
        db.execute("UPDATE cards SET epoch=epoch+1,mood='',mood_at='' WHERE id=?", (card_id,))
        db.execute("UPDATE conversations SET topic='' WHERE card_id=?", (card_id,))
        # Adding a fact must not erase every assistant turn. Only invalidate replies
        # that actually depended on the edited/deleted memory.
        if memory_id:
            rows = db.execute("SELECT id,debug FROM messages WHERE role='assistant' AND conversation_id IN (SELECT id FROM conversations WHERE card_id=?)", (card_id,)).fetchall()
            for row in rows:
                if any(c.get('id') == 'm:'+memory_id for c in json.loads(row['debug']).get('selected', [])):
                    db.execute('UPDATE messages SET forgotten=1 WHERE id=?', (row['id'],))
        db.execute("UPDATE messages SET debug='{}' WHERE conversation_id IN (SELECT id FROM conversations WHERE card_id=?)", (card_id,))

    def delete_memory(self, card_id, mid):
        with self.db() as db:
            old = db.execute('SELECT * FROM memories WHERE id=? AND card_id=?', (mid, card_id)).fetchone()
            if not old:
                raise ValueError('记忆不存在')
            self._forget_sources(db, old['source_ids'])
            db.execute('DELETE FROM memories WHERE id=? AND card_id=?', (mid, card_id))
            self._invalidate(db, card_id, mid)

    def delete_conversation(self, cid):
        conv = self.conversation(cid)
        with self.db() as db:
            # Explicit action deletes associated memories as well as messages.
            ids = {r[0] for r in db.execute('SELECT id FROM messages WHERE conversation_id=?', (cid,))}
            for row in db.execute('SELECT id,source_ids FROM memories WHERE card_id=?', (conv['card_id'],)).fetchall():
                if ids.intersection(json.loads(row['source_ids'])):
                    db.execute('DELETE FROM memories WHERE id=?', (row['id'],))
            self._invalidate(db, conv['card_id'])
            db.execute('DELETE FROM conversations WHERE id=?', (cid,))

    def export(self):
        tables = ('cards', 'versions', 'conversations', 'messages', 'memories', 'designs', 'jobs')
        with self.db() as db:
            return dict(format='companion-local-v1', exported_at=now(), tables={t: [dict(r) for r in db.execute('SELECT * FROM ' + t)] for t in tables})

    def import_data(self, data):
        if not isinstance(data, dict) or data.get('format') != 'companion-local-v1':
            raise ValueError('备份格式不正确')
        tables = data.get('tables', {})
        if not isinstance(tables, dict) or not isinstance(tables.get('cards'), list):
            raise ValueError('备份缺少人物卡')
        if len(tables['cards']) > 100:
            raise ValueError('一次最多导入100个人物')
        # Import as copies; identities and source references are remapped atomically.
        cmap, vmap, mmap = {}, {}, {}
        with self.db() as db:
            for c in tables['cards']:
                fields = validate_card(c)
                cid = uid()
                if c['id'] in cmap:
                    raise ValueError('备份人物重复')
                cmap[c['id']] = cid
                db.execute('INSERT INTO cards(id,name,tagline,core,details,rules,relationship,gender,style,created) VALUES (?,?,?,?,?,?,?,?,?,?)',
                           (cid, *fields.values(), now()))
                version = c.get('version', 1)
                if not isinstance(version, int) or not 1 <= version <= 100000:
                    raise ValueError('人物版本无效')
                db.execute('UPDATE cards SET version=? WHERE id=?', (version, cid))
            for v in tables.get('versions', []):
                old = json.loads(v['data'])
                old = {**validate_card(old), 'id': cmap[v['card_id']], 'version': int(v['version'])}
                db.execute('INSERT INTO versions VALUES (?,?,?,?,?)',
                           (uid(), cmap[v['card_id']], old['version'], json.dumps(old, ensure_ascii=False), now()))
            for c in tables.get('conversations', []):
                cid = uid()
                if c['id'] in vmap:
                    raise ValueError('备份对话重复')
                vmap[c['id']] = cid
                db.execute('INSERT INTO conversations(id,card_id,title,trial,created) VALUES (?,?,?,?,?)',
                           (cid, cmap[c['card_id']], clean(c['title'],100), int(bool(c.get('trial'))), now()))
            for m in tables.get('messages', []):
                if m.get('role') not in ('user','assistant'):
                    raise ValueError('备份消息角色无效')
                cur = db.execute('INSERT INTO messages(conversation_id,role,content,created,status,forgotten) VALUES (?,?,?,?,?,?)',
                                 (vmap[m['conversation_id']], m['role'], clean(m['content'],16000), clean(m['created'],100), 'failed' if m.get('status')!='ok' else 'ok', int(bool(m.get('forgotten')))))
                mmap[m['id']] = cur.lastrowid
            for m in tables.get('memories', []):
                cid = cmap[m['card_id']]
                refs = [mmap[x] for x in json.loads(m.get('source_ids','[]')) if x in mmap]
                for ref in refs:
                    owner = db.execute('SELECT c.card_id FROM messages m JOIN conversations c ON c.id=m.conversation_id WHERE m.id=?', (ref,)).fetchone()[0]
                    if owner != cid:
                        raise ValueError('备份含跨人物记忆来源')
                db.execute('INSERT INTO memories VALUES (?,?,?,?,?,?,?,?)',
                           (uid(), cid, clean(m['key'],160), clean(m['kind'],40), clean(m['text'],2000), json.dumps(refs), now(), now()))
            for cid in vmap.values():
                db.execute('UPDATE conversations SET cursor=COALESCE((SELECT MAX(id) FROM messages WHERE conversation_id=?),0) WHERE id=?', (cid,cid))
            # Resume unfinished extraction from its original checkpoint, not from zero.
            for c in tables.get('conversations', []):
                pending = [j for j in tables.get('jobs', []) if j['conversation_id'] == c['id'] and j['status'] != 'done']
                if pending and not c.get('trial'):
                    db.execute('UPDATE conversations SET cursor=? WHERE id=?', (mmap.get(c.get('cursor'), 0), vmap[c['id']]))
                    for j in pending:
                        if j['upto'] in mmap:
                            db.execute('INSERT OR IGNORE INTO jobs(id,conversation_id,upto,created) VALUES (?,?,?,?)',
                                       (uid(), vmap[c['id']], mmap[j['upto']], now()))
            for d in tables.get('designs', []):
                history = json.loads(d['history'])
                draft = json.loads(d['draft'])
                if not isinstance(history, list) or len(history) > 61:
                    raise ValueError('定制会话格式不正确')
                for message in history:
                    if message.get('role') not in ('user', 'assistant'):
                        raise ValueError('定制消息格式不正确')
                    clean(message.get('content'), 4000)
                if draft is not None:
                    draft = validate_card(draft)
                db.execute('INSERT INTO designs VALUES (?,?,?,?)',
                           (uid(), json.dumps(history, ensure_ascii=False), json.dumps(draft, ensure_ascii=False), now()))
        return len(cmap)
