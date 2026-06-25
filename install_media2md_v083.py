#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, re, shutil, sqlite3, subprocess, sys, time, zipfile
from datetime import datetime, timezone
from pathlib import Path
VERSION='0.8.3'
SOURCE=Path(__file__).resolve().parent
BUNDLE=SOURCE/'src'/'media2md'/'bundle'

def verify_source():
 init_file=SOURCE/'src'/'media2md'/'__init__.py'
 if not init_file.is_file():
  raise SystemExit(f'Invalid Media2MD source tree: missing {init_file}')
 text=init_file.read_text(encoding='utf-8')
 if VERSION not in text:
  raise SystemExit(f'Source version mismatch: expected {VERSION}')

def stamp(): return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

def purge_bytecode(root: Path) -> int:
 count=0
 if not root.exists(): return count
 for cache in sorted(root.rglob('__pycache__'), reverse=True):
  if cache.is_dir():
   shutil.rmtree(cache, ignore_errors=True); count += 1
 for pattern in ('*.pyc','*.pyo'):
  for item in root.rglob(pattern):
   try: item.unlink(); count += 1
   except FileNotFoundError: pass
 return count

def refresh_python_mtimes(root: Path) -> None:
 now=time.time()
 for base in (root/'scripts', root/'src'):
  if base.exists():
   for item in base.rglob('*.py'):
    os.utime(item, (now, now))

def source_version(path: Path) -> str | None:
 try: text=path.read_text(encoding='utf-8')
 except FileNotFoundError: return None
 match=re.search(r'^VERSION\s*=\s*["\']([^"\']+)', text, re.MULTILINE)
 return match.group(1) if match else None
def backup(target:Path)->Path|None:
 if not target.exists(): return None
 root=Path.home()/'.cache'/'media2md'/'updates'; root.mkdir(parents=True,exist_ok=True)
 archive=root/f'rollback-before-v083-{stamp()}.zip'
 with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
  for rel in ('scripts','bin','openclaw','src','pyproject.toml','README.md','LICENSE','CHANGELOG.md'):
   p=target/rel
   if p.is_dir():
    for f in p.rglob('*'):
     if f.is_file() and 'backups' not in f.parts: z.write(f,f.relative_to(target))
   elif p.is_file(): z.write(p,p.relative_to(target))
 return archive

def copytree_merge(src:Path,dst:Path):
 dst.mkdir(parents=True,exist_ok=True)
 for p in src.iterdir():
  t=dst/p.name
  if p.is_dir(): copytree_merge(p,t)
  else: shutil.copy2(p,t)


def repair_tiktok_exact_state(target: Path) -> int:
 db=target/'data'/'media2md.db'
 if not db.is_file(): return 0
 conn=sqlite3.connect(db)
 try:
  columns={row[1] for row in conn.execute("PRAGMA table_info(creators)").fetchall()}
  required={'provider','current_total','current_total_exact','last_full_exact_total','last_full_exact_at'}
  if not required.issubset(columns): return 0
  cursor=conn.execute(
   """UPDATE creators
      SET current_total_exact=1,updated_at=?
      WHERE provider='tiktok'
        AND current_total_exact=0
        AND last_full_exact_total IS NOT NULL
        AND last_full_exact_at IS NOT NULL
        AND current_total=last_full_exact_total""",
   (datetime.now(timezone.utc).isoformat(timespec='seconds'),),
  )
  conn.commit()
  return int(cursor.rowcount or 0)
 finally:
  conn.close()

