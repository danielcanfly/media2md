#!/usr/bin/env python3
from __future__ import annotations
import argparse, http.cookiejar, json, os, sys, urllib.error, urllib.parse, urllib.request, webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from media2md.cli_output_service import make_output_model, make_section
from media2md.health_taxonomy import health_category
from media2md_youtube_session import profile_inventory, validate_profile, verify_youtube_session, load_auth_profiles, save_auth_profiles
from media2md_auth_shared import export_profile_snapshot, load_cookie_jar, cookie_stats, refresh_if_configured

ROOT=Path(__file__).resolve().parents[1]; SECRET_DIR=ROOT/'data'/'secrets'; SUPPORTED=('instagram','youtube','tiktok')
LOGIN_URLS={'instagram':'https://www.instagram.com/accounts/login/','youtube':'https://accounts.google.com/ServiceLogin?service=youtube','tiktok':'https://www.tiktok.com/login'}
PROBES={'instagram':'https://www.instagram.com/accounts/edit/','tiktok':'https://www.tiktok.com/setting'}

def iso_now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def load(): return load_auth_profiles()
def save(x): save_auth_profiles(x)

def _transient_probe_error(provider, error):
 text=str(error or '').lower()
 if provider!='instagram': return False
 return any(token in text for token in (
  'unexpected_eof_while_reading',
  'eof occurred in violation of protocol',
  'ssl',
  'tls',
  'connection reset',
  'temporarily unavailable',
  'timed out',
  'timeout',
 ))

def emit_human(title,payload):
 print(title)
 for k,v in payload.items():
  if k!='event': print(f"{k}={json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v}")

def login(provider,browser,non_interactive,output):
 if provider=='youtube': raise RuntimeError("Use auth profiles/connect for YouTube; Media2MD never opens a Google login window.")
 if not non_interactive:
  opened=webbrowser.open(LOGIN_URLS[provider],new=2); print(f'LOGIN_PAGE_OPENED provider={provider} browser={browser} opened={str(opened).lower()}'); input('Complete login, then press Enter: ')
 rows=profile_inventory(browser)
 if not rows: raise RuntimeError('No browser profiles were found.')
 chosen=rows[0]
 return connect(provider,browser,chosen['profile'],output)

def list_profiles(provider,browser,output):
 rows=profile_inventory(browser)
 if output=='ndjson':
  for row in rows: print(json.dumps({'schema_version':12,'timestamp':iso_now(),'event':'auth_browser_profile','provider':provider,'browser':browser,**row},sort_keys=True))
 else:
  print('BROWSER_PROFILES'); print('PROVIDER   PROFILE      DISPLAY NAME                     COOKIE DB  PATH')
  for r in rows: print(f"{provider:<10} {r['profile']:<12} {r['display_name'][:32]:<32} {str(r['cookie_db_exists']).lower():<10} {r['path']}")
  print(f'TOTAL={len(rows)}')
 return 0 if rows else 2

def connect(provider,browser,profile,output):
 row=validate_profile(browser,profile); data=load(); previous=data['providers'].get(provider,{})
 old=previous.get('cookie_file') if isinstance(previous,dict) else None
 item={'mode':'browser_profile','browser':browser,'profile':profile,'profile_display_name':row['display_name'],'profile_path':row['path'],'use_live_browser_cookies':True,'browser_launch_allowed':False,'updated_at':iso_now(),'last_verified_at':None,'last_auth_state':'configured_unverified','last_authenticated':False,'last_verify_error':None}
 data['schema_version']=max(int(data.get('schema_version',1)),5); data['providers'][provider]=item; save(data)
 if provider!='youtube':
  try:
   result=refresh_if_configured(provider); item=load()['providers'][provider]
  except Exception as exc:
   item['last_refresh_error']=str(exc)[:1000]; data=load(); data['providers'][provider]=item; save(data)
 if old and old!=item.get('cookie_file'): Path(str(old)).unlink(missing_ok=True)
 payload={'event':'auth_connected','provider':provider,'mode':'browser_profile','browser':browser,'profile':profile,'profile_display_name':row['display_name'],'profile_path':row['path'],'browser_launch_allowed':False,'live_cookie_refresh':True}
 if output=='ndjson': print(json.dumps({'schema_version':12,'timestamp':iso_now(),**payload},sort_keys=True))
 else: emit_human('AUTH_CONNECTED',payload); print(f'next_command=media2md auth verify {provider}')
 return 0

