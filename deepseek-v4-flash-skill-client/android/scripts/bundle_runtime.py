"""Build an explicit public-source allowlist. Never walk the user's data tree."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT.parent
FILES = ['local_demo.py','deepseek_skill_client.py','web_server.py',
         'companion/__init__.py','companion/store.py','companion/engine.py',
         'companion/static/index.html','companion/static/app.js','companion/static/style.css']
SKILLS = ['cangzhou-chat-runtime/references/runtime-text.json',
          'cen-yexia-girlfriend/references/character-card.md',
          'cen-yexia-girlfriend/references/local-demo-core.md',
          'cen-yexia-girlfriend/references/persona-chat-template.md',
          'cen-yexia-girlfriend/references/local-demo-details.md']
def bundle():
    target = ROOT/'android/app/src/main/assets/runtime.zip'
    target.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(target,'w',ZIP_DEFLATED) as z:
        for name in FILES:
            z.write(ROOT/name,'client/'+name)
        for name in SKILLS:
            z.write(PROJECT/'skills'/name,'skills/'+name)
    with ZipFile(target) as z:
        assert len(z.namelist()) == len(FILES)+len(SKILLS)
        assert not any('.env' in n or '.sqlite' in n or 'relationship-memory' in n for n in z.namelist())
    print(f'Bundled {len(FILES)+len(SKILLS)} public runtime files; no keys, databases or user cards.')
    return target
if __name__=='__main__':bundle()
