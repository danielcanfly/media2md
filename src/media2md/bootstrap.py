from __future__ import annotations
import json, os, shutil, stat, sys, time
from contextlib import contextmanager
from importlib import resources
from pathlib import Path
VERSION='0.9.1'
STATE_DIRS=('config','data','logs','workspace','markdown','downloads','transcripts')
LOCK_TIMEOUT_SECONDS=30.0
LOCK_STALE_SECONDS=300.0

def _data_home()->Path:
 if sys.platform=='darwin': return Path.home()/'Library'/'Application Support'/'media2md'
 if os.name=='nt': return Path(os.getenv('LOCALAPPDATA',Path.home()/'AppData'/'Local'))/'media2md'
 return Path(os.getenv('XDG_DATA_HOME',Path.home()/'.local'/'share'))/'media2md'
def _config_home()->Path:
 if sys.platform=='darwin': return Path.home()/'Library'/'Application Support'/'media2md-config'
 if os.name=='nt': return Path(os.getenv('APPDATA',Path.home()/'AppData'/'Roaming'))/'media2md'
 return Path(os.getenv('XDG_CONFIG_HOME',Path.home()/'.config'))/'media2md'
def managed_base()->Path: return _data_home()
def state_root()->Path: return managed_base()/'state'
def runtime_root()->Path: return managed_base()/'runtime'/VERSION

@contextmanager
def _runtime_lock():
 base=managed_base(); base.mkdir(parents=True,exist_ok=True)
 lock=base/'.runtime.lock'; deadline=time.monotonic()+LOCK_TIMEOUT_SECONDS
 while True:
  try:
   lock.mkdir()
   break
  except FileExistsError:
   try: stale=(time.time()-lock.stat().st_mtime)>LOCK_STALE_SECONDS
   except FileNotFoundError: continue
   if stale:
    shutil.rmtree(lock,ignore_errors=True)
    continue
   if time.monotonic()>=deadline: raise TimeoutError(f'timed out waiting for runtime lock: {lock}')
   time.sleep(0.05)
 try: yield
 finally: shutil.rmtree(lock,ignore_errors=True)

def _copy_tree(source, target:Path):
 target.mkdir(parents=True,exist_ok=True)
 for item in source.iterdir():
  dst=target/item.name
  if item.is_dir(): _copy_tree(item,dst)
  else:
   with item.open('rb') as src, dst.open('wb') as out: shutil.copyfileobj(src,out)

def _ensure_state():
 state=state_root(); state.mkdir(parents=True,exist_ok=True)
 for d in STATE_DIRS: (state/d).mkdir(parents=True,exist_ok=True)
 defaults=resources.files('media2md').joinpath('bundle/defaults')
 for item in defaults.iterdir():
  target=state/'config'/item.name
  if not target.exists():
   with item.open('rb') as src, target.open('wb') as out: shutil.copyfileobj(src,out)

def ensure_runtime(force:bool=False)->Path:
 root=runtime_root(); marker=root/'.complete'
 with _runtime_lock():
  if force and root.exists(): shutil.rmtree(root)
  if not marker.exists():
   if root.exists(): shutil.rmtree(root)
   root.mkdir(parents=True,exist_ok=True)
   _copy_tree(resources.files('media2md').joinpath('bundle'),root)
   for name in ('media2md','social2md'):
    p=root/'bin'/name
    if p.exists(): p.chmod(p.stat().st_mode|stat.S_IXUSR|stat.S_IXGRP|stat.S_IXOTH)
   for p in (root/'scripts').glob('*.py'): p.chmod(p.stat().st_mode|stat.S_IXUSR)
   marker.write_text(VERSION+'\n')
  _ensure_state(); state=state_root()
  for d in STATE_DIRS:
   target=root/d
   if target.is_symlink() or target.exists():
    if target.is_symlink() and target.resolve()==(state/d).resolve(): continue
    if target.is_dir() and not target.is_symlink():
     for child in target.iterdir():
      dst=state/d/child.name
      if not dst.exists(): shutil.move(str(child),str(dst))
     shutil.rmtree(target)
    else: target.unlink(missing_ok=True)
   try: target.symlink_to(state/d,target_is_directory=True)
   except FileExistsError:
    if not (target.is_symlink() and target.resolve()==(state/d).resolve()): raise
  registry=_config_home()/'project.json'; registry.parent.mkdir(parents=True,exist_ok=True)
  registry.write_text(json.dumps({'schema_version':2,'project_root':str(root),'managed_runtime':True,'version':VERSION},indent=2)+'\n')
  return root

def import_legacy(source:Path)->dict:
 source=source.expanduser().resolve(); ensure_runtime(); state=state_root(); copied=[]
 for d in STATE_DIRS:
  src=source/d
  if not src.exists(): continue
  dst=state/d; dst.mkdir(parents=True,exist_ok=True)
  for item in src.iterdir():
   target=dst/item.name
   if target.exists(): continue
   if item.is_dir(): shutil.copytree(item,target)
   else: shutil.copy2(item,target)
   copied.append(f'{d}/{item.name}')
 return {'source':str(source),'state_root':str(state),'copied':copied,'count':len(copied)}