def _probe(provider,jar):
 req=urllib.request.Request(PROBES[provider],headers={'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36','Accept':'text/html,application/xhtml+xml'})
 opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
 try:
  with opener.open(req,timeout=20) as resp:
   final=resp.geturl(); status=getattr(resp,'status',200); body=resp.read(200000).decode('utf-8','ignore').lower()
  final_lower=final.lower()
  if '/login' in final_lower or 'accounts/login' in final_lower: return 'server_rejected',status,final,None
  if provider=='instagram':
   # /accounts/edit/ is an authenticated-only endpoint. Instagram's normal
   # application bundle contains the word "checkpoint", so body substring
   # matching produced false challenges for valid sessions in the live v0.8.6 gate.
   if '/accounts/edit' in final_lower and status==200: return 'authenticated',status,final,None
   if '/challenge/' in final_lower or '/checkpoint/' in final_lower: return 'platform_challenge',status,final,None
  if provider=='tiktok':
   # /setting is an authenticated-only endpoint. TikTok's application bundle
   # contains generic captcha/challenge strings even for a valid signed-in
   # session, which caused the v0.9.0 live false negative.
   if urllib.parse.urlparse(final_lower).path.rstrip('/')=='/setting' and status==200:
    return 'authenticated',status,final,None
   if any(marker in final_lower for marker in ('/challenge', '/captcha', '/verify')):
    return 'platform_challenge',status,final,None
   if 'verify to continue' in body:
    return 'platform_challenge',status,final,None
  return 'authenticated',status,final,None
 except urllib.error.HTTPError as exc:
  if exc.code in (401,403): return 'server_rejected',exc.code,getattr(exc,'url',None),str(exc)
  if exc.code==429: return 'platform_challenge',exc.code,getattr(exc,'url',None),str(exc)
  return 'probe_error',exc.code,getattr(exc,'url',None),str(exc)
 except Exception as exc: return 'probe_error',None,None,str(exc)

def verify_web(provider,persist=True):
 data=load(); p=data['providers'].get(provider,{})
 payload={'event':'auth_verify','provider':provider,'browser_launch_allowed':False,'browser':p.get('browser'),'profile':p.get('profile'),'profile_configured':bool(p.get('mode')=='browser_profile' and p.get('browser') and p.get('profile')),'cookie_extraction_ready':False,'authenticated':False,'auth_state':'unconfigured','required_action':None,'guidance':[],'error':None}
 if not p:
  payload['required_action']=f'connect_{provider}_browser_profile'; return payload
 try:
  if p.get('mode')=='browser_profile': refresh_if_configured(provider); data=load(); p=data['providers'][provider]
  cookie=Path(str(p.get('cookie_file') or ''))
  if not cookie.is_file():
   payload.update(auth_state='cookie_missing',required_action=f'reauthenticate_{provider}_in_selected_profile',error='Cookie snapshot is missing.'); return payload
  jar=load_cookie_jar(cookie); payload['cookie_extraction_ready']=True; payload.update(cookie_stats(provider,jar))
  if not payload['auth_cookie_present']:
   state='cookie_expired' if payload.get('expired_auth_cookie_names') else 'cookie_missing'
   payload.update(auth_state=state,required_action=f'reauthenticate_{provider}_in_selected_profile',guidance=[f'Open {p.get("profile_display_name") or p.get("profile")} in {p.get("browser")}.',f'Log in to {provider} manually.',f'Run: media2md auth verify {provider}']); return payload
  state,status,final,error=_probe(provider,jar); payload.update(server_auth_probe=state,server_auth_status=status,server_final_url=final,error=error)
  if state=='authenticated': payload.update(authenticated=True,auth_state='authenticated')
  elif state=='platform_challenge': payload.update(auth_state='platform_challenge',required_action=f'complete_{provider}_challenge_in_selected_profile',guidance=[f'Open the selected browser profile and complete the {provider} verification challenge.',f'Run: media2md auth verify {provider}'])
  elif state=='server_rejected': payload.update(auth_state='server_rejected',required_action=f'reauthenticate_{provider}_in_selected_profile',guidance=[f'Log in to {provider} in the selected browser profile.',f'Run: media2md auth verify {provider}'])
  elif state=='probe_error' and _transient_probe_error(provider,error) and payload.get('auth_cookie_present'):
   payload.update(
    auth_state='configured_unverified',
    required_action=None,
    retryable=True,
    warning='Browser auth cookies are present, but the live server probe failed with a transient transport error.',
    guidance=[f'Retry: media2md auth verify {provider}',f'If normal commands work, treat this as a probe-only failure and continue.'],
   )
  else: payload.update(auth_state='configured_unverified',required_action=f'inspect_{provider}_access_error')
 except Exception as exc:
  text=str(exc); lower=text.lower(); state='cookie_store_locked' if any(x in lower for x in ('locked','database is locked','permission')) else 'dependency_missing' if 'browser-cookie3' in lower else 'cookie_extraction_failed'
  payload.update(auth_state=state,error=text,required_action='close_browser_and_check_profile_cookie_access' if state=='cookie_store_locked' else 'install_auth_browser_dependencies' if state=='dependency_missing' else f'reconnect_{provider}_browser_profile')
 if persist:
  data=load(); p=data['providers'].get(provider,p); p['last_verified_at']=iso_now(); p['last_auth_state']=payload['auth_state']; p['last_authenticated']=payload['authenticated']; p['last_verify_error']=payload.get('error'); data['providers'][provider]=p; save(data)
 return payload

