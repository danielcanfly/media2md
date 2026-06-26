from pathlib import Path
import json, os, subprocess, sys, threading, zipfile
from media2md.bootstrap import ensure_runtime, runtime_root, state_root
from media2md import __version__

def test_version(): assert __version__=='0.9.1'
def test_clean_runtime(monkeypatch,tmp_path):
 monkeypatch.setenv('HOME',str(tmp_path)); root=ensure_runtime(force=True)
 assert (root/'scripts/media2md.py').is_file(); assert (root/'scripts/manage_creators.py').is_file(); assert (root/'scripts/manage_videos.py').is_file(); assert (root/'bin/media2md').is_file()
 assert (root/'config').is_symlink(); assert (root/'data').is_symlink()
 result=subprocess.run([sys.executable,str(root/'scripts/media2md.py'),'version'],cwd=root,capture_output=True,text=True)
 assert result.returncode==0 and '0.9.1' in result.stdout

def test_concurrent_runtime_bootstrap(monkeypatch,tmp_path):
 monkeypatch.setenv('HOME',str(tmp_path))
 results=[]; errors=[]
 def worker():
  try: results.append(ensure_runtime())
  except Exception as exc: errors.append(exc)
 threads=[threading.Thread(target=worker) for _ in range(4)]
 for thread in threads: thread.start()
 for thread in threads: thread.join()
 assert not errors
 assert len(results)==4
 root=results[0]
 assert all(item==root for item in results)
 assert (root/'.complete').is_file()
 assert (root/'config').is_symlink()
 assert (root/'data').is_symlink()

def test_command_path_prefers_active_venv_bins(monkeypatch, tmp_path):
 from media2md.bundle.scripts import media2md_paths
 venv_root=tmp_path/'venv'
 venv_bin=venv_root/'bin'
 path_bin=tmp_path/'path-bin'
 venv_bin.mkdir(parents=True)
 path_bin.mkdir(parents=True)
 local=venv_bin/'yt-dlp'
 global_bin=path_bin/'yt-dlp'
 local.write_text('#!/bin/sh\n',encoding='utf-8')
 global_bin.write_text('#!/bin/sh\n',encoding='utf-8')
 local.chmod(0o755)
 global_bin.chmod(0o755)
 monkeypatch.setenv('PATH',str(path_bin))
 monkeypatch.setenv('VIRTUAL_ENV',str(venv_root))
 monkeypatch.setattr(media2md_paths.sys,'prefix',str(venv_root))
 monkeypatch.setattr(media2md_paths.sys,'executable',str(venv_bin/'python'))
 assert media2md_paths.command_path('yt-dlp')==str(local)

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
