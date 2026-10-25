import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from companion.store import ROOT, Store, default_card, texts, uid
from companion.engine import Engine


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'test.sqlite3'
        self.store=Store(self.path)
        self.a=self.store.snapshot()['cards'][0]
        self.ca=self.store.snapshot()['conversations'][0]
        self.calls=[]
        self.result={"operations":[],"topic":"","mood":"平和"}
        def provider(purpose,messages):
            self.calls.append((purpose,messages))
            if purpose=='profile':return json.dumps({'additions':[], 'relevant_facts':''})
            if purpose=='chat':return '记住啦。'
            if purpose=='quality':return '{"approved":true,"problems":""}'
            if purpose=='extract':return json.dumps(self.result)
            if purpose=='select':return json.dumps({'ids':[]})
            if purpose=='designer':return json.dumps({'reply':'草稿已生成','options':[],'draft':default_card()})
        self.engine=Engine(self.store,provider)
    def tearDown(self):self.tmp.cleanup()
    def chat(self,text='我喜欢骑车',cid=None,rid=None):
        return self.engine.chat(cid or self.ca['id'],text,rid or uid())
    def test_profile_persists_versions_and_isolates_cards(self):
        other=self.store.create_card({**default_card(),'name':'另一个人'})
        self.engine.provider=lambda p,m: json.dumps({'additions':['工作城市：杭州。'], 'relevant_facts':'工作城市：杭州。'})
        card,facts,count=self.engine.character_profile(self.a)
        self.assertEqual(count,1)
        self.assertIn('工作城市：杭州。',Store(self.path).card(card['id'])['details'])
        self.assertEqual(card['version'],self.a['version']+1)
        self.assertEqual(self.store.card(other['id'])['details'],other['details'])
        again,_,count=self.engine.character_profile(card)
        self.assertEqual(count,0)
        self.assertEqual(again['version'],card['version'])
        with self.assertRaises(ValueError):self.engine.character_profile(self.a)

    def test_profile_trial_and_invalid_result_do_not_write(self):
        self.engine.provider=lambda p,m: json.dumps({'additions':['工作城市：杭州。'], 'relevant_facts':'杭州'})
        preview,_,_=self.engine.character_profile(self.a,persist=False)
        self.assertIn('工作城市：杭州。',preview['details'])
        self.assertEqual(self.store.card(self.a['id'])['details'],self.a['details'])
        self.engine.provider=lambda p,m: json.dumps({'additions':'wrong', 'relevant_facts':'杭州'})
        with self.assertRaises(ValueError):self.engine.character_profile(self.a)
        self.assertEqual(self.store.card(self.a['id'])['version'],self.a['version'])

    def test_persistence_and_isolation(self):
        self.store.edit_memory(self.a['id'],dict(kind='preference',text='喜欢山地骑行'))
        b=self.store.create_card({**default_card(),'name':'新人物'})
        cb=next(c for c in self.store.snapshot()['conversations'] if c['card_id']==b['id'])
        self.chat('你记得我喜欢什么吗',cb['id'])
        prompt=str([x for x in self.calls if x[0]=='chat'][-1])
        self.assertNotIn('喜欢山地骑行',prompt)
        self.assertEqual(Store(self.path).memories(self.a['id'])[0]['text'],'喜欢山地骑行')
        self.assertEqual(self.store.memories(b['id']),[])
    def test_twenty_messages_and_idempotent_retry(self):
        for n in range(12):self.chat('消息'+str(n))
        call=[x for x in self.calls if x[0]=='chat'][-1][1]
        self.assertEqual(len([m for m in call if m['role']!='system']),20)
        rid=uid();self.chat('单次请求',rid=rid);before=len(self.calls);self.chat('单次请求',rid=rid)
        self.assertEqual(before,len(self.calls))
        with self.assertRaises(ValueError):self.chat('另一条',rid=rid)
    def test_evidence_and_delete_no_resurrection(self):
        self.chat('我喜欢蓝莓冰淇淋')
        source=self.store.messages(self.ca['id'])[0]['id']
        self.result=dict(operations=[dict(action='upsert',key='ice',kind='preference',text='喜欢蓝莓冰淇淋',source_ids=[source])],topic='甜点',mood='开心')
        self.engine.process_job()
        memory=self.store.memories(self.a['id'])[0]
        self.store.delete_memory(self.a['id'],memory['id'])
        self.chat('记得我喜欢什么吗')
        prompt=[x for x in self.calls if x[0]=='chat'][-1][1]
        self.assertNotIn('蓝莓冰淇淋',str(prompt))
        self.assertEqual(self.store.memories(self.a['id']),[])
    def test_reject_assistant_evidence(self):
        self.chat()
        assistant=self.store.messages(self.ca['id'])[-1]['id']
        self.result=dict(operations=[dict(action='upsert',key='bad',kind='fact',text='虚构事实',source_ids=[assistant])])
        self.engine.process_job()
        self.assertEqual(self.store.memories(self.a['id']),[])
        self.assertEqual(self.store.snapshot()['jobs'][0]['status'],'pending')
    def test_trial_isolation(self):
        self.store.edit_memory(self.a['id'],dict(text='专属秘密记忆'))
        trial=self.store.create_conversation(self.a['id'],trial=True)
        self.chat('记得我的秘密吗',trial['id'])
        self.assertNotIn('专属秘密记忆',str(self.calls))
        self.assertEqual(self.store.snapshot()['jobs'],[])
    def test_card_version_conflict(self):
        a=self.store.update_card(self.a['id'],{**self.a,'name':'新名字'})
        self.assertEqual(a['version'],2)
        with self.assertRaises(ValueError):self.store.update_card(self.a['id'],self.a)
    def test_export_import_is_atomic_and_isolated(self):
        self.chat();self.store.edit_memory(self.a['id'],dict(text='记忆'))
        backup=self.store.export()
        self.assertNotIn('api_key',json.dumps(backup))
        self.assertEqual(self.store.import_data(backup),1)
        self.assertEqual(len(self.store.snapshot()['cards']),2)
        broken=json.loads(json.dumps(backup));broken['tables']['messages'][0]['conversation_id']='missing'
        with self.assertRaises(KeyError):self.store.import_data(broken)
        self.assertEqual(len(self.store.snapshot()['cards']),2)
    def test_designer_persists_without_memory(self):
        design=self.engine.designer()
        result=self.engine.designer(design['id'],'活泼一点')
        self.assertEqual(result['draft']['name'],'岑野夏')
        self.assertEqual(len(self.engine.designer(design['id'])['history']),3)
        self.assertEqual(self.store.memories(self.a['id']),[])
    def test_selector_unknown_ids_falls_back(self):
        self.store.edit_memory(self.a['id'],dict(text='上次约好骑车'))
        original=self.engine.provider
        def provider(purpose,messages):
            if purpose=='select':return '{"ids":["foreign-memory"]}'
            return original(purpose,messages)
        self.engine.provider=provider
        result=self.chat('上次约好的骑车你记得吗')
        self.assertEqual(result['debug']['mode'],'local')
        self.assertTrue(result['debug']['warning'])
    def test_failed_send_retries_without_duplicates(self):
        original=self.engine.provider
        self.engine.provider=lambda *args: (_ for _ in ()).throw(ValueError('offline'))
        rid=uid()
        with self.assertRaises(ValueError):self.chat('测试重试',rid=rid)
        self.engine.provider=original;self.chat('测试重试',rid=rid)
        self.assertEqual(len(self.store.messages(self.ca['id'])),2)
    def test_delete_conversation_drops_source_memory(self):
        self.chat();source=self.store.messages(self.ca['id'])[0]['id']
        self.result=dict(operations=[dict(action='upsert',key='cycling',kind='preference',text='喜欢骑车',source_ids=[source])])
        self.engine.process_job();self.store.delete_conversation(self.ca['id'])
        self.assertEqual(self.store.memories(self.a['id']),[])
    def test_reset_blocks_pending_extraction(self):
        self.chat()
        with self.store.db() as db:
            db.execute('UPDATE messages SET forgotten=1')
            self.store._invalidate(db,self.a['id'])
        self.engine.process_job()
        self.assertEqual(self.store.snapshot()['jobs'],[])

    def test_memory_add_does_not_remove_recent_dialogue(self):
        self.chat('你好')
        self.store.edit_memory(self.a['id'],dict(text='喜欢茶'))
        self.assertTrue(all(not m['forgotten'] for m in self.store.messages(self.ca['id'])))

    def test_erased_gap_never_backfills_old_message(self):
        self.chat('发错啦，你最近咋样')
        self.chat('你是谁')
        with self.store.db() as db:
            db.execute('UPDATE messages SET forgotten=1 WHERE id=(SELECT MAX(id) FROM messages)')
        result=self.chat('我喝多了')
        prompt=[x for x in self.calls if x[0]=='chat'][-1][1]
        self.assertEqual(result['debug']['recent_count'],1)
        self.assertNotIn('发错啦',str(prompt))
        self.assertFalse(any('15.9' in x['text'] or '15.6' in x['text'] for x in result['debug']['candidates']))

    def test_gender_roundtrip_and_copy(self):
        male=self.store.create_card({**default_card(),'name':'林川','gender':'男','core':'林川，28岁男性建筑师。'})
        self.assertEqual(self.store.card(male['id'])['gender'],'男')
        self.store.import_data(self.store.export())
        self.assertEqual(len([c for c in self.store.snapshot()['cards'] if c['name']=='林川' and c['gender']=='男']),2)

    def test_emoji_roundtrip(self):
        self.chat('今天真开心 😊')
        self.assertEqual(self.store.messages(self.ca['id'])[0]['content'],'今天真开心 😊')

    def test_quality_retries_with_feedback(self):
        original=self.engine.provider
        counts={'review':0}
        def provider(purpose,messages):
            if purpose=='quality':
                counts['review']+=1
                return json.dumps(dict(approved=counts['review']>1,problems='虚构近况' if counts['review']==1 else ''))
            return original(purpose,messages)
        self.engine.provider=provider
        r=self.chat('你最近如何')
        self.assertEqual(r['debug']['quality']['attempts'],2)

    def test_default_upgrade_preserves_history_and_memory(self):
        old=(ROOT/'skills/cen-yexia-girlfriend/references/local-demo-core.md').read_text().strip()
        self.store.update_card(self.a['id'],{**self.a,'core':old})
        self.chat('保留这段聊天')
        self.store.edit_memory(self.a['id'],dict(kind='preference',text='喜欢雨声'))
        before=self.store.messages(self.ca['id'])
        reopened=Store(self.path)
        self.assertEqual(reopened.card(self.a['id'])['core'],default_card()['core'])
        self.assertEqual(reopened.messages(self.ca['id']),before)
        self.assertEqual(reopened.memories(self.a['id'])[0]['text'],'喜欢雨声')
        with reopened.db() as db:
            saved=[json.loads(r['data']) for r in db.execute('SELECT data FROM versions WHERE card_id=?',(self.a['id'],))]
        self.assertTrue(any(c['core']==old for c in saved))

    def test_custom_core_is_not_replaced_on_startup(self):
        self.store.update_card(self.a['id'],{**self.a,'core':'用户自定义的人物设定'})
        self.assertEqual(Store(self.path).card(self.a['id'])['core'],'用户自定义的人物设定')

    def test_reasoned_review_has_budget_for_visible_json(self):
        engine=Engine(self.store)
        engine.api_key='test-only'
        with patch('companion.engine.DeepSeekSkillClient') as client:
            client.return_value.complete.return_value='{"approved":true,"problems":""}'
            self.assertTrue(engine.structured('quality',{'candidate':'你好'},450)['approved'])
            self.assertTrue(client.call_args.kwargs['thinking'])
            self.assertGreater(client.return_value.complete.call_args.kwargs['max_tokens'],450)

    def test_style_survives_reload_and_backup(self):
        self.store.update_card(self.a['id'],{**self.a,'style':'细腻健谈，以完整几句表达感受'})
        reopened=Store(self.path)
        self.assertEqual(reopened.card(self.a['id'])['style'],'细腻健谈，以完整几句表达感受')
        reopened.import_data(reopened.export())
        self.assertEqual(len([c for c in reopened.snapshot()['cards'] if c['style']=='细腻健谈，以完整几句表达感受']),2)

    def test_style_is_isolated_in_generation_and_review(self):
        quiet=self.store.create_card({**default_card(),'name':'林砚','gender':'男','core':'林砚，成年男性，修复师。','style':'平静克制，不用emoji'})
        cid=self.store.create_conversation(quiet['id'])['id']
        self.chat('今天还不错',cid)
        for purpose,messages in self.calls:
            if purpose in ('chat','quality'):
                content=str(messages)
                self.assertIn('平静克制',content)
                self.assertNotIn('岑野夏',content)

    def test_legacy_generic_rules_migrate_without_overwriting_custom_rules(self):
        self.store.update_card(self.a['id'],{**self.a,'rules':texts()['local_legacy_rules'],'style':'独立风格'})
        other=self.store.create_card({**default_card(),'name':'自定义','rules':'用户自定义规则'})
        reopened=Store(self.path)
        self.assertEqual(reopened.card(self.a['id'])['rules'],texts()['local_rules'])
        self.assertEqual(reopened.card(self.a['id'])['style'],'独立风格')
        self.assertEqual(reopened.card(other['id'])['rules'],'用户自定义规则')

    def test_style_generation_previews_unsaved_card_without_persisting(self):
        before=self.store.card(self.a['id'])
        captured=[]
        def provider(purpose,messages):
            captured.append(json.loads(messages[-1]['content']))
            return json.dumps({'style':'少说、朴素，不用emoji'})
        engine=Engine(self.store,provider)
        preview=engine.character_style({**before,'core':'尚未保存的成年修复师人格'})
        self.assertEqual(preview['style'],'少说、朴素，不用emoji')
        self.assertEqual(captured[0]['character_card']['core'],'尚未保存的成年修复师人格')
        self.assertNotIn('history',captured[0])
        self.assertEqual(self.store.card(self.a['id']),before)

    def test_invalid_generated_style_keeps_saved_data(self):
        before=self.store.card(self.a['id'])
        engine=Engine(self.store,lambda *_:'{"style":null}')
        with self.assertRaises(ValueError):engine.character_style(before)
        self.assertEqual(self.store.card(self.a['id']),before)

if __name__=='__main__':unittest.main()