def verify(provider,video_id,output):
 payload=verify_youtube_session(video_id,persist=True) if provider=='youtube' else verify_web(provider,True)
 if output=='ndjson': print(json.dumps({'schema_version':12,'timestamp':iso_now(),**payload},ensure_ascii=False,sort_keys=True))
 else: emit_human(f'{provider.upper()}_AUTH_VERIFY',payload)
 return 0 if payload.get('authenticated') else 2

def refresh(provider,quiet,output):
 if provider=='youtube': payload={'event':'auth_refresh','provider':'youtube','refreshed':True,'mode':'live_browser_read_on_demand'}
 else:
  try: payload={'event':'auth_refresh','provider':provider,**refresh_if_configured(provider)}
  except Exception as exc: payload={'event':'auth_refresh','provider':provider,'refreshed':False,'error':str(exc),'required_action':f'reauthenticate_{provider}_in_selected_profile'}
 if not quiet:
  if output=='ndjson': print(json.dumps({'schema_version':12,'timestamp':iso_now(),**payload},sort_keys=True))
  else: emit_human('AUTH_REFRESH',payload)
 return 0 if payload.get('refreshed') else 2

def status(output):
 data=load(); rows=[]
 for provider in SUPPORTED:
  p=data['providers'].get(provider,{}); cookie=Path(str(p.get('cookie_file') or '')) if p.get('cookie_file') else None
  configured=bool(p.get('mode')=='browser_profile' and p.get('browser') and p.get('profile')) or bool(cookie and cookie.is_file())
  rows.append({'provider':provider,'configured':configured,'authenticated':bool(p.get('last_authenticated',False)) if configured else False,'auth_state':p.get('last_auth_state') or ('configured_unverified' if configured else 'unconfigured'),'mode':p.get('mode'),'browser':p.get('browser'),'profile':p.get('profile'),'last_verified_at':p.get('last_verified_at'),'last_refresh_error':p.get('last_refresh_error')})
 if rows:
  section_status = "ok" if all(row["authenticated"] or not row["configured"] for row in rows) else "warn"
 else:
  section_status = "ok"
 payload = make_output_model(
  event="auth_status",
  schema="media2md.cli.auth_status/v1",
  summary="Authentication status summary",
  sections=(
   make_section(
    "auth",
    status=section_status,
    message="Authentication state for configured providers",
    data={"providers": rows},
   ),
  ),
  data={"providers": rows},
 ).as_dict()
 if output=='ndjson':
  print(json.dumps({'schema_version':12,'timestamp':iso_now(),**payload},sort_keys=True))
 else:
  print("AUTH_STATUS")
  print("tip=Run `media2md auth verify <provider>` after logging in to refresh the saved auth state.")
  print('PROVIDER   CONFIGURED  AUTHENTICATED  AUTH_STATE              MODE              BROWSER   PROFILE      LAST_VERIFIED')
  for r in rows: print(f"{r['provider']:<10} {str(r['configured']).lower():<11} {str(r['authenticated']).lower():<14} {(r['auth_state'] or '-'):<23} {(r['mode'] or '-'):<17} {(r['browser'] or '-'):<9} {(r['profile'] or '-'):<12} {r['last_verified_at'] or '-'}")
 return 0

