from pathlib import Path
import json, os, subprocess, sys, zipfile
from media2md.bootstrap import ensure_runtime, runtime_root, state_root
from media2md import __version__

def test_version(): assert __version__=='0.9.1'
def test_clean_runtime(monkeypatch,tmp_path):
 monkeypatch.setenv('HOME',str(tmp_path)); root=ensure_runtime(force=True)
 assert (root/'scripts/media2md.py').is_file(); assert (root/'scripts/manage_creators.py').is_file(); assert (root/'scripts/manage_videos.py').is_file(); assert (root/'bin/media2md').is_file()
 assert (root/'config').is_symlink(); assert (root/'data').is_symlink()
 result=subprocess.run([sys.executable,str(root/'scripts/media2md.py'),'version'],cwd=root,capture_output=True,text=True)
 assert result.returncode==0 and '0.9.1' in result.stdout

def test_no_sensitive_bundle():
 root=Path(__file__).parents[1]/'src/media2md/bundle'
 forbidden={'instagram-cookies.txt','tiktok-cookies.txt','auth_profiles.json'}
 files={p.name for p in root.rglob('*') if p.is_file() and 'defaults' not in p.parts}
 assert not forbidden.intersection(files)

def test_safe_updater_present():
 text=(Path(__file__).parents[1]/'src/media2md/bundle/scripts/media2md_update.py').read_text()
 assert '_safe_extract' in text and 'Unsafe path in update archive' in text and 'no verifiable SHA-256' in text

def test_agent_skill_current():
 text=(Path(__file__).parents[1]/'src/media2md/bundle/openclaw/SKILL.md').read_text()
 assert 'auth connect <provider>' in text and 'auth login youtube' not in text

def test_all_platform_auth_contract():
 text=(Path(__file__).parents[1]/'src/media2md/bundle/scripts/media2md_auth.py').read_text()
 for p in ('instagram','youtube','tiktok'): assert p in text
 assert 'automatic_password_login=false' in text
