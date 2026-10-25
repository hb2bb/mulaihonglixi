"""Retrieval, generation, durable consolidation jobs and guided character creation."""
import json
import os
import re
import threading
import time
from datetime import datetime
from urllib.request import urlopen
from urllib.parse import urlencode
from deepseek_skill_client import DeepSeekSkillClient, SkillLoader, DeepSeekError
from companion.store import ROOT, clean, default_card, now, texts, uid, validate_card


def parse_json(raw):
    raw = raw.strip()
    if raw.startswith('```'):
        raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw)
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError('模型返回格式不正确，请重试')
    return result


def tokens(text):
    text = text.lower()
    words = set(re.findall(r'[a-z0-9_]{2,}', text))
    for part in re.findall(r'[\u4e00-\u9fff]+', text):
        words.update(part[i:i+2] for i in range(len(part)-1))
    return words


def relevant(query, content):
    a, b = tokens(query), tokens(content)
    return len(a & b) / max(1, len(a))


class Engine:
    def __init__(self, store, provider=None):
        self.store = store
        self.provider = provider
        self.api_key = os.environ.get('DEEPSEEK_API_KEY', '')
        self.model = store.setting('model') or os.environ.get('DEEPSEEK_MODEL', 'deepseek-v4-flash')
        self.locks = {}
        self.lock_guard = threading.Lock()
        self.stopping = threading.Event()
        self.weather_cache = None

    def lock(self, key):
        with self.lock_guard:
            return self.locks.setdefault(key, threading.Lock())

    def call(self, purpose, messages, max_tokens=1500):
        if self.provider:
            return self.provider(purpose, messages)
        if not self.api_key:
            raise ValueError('请先在设置中填写 DeepSeek API Key')
        thinking = purpose in ('chat', 'quality', 'quality_choice', 'designer', 'style', 'profile')
        client = DeepSeekSkillClient(api_key=self.api_key, skill_loader=SkillLoader(ROOT, include_user_skills=False),
                                    base_url='https://api.deepseek.com', model=self.model,
                                    thinking=thinking, reasoning_effort='max' if thinking else 'high',
                                    include_reasoning_options=True, timeout=90)
        return client.complete(messages, max_tokens=max(12000, max_tokens) if thinking else max_tokens)

    def structured(self, purpose, payload, max_tokens=1600):
        return parse_json(self.call(purpose, [dict(role='system', content=texts()['local_'+purpose]),
                                            dict(role='user', content=json.dumps(payload, ensure_ascii=False))], max_tokens))

    def runtime_state(self, card):
        current = datetime.now().astimezone()
        mood = ''
        if card['mood_at']:
            age = current.timestamp() - datetime.fromisoformat(card['mood_at']).timestamp()
            if age < 1800:
                mood = card['mood']
        return dict(local_time=current.isoformat(timespec='seconds'), timezone=str(current.tzinfo),
                    mood=mood, weather=self.weather_cache or None)

    def retrieve(self, card, conv, recent):
        latest = recent[-1]['content'] if recent else ''
        recall = bool(re.search(r'记得|上次|之前|那件|那个|那家|后来', latest))
        query = '\n'.join(x['content'] for x in recent[-4:])[-5000:] if recall else latest
        candidates = []
        memories = [] if conv['trial'] else self.store.memories(card['id'])
        core = [m for m in memories if m['kind'] in ('boundary', 'relationship')]
        for m in memories:
            if m['kind'] not in ('boundary','relationship'):
                candidates.append(dict(id='m:'+m['id'], text=m['text'], kind=m['kind'], time=m['updated'], source_ids=json.loads(m['source_ids'])))
        # Section-based card chunks keep provenance; large sections are split into paragraphs.
        # Calibration dialogues are examples, not facts available for retrieval.
        details = re.sub(r'(?ms)^## (?:0\.|15\.|16\.|17\.).*?(?=^## |\Z)', '', card['details'])
        for i, section in enumerate(re.split(r'(?m)(?=^#{2,3} )', details)):
            for j in range(0, len(section), 1800):
                if section[j:j+1800].strip():
                    candidates.append(dict(id=f'p:{i}:{j}', kind='persona', text=section[j:j+1800], time=''))
        if not conv['trial']:
            with self.store.db() as db:
                old = db.execute("SELECT m.id,m.content,m.created FROM messages m JOIN conversations c ON c.id=m.conversation_id WHERE c.card_id=? AND c.trial=0 AND m.role='user' AND m.status='ok' AND m.forgotten=0 ORDER BY m.id DESC LIMIT 1000", (card['id'],)).fetchall()
            current_ids = {m['id'] for m in recent}
            for m in old:
                if m['id'] not in current_ids:
                    candidates.append(dict(id='h:'+str(m['id']), kind='history', text=m['content'], time=m['created'], source_ids=[m['id']]))
        for c in candidates:
            c['score'] = round(relevant(query, c['text']), 3)
        # Small personal memory stores are cheap to inspect semantically. A strict
        # lexical threshold missed paraphrases such as '周末想干什么来着'.
        memory_candidates = sorted((c for c in candidates if c['id'].startswith('m:')), key=lambda c:c['score'], reverse=True)[:20]
        persona_candidates = sorted((c for c in candidates if c['kind']=='persona' and c['score']>=0.25), key=lambda c:c['score'], reverse=True)[:2]
        historical = sorted((c for c in candidates if c['kind']=='history' and c['score']>=0.18), key=lambda c:c['score'], reverse=True)[:4] if recall else []
        candidates = memory_candidates + persona_candidates + historical
        # Vague recall requests need a chronological fallback when lexical overlap is absent.
        if not candidates and not conv['trial'] and recall:
            candidates = [dict(id='m:'+m['id'], kind=m['kind'], text=m['text'], time=m['updated'], score=0) for m in memories[:16]]
        latest = recent[-1]['content'] if recent else ''
        simple = re.sub(r'[\s，。！？!?,~～]', '', latest) in ('嗯','哦','好','好的','行','晚安','谢谢','知道了')
        selected = [] if simple else candidates[:6]
        mode, warning = ('skip' if simple else 'local'), ''
        selection_enabled = self.store.setting('selection_enabled') is not False
        if not simple and selection_enabled and candidates and (memory_candidates or len(candidates)>6 or recall):
            try:
                result = self.structured('select', dict(query=latest, recent=[dict(role=m['role'],content=m['content']) for m in recent[-6:]], candidates=candidates), 700)
                ids = result.get('ids')
                allowed = {c['id']:c for c in candidates}
                if not isinstance(ids,list) or len(ids)>8 or any(not isinstance(i,str) or i not in allowed for i in ids):
                    raise ValueError('精选结果引用了不存在的信息')
                selected = [allowed[i] for i in dict.fromkeys(ids)]
                mode = 'model'
            except (ValueError, DeepSeekError, TypeError):
                warning = '精选不可用，已使用本地检索结果'
        # Bounded factual data, never interpreted as higher-priority instructions.
        remaining, bounded = 7500, []
        memory_sources = {s for c in selected if c['id'].startswith('m:') for s in c.get('source_ids',[])}
        for c in selected:
            if c['kind']=='history' and memory_sources.intersection(c.get('source_ids',[])):
                continue
            if len(c['text']) <= remaining:
                bounded.append(c)
                remaining -= len(c['text'])
        return core, bounded, dict(mode=mode, warning=warning, candidates=candidates, selected=bounded)

    def reply(self, messages):
        candidates, checks = [], []
        candidate = self.call('chat', messages, 1400).strip()
        warning = ''
        for attempt in range(3):
            candidates.append(candidate)
            try:
                review = self.structured('quality', dict(
                    character_card=messages[0]['content'] if messages and messages[0]['role']=='system' else '',
                    context=[m['content'] for m in messages if m['role']=='system'],
                    history=[m for m in messages if m['role']!='system'], candidate=candidate), 450)
                if not isinstance(review.get('approved'),bool):
                    raise ValueError('质量检查格式不正确')
                checks.append(dict(approved=review['approved'], problems=str(review.get('problems',''))[:200]))
            except (ValueError,DeepSeekError,TypeError,AttributeError):
                warning='质量检查暂不可用，本轮使用原始回复'
                break
            if review['approved']:
                break
            if attempt < 2:
                feedback = dict(previous_candidate=candidate,problems=review.get('problems',''))
                candidate = self.call('chat', messages + [dict(role='system',content=texts()['local_quality_retry']+'\n'+json.dumps(feedback,ensure_ascii=False))],1400).strip()
        if len(checks)==3 and not checks[-1]['approved']:
            try:
                chosen=self.structured('quality_choice',dict(conversation=messages,candidates=candidates,checks=checks),100).get('selected')
                if not isinstance(chosen,int) or not 1<=chosen<=len(candidates):
                    raise ValueError('候选编号无效')
                candidate=candidates[chosen-1]
            except (ValueError,DeepSeekError,TypeError):
                pass
            warning='本轮仍有质量疑点，已选择候选回复；可查看调试信息'
        return candidate, dict(attempts=len(candidates),checks=checks,warning=warning)

    def chat(self, cid, content, request_id):
        content = clean(content, 6000)
        if not content:
            raise ValueError('消息不能为空')
        request_id = clean(request_id, 100)
        if not request_id:
            raise ValueError('缺少消息编号')
        if not self.api_key and not self.provider:
            raise ValueError('请先配置 DeepSeek API Key')
        lock = self.lock('chat:'+self.store.conversation(cid)['card_id'])
        if not lock.acquire(blocking=False):
            raise ValueError('这段对话正在生成回复，请稍候')
        try:
            conv = self.store.conversation(cid)
            card = self.store.card(conv['card_id'])
            with self.store.db() as db:
                existing = db.execute('SELECT * FROM messages WHERE request_id=?', (request_id,)).fetchone()
                if existing:
                    if existing['conversation_id'] != cid or existing['content'] != content:
                        raise ValueError('消息编号冲突')
                    reply = db.execute('SELECT * FROM messages WHERE request_id=?', (request_id+':reply',)).fetchone()
                    if reply:
                        return dict(message=dict(reply), debug=json.loads(reply['debug']))
                    user_id = existing['id']
                    db.execute("UPDATE messages SET status='pending' WHERE id=?", (user_id,))
                else:
                    row = db.execute("INSERT INTO messages(conversation_id,role,content,created,status,request_id) VALUES (?,?,?,?,?,?)", (cid,'user',content,now(),'pending',request_id))
                    user_id = row.lastrowid
            started = time.monotonic()
            try:
                # Select the chronological window first. Never backfill erased turns
                # with unrelated older messages or join dialogue across an erased gap.
                window = [m for m in self.store.messages(cid) if m['id'] < user_id][-19:]
                boundary = max((i for i,m in enumerate(window) if m['forgotten']), default=-1)
                recent = [m for m in window[boundary+1:] if m['status']=='ok']
                recent.append(dict(id=user_id, role='user',content=content,created=now()))
                # Preserve complete latest user message; reduce old input under a character budget.
                while len(recent)>1 and sum(len(m['content']) for m in recent)>18000:
                    recent.pop(0)
                profile_warning = ''
                try:
                    card, persona_facts, added = self.character_profile(card, content,
                        [dict(role=m['role'],content=m['content']) for m in recent], persist=not conv['trial'])
                except (ValueError, DeepSeekError, TypeError, AttributeError):
                    persona_facts, added = card['details'], 0
                    profile_warning = '背景补充暂不可用，本轮沿用已有档案'
                core, selected, debug = self.retrieve(card, conv, recent)
                debug.update(profile_added=added, profile_saved=bool(added and not conv['trial']), profile_warning=profile_warning)
                context = dict(persona_facts=persona_facts, relationship=card['relationship'], important_memories=[dict(kind=m['kind'],text=m['text']) for m in core],
                               topic=conv['topic'], selected_information=selected, state=self.runtime_state(card))
                data = dict(name=card['name'], gender=card['gender'], style=card.get('style',''), chat_rules=card['rules'], context=context)
                messages = [dict(role='system', content=card['core']+'\n\n'+texts()['local_chat']+'\n'+json.dumps(data,ensure_ascii=False))]
                messages += [dict(role=m['role'],content=m['content']) for m in recent]
                answer, quality = self.reply(messages)
                if not answer or len(answer)>16000:
                    raise ValueError('模型没有返回有效回复，请重试')
                debug.update(seconds=round(time.monotonic()-started,2), recent_count=len(recent), input_chars=sum(len(m['content']) for m in messages), card_version=card['version'], time=context['state']['local_time'], quality=quality)
                with self.store.db() as db:
                    live = db.execute('SELECT epoch FROM cards WHERE id=?', (card['id'],)).fetchone()
                    if not live or live['epoch'] != card['epoch']:
                        raise ValueError('生成期间设定或记忆发生变化，请重试')
                    db.execute("UPDATE messages SET status='ok' WHERE id=?", (user_id,))
                    row = db.execute('INSERT INTO messages(conversation_id,role,content,created,request_id,debug) VALUES (?,?,?,?,?,?)',
                                     (cid,'assistant',answer,now(),request_id+':reply',json.dumps(debug,ensure_ascii=False)))
                    mid = row.lastrowid
                    if not conv['trial']:
                        db.execute('INSERT OR IGNORE INTO jobs(id,conversation_id,upto,created) VALUES (?,?,?,?)', (uid(),cid,mid,now()))
                    if conv['title'] == '新的对话':
                        db.execute('UPDATE conversations SET title=? WHERE id=?', (content[:24],cid))
                return dict(message=dict(id=mid, role='assistant',content=answer,created=now(),status='ok'), debug=debug)
            except Exception:
                with self.store.db() as db:
                    db.execute("UPDATE messages SET status='failed' WHERE id=? AND status='pending'", (user_id,))
                raise
        finally:
            lock.release()

    def process_job(self):
        if not self.api_key and not self.provider:
            return False
        with self.store.db() as db:
            job = db.execute("SELECT * FROM jobs WHERE status='pending' ORDER BY created LIMIT 1").fetchone()
            if not job:
                return False
            job = dict(job)
            db.execute("UPDATE jobs SET status='running',attempts=attempts+1 WHERE id=?", (job['id'],))
        try:
            conv = self.store.conversation(job['conversation_id'])
            card = self.store.card(conv['card_id'])
            with self.store.db() as db:
                batch = [dict(r) for r in db.execute("SELECT id,role,content,created FROM messages WHERE conversation_id=? AND id>? AND id<=? AND status='ok' AND forgotten=0 ORDER BY id", (conv['id'],conv['cursor'],job['upto']))]
            if not batch or conv['trial']:
                with self.store.db() as db:
                    db.execute("UPDATE jobs SET status='done' WHERE id=?", (job['id'],))
                return True
            existing = self.store.memories(card['id'])
            result = self.structured('extract', dict(messages=batch, existing_memories=existing[:100], previous_topic=conv['topic'], persona=card['core'][:4000], previous_mood=card['mood']), 2200)
            operations = result.get('operations', [])
            if not isinstance(operations,list) or len(operations)>12:
                raise ValueError('记忆整理返回格式不正确')
            allowed_sources = {m['id'] for m in batch if m['role']=='user'}
            replacement_sources = {s for op in operations if isinstance(op,dict) and op.get('action')=='upsert' for s in op.get('source_ids',[]) if isinstance(s,int)}
            with self.store.db() as db:
                live = db.execute('SELECT epoch FROM cards WHERE id=?', (card['id'],)).fetchone()
                if not live or live['epoch'] != card['epoch']:
                    db.execute("UPDATE jobs SET status='pending' WHERE id=?", (job['id'],))
                    return True
                for op in operations:
                    if not isinstance(op,dict):
                        raise ValueError('无效记忆操作')
                    sources = op.get('source_ids',[])
                    if not isinstance(sources,list) or not sources or not all(isinstance(x,int) and x in allowed_sources for x in sources):
                        raise ValueError('记忆缺少本轮用户证据')
                    if op.get('action') == 'delete':
                        old = db.execute('SELECT * FROM memories WHERE id=? AND card_id=?', (op.get('id',''),card['id'])).fetchone()
                        if old:
                            self.store._forget_sources(db,old['source_ids'])
                            # Do not relearn forgotten content from the deletion request itself.
                            self.store._forget_sources(db,json.dumps([s for s in sources if s not in replacement_sources]))
                            db.execute('DELETE FROM memories WHERE id=?', (old['id'],))
                            self.store._invalidate(db,card['id'],old['id'])
                    elif op.get('action') == 'upsert':
                        kind = op.get('kind')
                        if kind not in ('fact','preference','boundary','relationship','event'):
                            raise ValueError('无效记忆类型')
                        key, value = clean(op.get('key'),160), clean(op.get('text'),1500)
                        if not key or not value:
                            raise ValueError('记忆为空')
                        old = db.execute('SELECT * FROM memories WHERE card_id=? AND key=?', (card['id'],key)).fetchone()
                        if old:
                            # Old evidence is invalidated on correction; current evidence remains usable.
                            old_ids = set(json.loads(old['source_ids'])) - set(sources)
                            self.store._forget_sources(db,json.dumps(list(old_ids)))
                            db.execute('UPDATE memories SET text=?,kind=?,source_ids=?,updated=? WHERE id=?', (value,kind,json.dumps(sources),now(),old['id']))
                        else:
                            db.execute('INSERT INTO memories VALUES (?,?,?,?,?,?,?,?)', (uid(),card['id'],key,kind,value,json.dumps(sources),now(),now()))
                    else:
                        raise ValueError('无效记忆操作')
                deleted = any(op.get('action')=='delete' for op in operations)
                topic = '' if deleted else clean(result.get('topic') or '',1800)
                mood = '' if deleted else clean(result.get('mood') or '',100)
                db.execute('UPDATE conversations SET topic=?,cursor=? WHERE id=?', (topic,job['upto'],conv['id']))
                db.execute('UPDATE cards SET mood=?,mood_at=? WHERE id=?', (mood,now(),card['id']))
                db.execute("UPDATE jobs SET status='done',error='' WHERE id=?", (job['id'],))
        except Exception as exc:
            detail = str(exc)[:100] if isinstance(exc,ValueError) else type(exc).__name__
            with self.store.db() as db:
                db.execute("UPDATE jobs SET status=?,error=? WHERE id=?", ('failed' if job['attempts']>=2 else 'pending','记忆整理失败：'+detail+'；原始聊天已保存，可重试。',job['id']))
        return True

    def start_worker(self):
        def worker():
            while not self.stopping.wait(2):
                self.process_job()
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return thread

    def character_profile(self, card, query='', history=None, persist=True, full=False):
        result = self.structured('profile', dict(character_card={k:card[k] for k in
            ('name','gender','core','details','relationship')}, query=query, history=history or [],
            ensure_basics=full or '## 自动补充的虚构背景' not in card['details']), 3000)
        additions = result.get('additions')
        facts = result.get('relevant_facts')
        if (not isinstance(additions,list) or len(additions)>12 or
                any(not isinstance(x,str) or not x.strip() or len(x)>1500 for x in additions) or
                not isinstance(facts,str) or len(facts)>4000):
            raise ValueError('人物背景补充格式不正确')
        additions = list(dict.fromkeys(x.strip() for x in additions if x.strip() not in card['details']))
        if additions:
            details = card['details'] + '\n\n## 自动补充的虚构背景\n' + '\n'.join('- '+x for x in additions)
            if len(details)>60000:
                raise ValueError('人物背景已满，请先整理档案')
            card = self.store.update_card(card['id'], {**card,'details':details}) if persist else {**card,'details':details}
        return card, facts, len(additions)

    def character_style(self, body):
        card = validate_card(body)
        result = self.structured('style', dict(character_card=card), 1800)
        style = clean(result.get('style',''),6000)
        if not style:
            raise ValueError('没有生成有效的聊天风格，请重试')
        return dict(style=style)

    def designer(self, design_id=None, content=None):
        if not design_id:
            design_id = uid()
            result = dict(reply=texts()['local_designer_start'], options=json.loads(texts()['local_designer_options']), draft=None)
            history = [dict(role='assistant',content=result['reply'])]
            with self.store.db() as db:
                db.execute('INSERT INTO designs VALUES (?,?,?,?)', (design_id,json.dumps(history,ensure_ascii=False),'null',now()))
            return dict(id=design_id,history=history,**result)
        lock = self.lock('design:'+design_id)
        with lock:
            with self.store.db() as db:
                row = db.execute('SELECT * FROM designs WHERE id=?', (design_id,)).fetchone()
                if not row:
                    raise ValueError('定制会话不存在')
            history = json.loads(row['history'])
            if content is None:
                return dict(id=design_id,history=history,draft=json.loads(row['draft']),options=[])
            content = clean(content,4000)
            if not content:
                raise ValueError('请先填写回答')
            history.append(dict(role='user',content=content))
            if len(history)>61:
                raise ValueError('这份定制已达到30轮，请保存或重新开始')
            result = self.structured('designer',dict(history=history,current_draft=json.loads(row['draft']),template=dict(fields=list(validate_card(default_card()).keys()))),3500)
            reply = clean(result.get('reply',''),3000)
            draft = result.get('draft')
            if draft is not None:
                draft = validate_card(draft)
            else:
                draft = json.loads(row['draft'])
            options = result.get('options',[])
            if not isinstance(options,list):
                options=[]
            options = [clean(x,150) for x in options[:4] if isinstance(x,str)]
            history.append(dict(role='assistant',content=reply))
            with self.store.db() as db:
                db.execute('UPDATE designs SET history=?,draft=? WHERE id=?',(json.dumps(history,ensure_ascii=False),json.dumps(draft,ensure_ascii=False),design_id))
            return dict(id=design_id,history=history,draft=draft,reply=reply,options=options)

    def weather(self, body):
        if not body.get('enabled'):
            self.store.setting('weather',dict(enabled=False))
            self.weather_cache=None
            return None
        lat, lon = float(body['latitude']), float(body['longitude'])
        if not -90<=lat<=90 or not -180<=lon<=180:
            raise ValueError('经纬度不正确')
        city = clean(body.get('city',''),60)
        self.store.setting('weather',dict(enabled=True,latitude=lat,longitude=lon,city=city))
        url = 'https://api.open-meteo.com/v1/forecast?' + urlencode(dict(latitude=lat,longitude=lon,current='temperature_2m,weather_code',timezone='auto'))
        try:
            with urlopen(url,timeout=8) as response:
                data=json.load(response)
            self.weather_cache=dict(city=city,temperature=data['current']['temperature_2m'],weather_code=data['current']['weather_code'],observed_at=now())
        except Exception:
            self.weather_cache=dict(city=city,error='天气暂时不可用',observed_at=now())
        return self.weather_cache
