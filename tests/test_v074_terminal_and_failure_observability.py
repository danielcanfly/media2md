from __future__ import annotations
import importlib.util, os, signal, subprocess, sys, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/'src'/'media2md'/'bundle'/'scripts'

def load(module_name, filename):
 spec=importlib.util.spec_from_file_location(module_name,SCRIPTS/filename)
 mod=importlib.util.module_from_spec(spec); assert spec and spec.loader; sys.modules[module_name]=mod; spec.loader.exec_module(mod); return mod

def test_v074_installer_purges_stale_bytecode_and_direct_wrapper():
 text=(ROOT/'install_media2md_v074.py').read_text()
 assert 'purge_bytecode' in text
 assert '--force-reinstall' in text
 assert "scripts/media2md.py" in text
 wrapper=(ROOT/'bin'/'media2md').read_text()
 assert '-B "$ROOT/scripts/media2md.py"' in wrapper

def test_install_guide_uses_child_subshell_and_no_interactive_set_e():
 text=(ROOT/'MEDIA2MD_V074_INSTALL.md').read_text()
 assert '\n(\n  set -euo pipefail' in text
 assert 'upgrade_exit_code=' in text
 assert 'Do not run `set -euo pipefail` by itself' in text

def test_tiktok_capture_emits_heartbeat(monkeypatch, capsys):
 registry=load('media2md_registry_v074_heartbeat','media2md_registry.py')
 class FakeProcess:
  pid=4321
  returncode=0
  calls=0
  def communicate(self, timeout=None):
   self.calls+=1
   if self.calls<3: raise subprocess.TimeoutExpired(['x'],timeout)
   return ('{}','')
  def poll(self): return None
 monkeypatch.setattr(registry.subprocess,'Popen',lambda *a,**k: FakeProcess())
 clock={'v':-1.1}
 def fake_monotonic():
  clock['v']+=1.1
  return clock['v']
 monkeypatch.setattr(registry.time,'monotonic',fake_monotonic)
 result=registry._capture_process(['x'],30,heartbeat_context='provider=tiktok strategy=plain',heartbeat_interval=1)
 assert result.returncode==0
 assert 'SYNC_WAITING provider=tiktok strategy=plain' in capsys.readouterr().err

def test_tiktok_timeout_is_finite():
 text=(SCRIPTS/'media2md_registry.py').read_text()
 assert 'MEDIA2MD_TIKTOK_EXTRACT_TIMEOUT_SECONDS' in text
 assert 'MEDIA2MD_TIKTOK_PAGE_BUDGET_SECONDS' in text

def test_instagram_progress_and_failure_diagnostics_present():
 core=(SCRIPTS/'social2md_core.py').read_text()
 bulk=(SCRIPTS/'creator_bulk.py').read_text()
 assert 'completed={int(event.get' in core
 assert 'ITEM_RESULT shortcode=' in core
 assert 'required_action=inspect_instagram_failure_report' in core
 assert '"--max-failures", str(max_failures)' in core
 assert 'BATCH_ABORTED reason=max_failures' in bulk
 assert 'ITEM_FAILED shortcode=' in bulk
 assert 'processed={len(report[' in bulk
