from pathlib import Path
import json, os, subprocess, sys, threading, zipfile
from media2md.bootstrap import ensure_runtime, managed_base, runtime_root, state_root
from media2md import __version__

def test_version(): assert __version__=='0.9.6'
def test_clean_runtime(monkeypatch,tmp_path):
 monkeypatch.setenv('HOME',str(tmp_path)); root=ensure_runtime(force=True)
 assert managed_base()==tmp_path/'Downloads'/'media2md'
 assert (root/'scripts/media2md.py').is_file(); assert (root/'scripts/manage_creators.py').is_file(); assert (root/'scripts/manage_videos.py').is_file(); assert (root/'bin/media2md').is_file()
 assert (root/'config').is_symlink(); assert (root/'data').is_symlink()
 result=subprocess.run([sys.executable,str(root/'scripts/media2md.py'),'version'],cwd=root,capture_output=True,text=True)
 assert result.returncode==0 and '0.9.6' in result.stdout

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

def test_build_excludes_local_virtualenvs():
 text=(Path(__file__).parents[1]/'pyproject.toml').read_text()
 for token in ('".venv*/**"','"venv*/**"','".audit-venv/**"'):
  assert token in text

def test_runtime_base_path_command(monkeypatch,tmp_path):
 monkeypatch.setenv('HOME',str(tmp_path))
 from media2md import cli
 assert cli.runtime_command(['base-path'])==0

def test_managed_runtime_generic_media_script_starts_without_src_pythonpath(monkeypatch,tmp_path):
 monkeypatch.setenv('HOME',str(tmp_path))
 root=ensure_runtime(force=True)
 env=os.environ.copy()
 env.pop('PYTHONPATH',None)
 env['HOME']=str(tmp_path)
 result=subprocess.run(
  [sys.executable,str(root/'scripts'/'generic_media.py'),'--help'],
  cwd=root,
  capture_output=True,
  text=True,
  env=env,
 )
 assert result.returncode==0, result.stderr or result.stdout
 assert 'usage:' in result.stdout.lower()

def test_managed_runtime_public_cli_script_starts_without_src_pythonpath(monkeypatch,tmp_path):
 monkeypatch.setenv('HOME',str(tmp_path))
 root=ensure_runtime(force=True)
 env=os.environ.copy()
 env.pop('PYTHONPATH',None)
 env['HOME']=str(tmp_path)
 result=subprocess.run(
  [sys.executable,str(root/'scripts'/'media2md.py'),'creator','status','--help'],
  cwd=root,
  capture_output=True,
  text=True,
  env=env,
 )
 assert result.returncode==0, result.stderr or result.stdout
 assert 'creator status' in result.stdout.lower()

def test_module_entrypoint_prefers_source_checkout_when_project_root_points_to_repo(monkeypatch, tmp_path):
 monkeypatch.setenv('HOME',str(tmp_path))
 root=Path(__file__).parents[1]
 env=os.environ.copy()
 env['PYTHONPATH']=str(root/'src')
 env['HOME']=str(tmp_path)
 env['MEDIA2MD_PROJECT_ROOT']=str(root)
 result=subprocess.run(
  [sys.executable,'-m','media2md.cli','creator','status','--provider','bilibili','--creator','1510588366','--help'],
  cwd=root,
  capture_output=True,
  text=True,
  env=env,
 )
 assert result.returncode==0, result.stderr or result.stdout
 assert '--provider {instagram,youtube,tiktok,bilibili}' in result.stdout

def test_runtime_set_base_path_migrates_existing_managed_tree(monkeypatch,tmp_path):
 monkeypatch.setenv('HOME',str(tmp_path))
 from media2md import cli
 root=ensure_runtime(force=True)
 marker=state_root()/'markdown'/'sample.txt'
 marker.parent.mkdir(parents=True,exist_ok=True)
 marker.write_text('ok',encoding='utf-8')
 target=tmp_path/'external-media2md'
 assert cli.runtime_command(['set-base-path',str(target)])==0
 payload=json.loads((tmp_path/'Library'/'Application Support'/'media2md-config'/'project.json').read_text())
 assert payload['managed_base']==str(target)
 assert (target/'state'/'markdown'/'sample.txt').read_text(encoding='utf-8')=='ok'
 assert not root.exists()

def test_uninstall_runs_pip_by_default(monkeypatch,tmp_path,capsys):
 monkeypatch.setenv('HOME',str(tmp_path))
 from media2md.bundle.scripts import media2md as public_cli
 calls=[]
 monkeypatch.setattr(public_cli, 'remove_openclaw_cron', lambda: (0, []))
 monkeypatch.setattr(public_cli, 'run', lambda cmd, check=False: calls.append(cmd) or 0)
 args=type('Args',(),{'purge_data':False,'yes':False,'confirm':None,'dry_run':False})()
 assert public_cli.uninstall(args)==0
 out=capsys.readouterr().out
 assert 'MEDIA2MD_UNINSTALL_PREPARED' in out
 assert 'package_uninstalled=true' in out
 assert calls and calls[0][-2:]==['media2md','social2md']

def test_uninstall_dry_run_does_not_remove_package(monkeypatch,tmp_path,capsys):
 monkeypatch.setenv('HOME',str(tmp_path))
 from media2md.bundle.scripts import media2md as public_cli
 calls=[]
 monkeypatch.setattr(public_cli, 'remove_openclaw_cron', lambda: (0, []))
 monkeypatch.setattr(public_cli, 'run', lambda cmd, check=False: calls.append(cmd) or 0)
 args=type('Args',(),{'purge_data':False,'yes':False,'confirm':None,'dry_run':True})()
 assert public_cli.uninstall(args)==0
 out=capsys.readouterr().out
 assert 'package_uninstalled=false' in out
 assert '--dry-run' not in out
 assert calls==[]
