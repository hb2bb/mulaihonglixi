"""Real multi-turn integration evaluation; --live explicitly enables API calls."""
import argparse
import json
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from companion.store import Store,uid
from companion.engine import Engine
from web_server import load_dotenv

SCENARIOS={
 'daily':['发错啦，你最近咋样','我不是很了解你','你是谁？','你是真人吗？','我喝多了','我在家，朋友在旁边','嗯，先不聊了'],
 'boundaries':['我今天被领导批评了','先别分析，我只想说说','他当着同事说我的方案不行','不用替我骂他','嗯','我不喜欢你叫我冠军，叫我阿远就行','你应该怎么称呼我？'],
 'memory':['记住，我喜欢无糖乌龙茶。','周末我想去骑行，不过还没定去哪。','我更正一下，现在更喜欢柠檬水，乌龙茶不喝了。','以后聊我的饮料喜好时以刚才的更正为准。','@new','你记得我现在喜欢喝什么吗？','我周末想干什么来着？','忘掉我的饮料偏好吧。','@new','你知道我喜欢喝什么吗？']}

def scenario(name,lines):
 path=Path(tempfile.mkdtemp(prefix='qiyu-eval-'))/'eval.db'
 store=Store(path);engine=Engine(store);card=store.snapshot()['cards'][0];cid=store.snapshot()['conversations'][0]['id'];results=[]
 for line in lines:
  if line=='@new':
   store=Store(path);engine=Engine(store);cid=store.create_conversation(card['id'])['id'];continue
  try:
   r=engine.chat(cid,line,uid())
   for _ in range(12):
    if not engine.process_job():break
   item=dict(scenario=name,user=line,reply=r['message']['content'],recent_count=r['debug']['recent_count'],selected=[dict(id=c['id'],kind=c['kind'],text=c['text'][:200]) for c in r['debug']['selected']],seconds=r['debug']['seconds'],memories=[m['text'] for m in store.memories(card['id'])],quality=r['debug'].get('quality'),jobs=[dict(status=j['status'],error=j['error']) for j in store.snapshot()['jobs']])
  except Exception as exc:
   item=dict(scenario=name,user=line,error=type(exc).__name__,status=getattr(exc,'status_code',None))
  results.append(item);print(json.dumps(item,ensure_ascii=False),flush=True)
 return results

def main():
 p=argparse.ArgumentParser();p.add_argument('--live',action='store_true');p.add_argument('--output',default='evals/results/local-demo-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.json');a=p.parse_args()
 if not a.live: p.error('Use --live to explicitly enable paid API calls with synthetic data.')
 load_dotenv(Path(__file__).resolve().parents[1]/'.env')
 with ThreadPoolExecutor(max_workers=3) as pool: results=list(pool.map(lambda x:scenario(*x),SCENARIOS.items()))
 target=Path(a.output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(results,ensure_ascii=False,indent=2));print('REPORT',str(target.resolve()),flush=True)
if __name__=='__main__':main()