def repair_known_regressions(target: Path) -> int:
 db=target/'data'/'state.db'
 if not db.is_file(): return 0
 conn=sqlite3.connect(db)
 try:
  cursor=conn.execute(
   """
   UPDATE videos
   SET status='pending',
       attempt_count=0,
       next_retry_at=NULL,
       last_error=NULL,
       updated_at=?
   WHERE last_error LIKE '%unrecognized arguments:%--cookies-file%'
      OR last_error LIKE '%process_worker.py%--cookies-file%'
   """,
   (datetime.now(timezone.utc).isoformat(timespec='seconds'),),
  )
  conn.commit()
  return int(cursor.rowcount or 0)
 finally:
  conn.close()

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--target',default='.'); ap.add_argument('--skip-pip',action='store_true'); a=ap.parse_args()
 verify_source()
 target=Path(a.target).expanduser().resolve(); target.mkdir(parents=True,exist_ok=True)
 rollback=backup(target)
 purged_before=purge_bytecode(target)
 copytree_merge(BUNDLE/'scripts',target/'scripts'); copytree_merge(BUNDLE/'bin',target/'bin'); copytree_merge(BUNDLE/'openclaw',target/'openclaw')
 for d in ('config','data','logs','workspace','markdown','downloads','transcripts'): (target/d).mkdir(parents=True,exist_ok=True)
 for f in (BUNDLE/'defaults').iterdir():
  t=target/'config'/f.name
  if not t.exists(): shutil.copy2(f,t)
 copytree_merge(SOURCE/'src',target/'src')
 for name in ('pyproject.toml','README.md','LICENSE','CHANGELOG.md','SECURITY.md','CONTRIBUTING.md','.gitignore'):
  if (SOURCE/name).is_file(): shutil.copy2(SOURCE/name,target/name)
 (target/'bin'/'media2md').write_text('#!/bin/sh\nset -eu\nROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)\nif [ -x "$ROOT/.venv/bin/python" ]; then PY="$ROOT/.venv/bin/python"; else PY="${PYTHON:-python3}"; fi\nexport MEDIA2MD_PROJECT_ROOT="$ROOT"\nexec "$PY" -B "$ROOT/scripts/media2md.py" "$@"\n')
 (target/'bin'/'social2md').write_text((target/'bin'/'media2md').read_text())
 for p in (target/'bin').iterdir(): p.chmod(0o755)
 for p in (target/'scripts').glob('*.py'): p.chmod(0o755)
 refresh_python_mtimes(target)
 purged_after_copy=purge_bytecode(target)
 for egg in (target/'src').glob('*.egg-info'):
  if egg.is_dir(): shutil.rmtree(egg, ignore_errors=True)
 pip_exit=None
 if not a.skip_pip:
  project_python=target/'.venv'/'bin'/'python'
  if not project_python.is_file():
   created=subprocess.run([sys.executable,'-m','venv',str(target/'.venv')],cwd=target,check=False)
   if created.returncode:
    raise SystemExit(f'virtual environment creation failed with exit code {created.returncode}')
  r=subprocess.run([str(project_python),'-m','pip','install','--upgrade','--force-reinstall','--no-deps','-e',str(target)],cwd=target,check=False); pip_exit=r.returncode
  if r.returncode: raise SystemExit(f'pip install failed with exit code {r.returncode}')
  purged_after_pip=purge_bytecode(target)
  refresh_python_mtimes(target)
  package_check=subprocess.run([str(project_python),'-c','import media2md; print(media2md.__version__)'],cwd=target,capture_output=True,text=True,check=False)
  cli_check=subprocess.run([str(target/'bin'/'media2md'),'version'],cwd=target,capture_output=True,text=True,check=False)
  script_version=source_version(target/'scripts'/'media2md.py')
  failures=[]
  if package_check.returncode or package_check.stdout.strip()!=VERSION:
   failures.append(f'package={package_check.stdout.strip() or package_check.stderr.strip()}')
  if cli_check.returncode or cli_check.stdout.strip()!=f'media2md {VERSION}':
   failures.append(f'cli={cli_check.stdout.strip() or cli_check.stderr.strip()}')
  if script_version!=VERSION:
   failures.append(f'script={script_version}')
  if failures:
   raise SystemExit('post-install version verification failed: '+', '.join(failures))
 repaired_instagram_items=repair_known_regressions(target)
 repaired_tiktok_exact=repair_tiktok_exact_state(target)
 registry=Path.home()/'.config'/'media2md'/'project.json'; registry.parent.mkdir(parents=True,exist_ok=True); registry.write_text(json.dumps({'schema_version':2,'project_root':str(target),'managed_runtime':False,'version':VERSION},indent=2)+'\n')
 print('MEDIA2MD_V083_INSTALLED'); print(f'version={VERSION}'); print(f'project_root={target}'); print(f'rollback_backup={rollback}'); print(f'pip_exit_code={pip_exit}'); print(f'bytecode_caches_removed={purged_before+purged_after_copy+(purged_after_pip if not a.skip_pip else 0)}'); print(f'instagram_contract_regression_items_requeued={repaired_instagram_items}'); print(f'tiktok_exact_state_repaired={repaired_tiktok_exact}'); print('data_preserved=config,data,logs,workspace,markdown,downloads,transcripts'); return 0
if __name__=='__main__': raise SystemExit(main())
