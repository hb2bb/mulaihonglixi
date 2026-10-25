"""Compare distinct adult characters with identical conversation inputs."""
import argparse,json,sys,tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from companion.store import Store,default_card,uid
from companion.engine import Engine
from web_server import load_dotenv
PROFILES=[
 {'name':'岑野夏','gender':'女','core':None,'style':''},
 {'name':'林砚','gender':'男','core':'林砚，32岁男性，文物修复师。沉静寡言，认真稳重，不争口舌输赢。习惯先观察具体细节再表态。温柔是低调记住对方的需要，不热烈表白，不挖苦，不起昵称。高兴时简短肯定；别人难过时安静倾听，确实需要时给一个务实办法。对不公会坚定但平静地指出，不用脏话。日常一两句朴素短话，不卖弄文艺，不讲笑话，不用emoji和感叹号。不是冷漠或上级训话，有自己的立场。只做文字聊天，不编用户事实。','style':''},
 {'name':'许遥','gender':'女','core':'许遥，27岁女性，绘本编辑。温柔细腻，感受丰富，愿意展开自己的感受和看法，让对方知道自己为什么喜欢或在意某件事。喜欢语言的韵律，偶尔贴题的轻巧比喻；不端着文艺腔。日常常有两到四句，完整但口语，不刻意短句酷酷地收尾。高兴时热情分享感受；倾诉时耐心回应具体遭遇，不急着建议；分歧时先认真理解再温和表达不同意见。不是较劲或反击型，不称输赢、不打趣用户脆弱。可以偶尔emoji。保持自主与判断，不无条件附和。只直接发消息，不写旁白，不虚构用户事实。','style':''}]
LINES=['拖了好久的报名，今天终于交上去了','你夸夸我，不准敷衍','同事把我做的方案说成他自己的了','先别给建议，我只是想说说','好啦，我去忙，晚点聊']
def main():
 p=argparse.ArgumentParser();p.add_argument('--live',action='store_true');p.add_argument('--output',type=Path,required=True);p.add_argument('--repeats',type=int,default=1);a=p.parse_args()
 if not a.live:p.error('--live required for paid API calls')
 load_dotenv(Path('.env'))
 def run(item):
  profile,n=item
  with tempfile.TemporaryDirectory() as folder:
   store=Store(Path(folder)/'test.db');engine=Engine(store);base=default_card()
   fields={**base,**profile,'core':profile['core'] or base['core'],'details':'','rules':'','relationship':'双方熟悉，尚未建立恋爱关系。没有现实共同经历。'}
   card=store.create_card(fields);conv=store.create_conversation(card['id'],trial=True);rows=[]
   for line in LINES:
    r=engine.chat(conv['id'],line,uid());rows.append(dict(user=line,reply=r['message']['content'],quality=r['debug']['quality']))
   return dict(name=profile['name'],repeat=n,card=fields,turns=rows)
 with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(run,[(p,n+1) for n in range(a.repeats) for p in PROFILES]))
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps(results,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
