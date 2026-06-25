#!/usr/bin/env python3
from __future__ import annotations
import http.cookiejar, json, os, shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUTH_PROFILES = ROOT / "config" / "auth_profiles.json"
SECRET_DIR = ROOT / "data" / "secrets"
DOMAINS = {"instagram": (".instagram.com",), "tiktok": (".tiktok.com",), "youtube": (".youtube.com", ".google.com")}
AUTH_COOKIE_NAMES = {
 "instagram": {"sessionid", "ds_user_id"},
 "tiktok": {"sessionid", "sessionid_ss", "sid_tt", "sid_guard", "uid_tt", "uid_tt_ss"},
}

def iso_now() -> str: return datetime.now(timezone.utc).isoformat(timespec="seconds")
def load_profiles() -> dict[str,Any]:
    try: data=json.loads(AUTH_PROFILES.read_text(encoding="utf-8"))
    except Exception: data={"schema_version":5,"providers":{}}
    data.setdefault("schema_version",5); data.setdefault("providers",{})
    return data

def save_profiles(data:dict[str,Any])->None:
    AUTH_PROFILES.parent.mkdir(parents=True,exist_ok=True)
    temp=AUTH_PROFILES.with_suffix('.tmp'); temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); os.replace(temp,AUTH_PROFILES)

def cookie_db(profile_path: str|Path) -> Path | None:
    base=Path(profile_path)
    for p in (base/'Network'/'Cookies',base/'Cookies'):
        if p.is_file(): return p
    return None

def browser_jar(browser:str, profile_path:str, domain:str):
    try: import browser_cookie3  # type: ignore
    except ImportError as exc: raise RuntimeError('browser-cookie3 is required; install media2md[auth-browser] or media2md[all].') from exc
    fn=getattr(browser_cookie3,browser.lower(),None)
    if not fn: raise RuntimeError(f'Unsupported browser for cookie extraction: {browser}')
    db=cookie_db(profile_path)
    if not db: raise RuntimeError(f'Cookie database not found under profile: {profile_path}')
    return fn(cookie_file=str(db),domain_name=domain)

def export_profile_snapshot(provider:str, profile:dict[str,Any], *, force:bool=True) -> tuple[Path,int,list[str]]:
    browser=str(profile.get('browser') or '')
    profile_path=str(profile.get('profile_path') or '')
    if not browser or not profile_path: raise RuntimeError('Browser profile is not configured.')
    SECRET_DIR.mkdir(parents=True,exist_ok=True)
    out=SECRET_DIR/f'{provider}-cookies.txt'
    merged={}; errors=[]
    for domain in DOMAINS[provider]:
        try:
            for c in browser_jar(browser,profile_path,domain): merged[(c.domain,c.path,c.name)]=c
        except Exception as exc: errors.append(f'{domain}: {exc}')
    if not merged: raise RuntimeError('No platform cookies were found. '+ '; '.join(errors))
    jar=http.cookiejar.MozillaCookieJar(str(out))
    for c in merged.values(): jar.set_cookie(c)
    jar.save(ignore_discard=True,ignore_expires=True); out.chmod(0o600)
    names=sorted({c.name for c in merged.values()})
    return out,len(merged),names

def load_cookie_jar(path:Path)->http.cookiejar.MozillaCookieJar:
    jar=http.cookiejar.MozillaCookieJar(str(path)); jar.load(ignore_discard=True,ignore_expires=True); return jar

def cookie_stats(provider:str, jar:http.cookiejar.CookieJar)->dict[str,Any]:
    now=datetime.now(timezone.utc).timestamp(); active=[]; expired=[]
    for c in jar:
        if c.is_expired(now): expired.append(c.name)
        else: active.append(c.name)
    required=AUTH_COOKIE_NAMES.get(provider,set())
    active_auth=sorted(required.intersection(active)); expired_auth=sorted(required.intersection(expired))
    return {"cookie_active_count":len(active),"cookie_expired_count":len(expired),"auth_cookie_names":active_auth,"expired_auth_cookie_names":expired_auth,"auth_cookie_present":bool(active_auth)}

def refresh_if_configured(provider:str, *, persist:bool=True)->dict[str,Any]:
    data=load_profiles(); p=data['providers'].get(provider,{})
    if p.get('mode')!='browser_profile': return {"refreshed":False,"reason":"not_browser_profile"}
    out,count,names=export_profile_snapshot(provider,p)
    p['cookie_file']=str(out); p['cookie_count']=count; p['snapshot_refreshed_at']=iso_now(); p['last_refresh_error']=None
    data['providers'][provider]=p
    if persist: save_profiles(data)
    return {"refreshed":True,"cookie_file":str(out),"cookie_count":count,"cookie_names":names}
