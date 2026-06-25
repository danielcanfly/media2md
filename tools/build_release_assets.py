#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, os, shutil, subprocess, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DIST=ROOT/'dist'
VERSION='0.9.1'

def sha256(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
 return h.hexdigest()

def source_zip()->Path:
 target=DIST/f'media2md-v{VERSION}-source.zip'
 excluded={'.git','dist','build','.pytest_cache','.mypy_cache','.ruff_cache','Formula','npm'}
 files=[]
 for p in ROOT.rglob('*'):
  rel=p.relative_to(ROOT)
  if not p.is_file() or rel.parts[0] in excluded or any(x in excluded for x in rel.parts): continue
  if rel.parts[:4] in {('src', 'media2md', 'bundle', 'data'), ('src', 'media2md', 'bundle', 'logs')}: continue
  if rel.as_posix() == 'RELEASE_REPORT.json': continue
  if p.suffix in {'.pyc','.pyo'} or '__pycache__' in rel.parts: continue
  files.append(p)
 with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for p in sorted(files):
   rel=p.relative_to(ROOT).as_posix(); info=zipfile.ZipInfo(rel,(2026,6,24,0,0,0)); info.compress_type=zipfile.ZIP_DEFLATED; info.external_attr=(0o755 if p.stat().st_mode&0o111 else 0o644)<<16; z.writestr(info,p.read_bytes())
 return target

def formula(source:Path)->Path:
 digest=sha256(source); out=DIST/'media2md.rb'
 out.write_text(f'''class Media2md < Formula\n  desc "Agent-ready Instagram, YouTube, and TikTok media-to-Markdown pipeline"\n  homepage "https://github.com/danielcanfly/media2md"\n  url "https://github.com/danielcanfly/media2md/releases/download/v{VERSION}/media2md-v{VERSION}-source.zip"\n  sha256 "{digest}"\n  license "MIT"\n  depends_on "python@3.12"\n  depends_on "ffmpeg"\n  def install\n    libexec.install "src/media2md"\n    (bin/"media2md").write <<~EOS\n      #!/bin/bash\n      export PYTHONPATH="#{{libexec}}"\n      exec "#{{Formula[\"python@3.12\"].opt_bin}}/python3.12" -m media2md.cli "$@"\n    EOS\n    chmod 0755, bin/"media2md"\n    bin.install_symlink "media2md" => "social2md"\n  end\n  test do\n    assert_match "media2md {VERSION}", shell_output("#{{bin}}/media2md version")\n    system bin/"media2md", "runtime", "install"\n  end\nend\n''')
 return out

def main():
 DIST.mkdir(exist_ok=True)
 src=source_zip(); formula(src)
 result=subprocess.run(['npm','pack','--silent','--pack-destination',str(DIST)],cwd=ROOT/'npm',check=False,text=True,capture_output=True)
 if result.returncode: raise SystemExit(result.stderr)
 assets=[]
 for p in sorted(DIST.iterdir()):
  if p.is_file() and not p.name.startswith('.') and not p.name.endswith('.sha256') and p.name!='SHA256SUMS':
   digest=sha256(p); (DIST/(p.name+'.sha256')).write_text(f'{digest}  {p.name}\n'); assets.append((digest,p.name))
 (DIST/'SHA256SUMS').write_text(''.join(f'{h}  {n}\n' for h,n in assets))
 print(json.dumps({'version':VERSION,'assets':[n for _,n in assets]},indent=2))
if __name__=='__main__': main()
