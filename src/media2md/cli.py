from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys
from pathlib import Path
from .bootstrap import VERSION, ensure_runtime, import_legacy, managed_base, runtime_root, state_root

def _registry_path() -> Path:
 return Path.home()/'Library'/'Application Support'/'media2md-config'/'project.json' if sys.platform=='darwin' else (Path(os.getenv('APPDATA',Path.home()/'.config'))/'media2md'/'project.json' if os.name=='nt' else Path(os.getenv('XDG_CONFIG_HOME',Path.home()/'.config'))/'media2md'/'project.json')

def _write_registry(payload: dict) -> None:
 registry = _registry_path()
 registry.parent.mkdir(parents=True, exist_ok=True)
 registry.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')

def _migrate_managed_base(current: Path, target: Path) -> tuple[Path, bool]:
 current = current.resolve()
 target = target.resolve()
 if current == target:
  return current, False
 if target.exists() and any(target.iterdir()):
  raise RuntimeError(f'target base path is not empty: {target}')
 target.parent.mkdir(parents=True, exist_ok=True)
 shutil.move(str(current), str(target))
 return target, True

def runtime_command(argv):
 p=argparse.ArgumentParser(prog='media2md runtime'); s=p.add_subparsers(dest='cmd',required=True)
 s.add_parser('status'); s.add_parser('path'); s.add_parser('base-path'); x=s.add_parser('install'); x.add_argument('--force',action='store_true')
 x=s.add_parser('import'); x.add_argument('--from-project',required=True)
 x=s.add_parser('set-base-path'); x.add_argument('path')
 a=p.parse_args(argv)
 if a.cmd=='status': print(json.dumps({'version':VERSION,'managed_base':str(managed_base()),'runtime_root':str(runtime_root()),'runtime_exists':runtime_root().is_dir(),'state_root':str(state_root()),'managed':True},indent=2)); return 0
 if a.cmd=='path': print(ensure_runtime()); return 0
 if a.cmd=='base-path': print(managed_base()); return 0
 if a.cmd=='install': print(f'MEDIA2MD_RUNTIME_INSTALLED path={ensure_runtime(a.force)} version={VERSION}'); return 0
 if a.cmd=='set-base-path':
  target=Path(a.path).expanduser().resolve()
  current_base=managed_base()
  moved=False
  if current_base.exists():
   target,moved=_migrate_managed_base(current_base,target)
  else:
   target.mkdir(parents=True, exist_ok=True)
  current_runtime=runtime_root()
  payload={'schema_version':3,'project_root':str(target/'runtime'/VERSION),'managed_runtime':True,'version':VERSION,'managed_base':str(target)}
  _write_registry(payload)
  print(f'MEDIA2MD_BASE_PATH_SET path={target}')
  print(f'previous_runtime_root={current_runtime}')
  print(f'migrated={str(moved).lower()}')
  return 0
 print(json.dumps(import_legacy(Path(a.from_project)),indent=2)); return 0

def main()->int:
 argv=sys.argv[1:]
 if argv and argv[0]=='runtime': return runtime_command(argv[1:])
 if argv in (['--version'],['version']): print(f'media2md {VERSION}'); return 0
 explicit=os.getenv('MEDIA2MD_PROJECT_ROOT')
 if explicit:
  candidate=Path(explicit).expanduser().resolve()
  script=candidate/'scripts'/'media2md.py'
  if script.is_file():
   env=os.environ.copy(); env['MEDIA2MD_PYTHON']=sys.executable
   return subprocess.call([sys.executable,str(script),*argv],cwd=candidate,env=env)
 root=ensure_runtime()
 env=os.environ.copy(); env['MEDIA2MD_PROJECT_ROOT']=str(root); env['MEDIA2MD_PYTHON']=sys.executable
 return subprocess.call([sys.executable,str(root/'scripts'/'media2md.py'),*argv],cwd=root,env=env)
if __name__=='__main__': raise SystemExit(main())
