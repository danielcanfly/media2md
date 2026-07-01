from __future__ import annotations
import json, os, shutil, stat, sys, time
from contextlib import contextmanager
from importlib import resources
from pathlib import Path
VERSION='0.9.5'
STATE_DIRS=('config','data','logs','workspace','markdown','downloads','transcripts')
LOCK_TIMEOUT_SECONDS=30.0
LOCK_STALE_SECONDS=300.0

def _default_managed_base()->Path:
 downloads = Path.home() / 'Downloads' / 'media2md'
 downloads.mkdir(parents=True, exist_ok=True)
 return downloads

def _legacy_data_home()->Path:
 if sys.platform=='darwin': return Path.home()/'Library'/'Application Support'/'media2md'
 if os.name=='nt': return Path(os.getenv('LOCALAPPDATA',Path.home()/'AppData'/'Local'))/'media2md'
 return Path(os.getenv('XDG_DATA_HOME',Path.home()/'.local'/'share'))/'media2md'

def _config_home()->Path:
 if sys.platform=='darwin': return Path.home()/'Library'/'Application Support'/'media2md-config'
 if os.name=='nt': return Path(os.getenv('APPDATA',Path.home()/'AppData'/'Roaming'))/'media2md'
 return Path(os.getenv('XDG_CONFIG_HOME',Path.home()/'.config'))/'media2md'

def _project_registry_path()->Path:
 return _config_home()/'project.json'

def _load_project_registry()->dict|None:
 registry = _project_registry_path()
 try: return json.loads(registry.read_text(encoding='utf-8'))
 except (FileNotFoundError, json.JSONDecodeError, OSError): return None

def managed_base()->Path:
 explicit=os.getenv('MEDIA2MD_HOME')
 if explicit:
  path=Path(explicit).expanduser().resolve()
  path.mkdir(parents=True,exist_ok=True)
  return path
 payload=_load_project_registry()
 stored=payload.get('managed_base') if isinstance(payload,dict) else None
 if stored:
  path=Path(str(stored)).expanduser().resolve()
  path.mkdir(parents=True,exist_ok=True)
  return path
 legacy=_legacy_data_home()
 if legacy.exists():
  legacy.mkdir(parents=True,exist_ok=True)
  return legacy
 return _default_managed_base()

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

def _project_registry_candidates()->list[Path]:
 seen=set(); rows=[]
 for path in (
  _config_home()/'project.json',
  Path.home()/'.config'/'media2md'/'project.json',
  Path.home()/'.config'/'social2md'/'project.json',
 ):
  key=str(path)
  if key in seen: continue
  seen.add(key); rows.append(path)
 return rows

def _legacy_project_root()->Path|None:
 for registry in _project_registry_candidates():
  try: payload=json.loads(registry.read_text(encoding='utf-8'))
  except (FileNotFoundError,json.JSONDecodeError,OSError): continue
  if payload.get('managed_runtime') is True: continue
  root=Path(str(payload.get('project_root') or '')).expanduser()
  if root.is_dir(): return root.resolve()
 return None

def _seed_state_from_legacy(state:Path)->list[str]:
 legacy=_legacy_project_root()
 if not legacy: return []
 copied=[]
 defaults=resources.files('media2md').joinpath('bundle/defaults')
 for rel in (
  'config/auth_profiles.json',
  'config/social2md.json',
  'config/creator_policies.json',
  'config/provider_policies.json',
 ):
  src=legacy/rel
  dst=state/rel
  if not src.is_file(): continue
  if dst.exists():
   default=defaults/Path(rel).name
   if not default.is_file() or dst.read_bytes()!=default.read_bytes(): continue
  dst.parent.mkdir(parents=True,exist_ok=True)
  shutil.copy2(src,dst)
  copied.append(rel)
 return copied

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
  _ensure_state(); state=state_root(); _seed_state_from_legacy(state)
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
  registry=_project_registry_path(); registry.parent.mkdir(parents=True,exist_ok=True)
  registry.write_text(json.dumps({'schema_version':3,'project_root':str(root),'managed_runtime':True,'version':VERSION,'managed_base':str(managed_base())},indent=2)+'\n')
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