def disconnect(provider,yes):
 if not yes: raise RuntimeError('Disconnect requires --yes.')
 data=load(); p=data['providers'].pop(provider,None)
 if p and p.get('cookie_file'): Path(str(p['cookie_file'])).unlink(missing_ok=True)
 save(data); print(f'AUTH_DISCONNECT_COMPLETED provider={provider}'); print('browser_session_unchanged=true'); print('operation=disconnect_media2md_profile'); return 0

def capabilities():
 print('AUTH_CAPABILITIES'); print('browser_profile=instagram,youtube,tiktok'); print('browser_launch_policy=never-for-agent-commands'); print('live_cookie_refresh=instagram,youtube,tiktok'); print('server_session_verify=instagram,youtube,tiktok'); print('automatic_password_login=false'); print('human_required=password,2fa,captcha,platform_challenge'); return 0

def main():
 p=argparse.ArgumentParser(); s=p.add_subparsers(dest='cmd',required=True)
 x=s.add_parser('login'); x.add_argument('provider',choices=SUPPORTED); x.add_argument('--browser',default='chrome'); x.add_argument('--non-interactive',action='store_true'); x.add_argument('--output',choices=('human','ndjson'),default='human')
 x=s.add_parser('profiles'); x.add_argument('provider',choices=SUPPORTED); x.add_argument('--browser',choices=('chrome','chromium','brave','edge'),default='chrome'); x.add_argument('--output',choices=('human','ndjson'),default='human')
 x=s.add_parser('connect'); x.add_argument('provider',choices=SUPPORTED); x.add_argument('--browser',choices=('chrome','chromium','brave','edge'),default='chrome'); x.add_argument('--profile',required=True); x.add_argument('--output',choices=('human','ndjson'),default='human')
 x=s.add_parser('verify'); x.add_argument('provider',choices=SUPPORTED); x.add_argument('--video-id'); x.add_argument('--output',choices=('human','ndjson'),default='human')
 x=s.add_parser('refresh'); x.add_argument('provider',choices=SUPPORTED); x.add_argument('--quiet',action='store_true'); x.add_argument('--output',choices=('human','ndjson'),default='human')
 x=s.add_parser('status'); x.add_argument('--output',choices=('human','ndjson'),default='human')
 for name in ('logout','disconnect'):
  x=s.add_parser(name); x.add_argument('provider',choices=SUPPORTED); x.add_argument('--yes',action='store_true')
 s.add_parser('capabilities'); a=p.parse_args()
 if a.cmd=='login': return login(a.provider,a.browser,a.non_interactive,a.output)
 if a.cmd=='profiles': return list_profiles(a.provider,a.browser,a.output)
 if a.cmd=='connect': return connect(a.provider,a.browser,a.profile,a.output)
 if a.cmd=='verify': return verify(a.provider,a.video_id,a.output)
 if a.cmd=='refresh': return refresh(a.provider,a.quiet,a.output)
 if a.cmd=='status': return status(a.output)
 if a.cmd in ('logout','disconnect'): return disconnect(a.provider,a.yes)
 return capabilities()
if __name__=='__main__':
 try: raise SystemExit(main())
 except RuntimeError as exc: print(f'ERROR: {exc}',file=sys.stderr); raise SystemExit(2)
