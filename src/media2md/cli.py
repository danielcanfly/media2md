from __future__ import annotations
import argparse, json, os, subprocess, sys
from pathlib import Path
from .bootstrap import VERSION, ensure_runtime, import_legacy, runtime_root, state_root

def runtime_command(argv):
 p=argparse.ArgumentParser(prog='media2md runtime'); s=p.add_subparsers(dest='cmd',required=True)
 s.add_parser('status'); s.add_parser('path'); x=s.add_parser('install'); x.add_argument('--force',action='store_true')
 x=s.add_parser('import'); x.add_argument('--from-project',required=True)
 a=p.parse_args(argv)
 if a.cmd=='status': print(json.dumps({'version':VERSION,'runtime_root':str(runtime_root()),'runtime_exists':runtime_root().is_dir(),'state_root':str(state_root()),'managed':True},indent=2)); return 0
 if a.cmd=='path': print(ensure_runtime()); return 0
 if a.cmd=='install': print(f'MEDIA2MD_RUNTIME_INSTALLED path={ensure_runtime(a.force)} version={VERSION}'); return 0
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
