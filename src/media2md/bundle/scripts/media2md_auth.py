#!/usr/bin/env python3
from __future__ import annotations
import argparse, http.cookiejar, json, os, sys, tempfile, urllib.error, urllib.parse, urllib.request, webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if sys.path and sys.path[0] == _SCRIPT_DIR:
 sys.path.append(sys.path.pop(0))

try:
    from media2md.cli_output_service import make_event_payload, make_output_model, make_section
    from media2md.health_taxonomy import health_category
except ModuleNotFoundError:
    from media2md_contract_compat import make_event_payload, make_output_model, make_section, health_category
try:
    from media2md.remediation_service import auth_verify_command, provider_profile_guidance
except ModuleNotFoundError:
    from media2md_remediation_compat import auth_verify_command, provider_profile_guidance
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

def emit_ndjson(payload):
 print(json.dumps({'schema_version':12,'timestamp':iso_now(),**payload},ensure_ascii=False,sort_keys=True))

def ensure_schema(payload, *, event, schema):
 enriched={**payload}
 enriched.setdefault('event',event)
 enriched.setdefault('schema',schema)
 return enriched

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
  for row in rows:
   emit_ndjson(make_event_payload(event='auth_browser_profile',schema='media2md.cli.auth_browser_profile/v1',data={'provider':provider,'browser':browser,**row}))
 else:
  print('BROWSER_PROFILES'); print('PROVIDER   PROFILE      DISPLAY NAME                     COOKIE DB  PATH')
  for r in rows: print(f"{provider:<10} {r['profile']:<12} {r['display_name'][:32]:<32} {str(r['cookie_db_exists']).lower():<10} {r['path']}")
  print(f'TOTAL={len(rows)}')
 return 0 if rows else 2

def _resolve_selected_instagram_account(browser,profile_name,requested_account):
 code,payload=_instagram_accounts_payload(browser,profile_name,persist=False)
 accounts=payload.get('accounts',[])
 if not accounts:
  raise RuntimeError('No Instagram account could be resolved from the selected browser profile.')
 if requested_account is None:
  if len(accounts)==1: return accounts[0],'implicit_single_discovered_account'
  raise RuntimeError('Multiple Instagram accounts require explicit --account selection.')
 chosen=str(requested_account).strip()
 for item in accounts:
  keys={str(item.get('account_key') or '').strip(),str(item.get('account_id') or '').strip(),str(item.get('username') or '').strip()}
  if chosen in {key for key in keys if key}:
   return item,'explicit_connect_account'
 available=', '.join(str(item.get('account_key') or item.get('account_id') or item.get('username') or '-') for item in accounts)
 raise RuntimeError(f'Instagram account `{chosen}` was not resolved from this browser profile. Available account keys: {available}')

def connect(provider,browser,profile,output,account=None):
 row=validate_profile(browser,profile); data=load(); previous=data['providers'].get(provider,{})
 old=previous.get('cookie_file') if isinstance(previous,dict) else None
 item={'mode':'browser_profile','browser':browser,'profile':profile,'profile_display_name':row['display_name'],'profile_path':row['path'],'use_live_browser_cookies':True,'browser_launch_allowed':False,'updated_at':iso_now(),'last_verified_at':None,'last_auth_state':'configured_unverified','last_authenticated':False,'last_verify_error':None}
 if account is not None and provider!='instagram':
  raise RuntimeError(f'Explicit --account selection is not yet supported for {provider}.')
 if provider=='instagram':
  discovered,selection_mode=_resolve_selected_instagram_account(browser,profile,account)
  item['selected_account_id']=discovered.get('account_id')
  item['selected_account_username']=discovered.get('username')
  item['selected_account_display_name']=discovered.get('display_name')
  item['selected_account_key']=discovered.get('account_key')
  item['selected_account_source']=selection_mode
 data['schema_version']=max(int(data.get('schema_version',1)),5); data['providers'][provider]=item; save(data)
 if provider!='youtube':
  try:
   result=refresh_if_configured(provider); item=load()['providers'][provider]
  except Exception as exc:
   item['last_refresh_error']=str(exc)[:1000]; data=load(); data['providers'][provider]=item; save(data)
 if old and old!=item.get('cookie_file'): Path(str(old)).unlink(missing_ok=True)
 payload=make_event_payload(event='auth_connected',schema='media2md.cli.auth_connected/v1',data={'provider':provider,'mode':'browser_profile','browser':browser,'profile':profile,'profile_display_name':row['display_name'],'profile_path':row['path'],'browser_launch_allowed':False,'live_cookie_refresh':True,'selected_account_key':item.get('selected_account_key'),'selected_account_id':item.get('selected_account_id'),'selected_account_username':item.get('selected_account_username'),'selected_account_display_name':item.get('selected_account_display_name'),'account_selection_mode':item.get('selected_account_source')})
 if output=='ndjson': emit_ndjson(payload)
 else: emit_human('AUTH_CONNECTED',payload); print(f'next_command=media2md auth verify {provider}')
 return 0

def _account_key(account_id, username):
 if username: return str(username)
 if account_id: return str(account_id)
 return 'effective-session'

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

def _active_cookie_value(jar,name):
 now=datetime.now(timezone.utc).timestamp()
 for cookie in jar:
  if cookie.name==name and not cookie.is_expired(now): return cookie.value
 return None

def _instagram_identity_probe(jar):
 opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
 headers={
  'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36',
  'Accept':'application/json',
  'X-Requested-With':'XMLHttpRequest',
 }
 last_error=None
 for url in (
  'https://www.instagram.com/api/v1/accounts/current_user/?edit=true',
  'https://i.instagram.com/api/v1/accounts/current_user/?edit=true',
 ):
  try:
   with opener.open(urllib.request.Request(url,headers=headers),timeout=20) as resp:
    final=resp.geturl(); body=resp.read(500000).decode('utf-8','ignore')
  except urllib.error.HTTPError as exc:
   last_error=f'HTTP {exc.code} from {urllib.parse.urlparse(url).path}'
   continue
  except Exception as exc:
   last_error=str(exc)
   continue
  try:
   data=json.loads(body)
  except json.JSONDecodeError:
   last_error=f'Non-JSON response from {urllib.parse.urlparse(final).path}'
   continue
  user=data.get('user') if isinstance(data,dict) else None
  if isinstance(user,dict):
   account_id=str(user.get('pk') or user.get('id') or '').strip() or None
   username=str(user.get('username') or '').strip() or None
   display_name=str(user.get('full_name') or '').strip() or None
   if account_id or username or display_name:
    return {
     'resolved_account_id':account_id,
     'resolved_account_username':username,
     'resolved_account_display_name':display_name,
     'account_identity_source':f'live_probe:{urllib.parse.urlparse(final).path or urllib.parse.urlparse(url).path}',
    }
  last_error=f'No account identity fields returned from {urllib.parse.urlparse(final).path}'
 return {'account_identity_error':last_error}

def _resolve_instagram_identity(jar):
 cookie_account_id=_active_cookie_value(jar,'ds_user_id')
 identity={
  'resolved_account_id':cookie_account_id or None,
  'resolved_account_username':None,
  'resolved_account_display_name':None,
  'account_identity_source':'cookie:ds_user_id' if cookie_account_id else None,
  'account_identity_warning':None,
 }
 live=_instagram_identity_probe(jar)
 if live.get('resolved_account_id') or live.get('resolved_account_username') or live.get('resolved_account_display_name'):
  if cookie_account_id and live.get('resolved_account_id') and str(cookie_account_id)!=str(live['resolved_account_id']):
   identity['account_identity_warning']='Instagram cookie user id and live identity probe disagree; Media2MD is reporting the live resolved account.'
  identity.update(live)
  return identity
 if cookie_account_id:
  identity['account_identity_warning']='Resolved Instagram account id from cookies only; live username probe was unavailable.'
  return identity
 if live.get('account_identity_error'):
  identity['account_identity_warning']='Unable to resolve Instagram account identity from the current session.'
 return identity

def _apply_instagram_account_tracking(profile,payload):
 resolved_id=payload.get('resolved_account_id')
 resolved_username=payload.get('resolved_account_username')
 resolved_display_name=payload.get('resolved_account_display_name')
 selected_id=profile.get('selected_account_id')
 selected_username=profile.get('selected_account_username')
 selected_display_name=profile.get('selected_account_display_name')
 if (resolved_id or resolved_username) and not (selected_id or selected_username):
  profile['selected_account_id']=resolved_id
  profile['selected_account_username']=resolved_username
  profile['selected_account_display_name']=resolved_display_name
  profile['selected_account_source']='implicit_first_verified_identity'
  selected_id=resolved_id
  selected_username=resolved_username
  selected_display_name=resolved_display_name
 payload['selected_account_id']=selected_id
 payload['selected_account_username']=selected_username
 payload['selected_account_display_name']=selected_display_name
 profile['last_resolved_account_id']=resolved_id
 profile['last_resolved_account_username']=resolved_username
 profile['last_resolved_account_display_name']=resolved_display_name
 match=None
 if (selected_id or selected_username) and (resolved_id or resolved_username):
  if selected_id and resolved_id:
   match=str(selected_id)==str(resolved_id)
  elif selected_username and resolved_username:
   match=str(selected_username).casefold()==str(resolved_username).casefold()
 if match is not None:
  payload['account_match']=match
  profile['last_account_match']=match
  if match is False:
   selected_label=selected_username or selected_id
   resolved_label=resolved_username or resolved_id
   payload['account_mismatch_warning']=f'Selected Instagram account {selected_label} does not match the current live session {resolved_label}.'
 return profile,payload

def _persist_discovered_accounts(provider,browser,profile_name,row,accounts,*,discovery_mode,enumeration_complete):
 data=load(); current=data['providers'].get(provider,{})
 if not isinstance(current,dict): current={}
 if current.get('browser')==browser and current.get('profile')==profile_name:
  current['profile_display_name']=row.get('display_name')
  current['profile_path']=row.get('path')
  current['last_account_discovery_at']=iso_now()
  current['account_discovery_mode']=discovery_mode
  current['account_enumeration_complete']=bool(enumeration_complete)
  current['discovered_accounts']=[
   {
    'account_key':item.get('account_key'),
    'account_id':item.get('account_id'),
    'username':item.get('username'),
    'display_name':item.get('display_name'),
    'status':item.get('status'),
    'selected':bool(item.get('selected')),
    'source':item.get('source'),
    'effective_session':bool(item.get('effective_session')),
   }
   for item in accounts
  ]
  data['providers'][provider]=current
  save(data)

def _instagram_accounts_payload(browser,profile_name,*,persist=True):
 row=validate_profile(browser,profile_name)
 errors=[]; accounts=[]; warning='Instagram account discovery currently reports the effective session Media2MD can resolve from this browser profile; full multi-account enumeration is not yet available.'
 SECRET_DIR.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile(prefix='media2md-instagram-discovery-',suffix='.txt',dir=str(SECRET_DIR),delete=False) as handle:
  temp_path=Path(handle.name)
 try:
  temp_path.unlink(missing_ok=True)
  profile={'browser':browser,'profile_path':row['path']}
  out,count,names=export_profile_snapshot('instagram',profile,output_path=temp_path)
  jar=load_cookie_jar(out)
  stats=cookie_stats('instagram',jar)
  identity=_resolve_instagram_identity(jar)
  resolved_id=identity.get('resolved_account_id')
  resolved_username=identity.get('resolved_account_username')
  resolved_display_name=identity.get('resolved_account_display_name')
  selected=False
  saved=load().get('providers',{}).get('instagram',{})
  if isinstance(saved,dict):
   selected_id=saved.get('selected_account_id')
   selected_username=saved.get('selected_account_username')
   if selected_id and resolved_id:
    selected=str(selected_id)==str(resolved_id)
   elif selected_username and resolved_username:
    selected=str(selected_username).casefold()==str(resolved_username).casefold()
  if stats.get('auth_cookie_present') and (resolved_id or resolved_username or resolved_display_name):
   accounts.append({
    'account_key':_account_key(resolved_id,resolved_username),
    'account_id':resolved_id,
    'username':resolved_username,
    'display_name':resolved_display_name,
    'status':'authenticated',
    'selected':selected,
    'source':identity.get('account_identity_source'),
    'effective_session':True,
   })
  if identity.get('account_identity_warning'): errors.append(identity['account_identity_warning'])
  if not accounts and not stats.get('auth_cookie_present'):
   errors.append('No active Instagram auth cookies were found for this browser profile.')
  if persist: _persist_discovered_accounts('instagram',browser,profile_name,row,accounts,discovery_mode='effective_session_only',enumeration_complete=False)
  status='ok' if accounts else 'missing'
  message='Instagram account discovery completed' if accounts else 'No Instagram account could be resolved from this browser profile'
  account_selection_ready=bool(accounts)
  payload=make_output_model(
   event='auth_accounts',
   schema='media2md.cli.auth_accounts/v1',
   summary=message,
   sections=(
    make_section(
     'accounts',
     status=status,
     message=message,
     data={
      'provider':'instagram',
      'browser':browser,
      'profile':profile_name,
      'profile_display_name':row.get('display_name'),
      'profile_path':row.get('path'),
      'cookie_count':count,
      'cookie_names':names,
      'auth_cookie_present':bool(stats.get('auth_cookie_present')),
      'discovery_mode':'effective_session_only',
      'enumeration_complete':False,
      'account_selection_ready':account_selection_ready,
      'warning':warning,
      'warnings':errors,
      'accounts':accounts,
     },
    ),
   ),
   data={
    'provider':'instagram',
    'browser':browser,
    'profile':profile_name,
    'profile_display_name':row.get('display_name'),
    'profile_path':row.get('path'),
    'cookie_count':count,
    'cookie_names':names,
    'auth_cookie_present':bool(stats.get('auth_cookie_present')),
    'discovery_mode':'effective_session_only',
    'enumeration_complete':False,
    'account_selection_ready':account_selection_ready,
    'warning':warning,
    'warnings':errors,
    'accounts':accounts,
   },
  ).as_dict()
  return (0 if accounts else 2),payload
 finally:
  temp_path.unlink(missing_ok=True)

def accounts(provider,browser,profile_name,output):
 if provider!='instagram':
  payload=make_output_model(
   event='auth_accounts',
   schema='media2md.cli.auth_accounts/v1',
   summary='Account discovery is not yet available for this provider',
   sections=(
    make_section(
     'accounts',
     status='warn',
     message='Account discovery is not yet available for this provider',
     data={
      'provider':provider,
      'browser':browser,
      'profile':profile_name,
      'supported':False,
      'accounts':[],
      'warning':f'Media2MD does not yet support explicit account discovery for {provider}.',
     },
    ),
   ),
   data={
    'provider':provider,
    'browser':browser,
    'profile':profile_name,
    'supported':False,
    'accounts':[],
    'warning':f'Media2MD does not yet support explicit account discovery for {provider}.',
   },
  ).as_dict()
  code=0
 else:
  code,payload=_instagram_accounts_payload(browser,profile_name)
 if output=='ndjson': emit_ndjson(payload)
 else:
  print('AUTH_ACCOUNTS')
  print(f"provider={payload.get('provider')}")
  print(f"browser={payload.get('browser')}")
  print(f"profile={payload.get('profile')}")
  if payload.get('profile_display_name') is not None: print(f"profile_display_name={payload.get('profile_display_name')}")
  if payload.get('discovery_mode') is not None: print(f"discovery_mode={payload.get('discovery_mode')}")
  if payload.get('enumeration_complete') is not None: print(f"enumeration_complete={str(bool(payload.get('enumeration_complete'))).lower()}")
  if payload.get('account_selection_ready') is not None: print(f"account_selection_ready={str(bool(payload.get('account_selection_ready'))).lower()}")
  if payload.get('warning'): print(f"warning={payload.get('warning')}")
  if payload.get('warnings'):
   for item in payload['warnings']: print(f"warning_detail={item}")
  print('ACCOUNT_KEY   ACCOUNT_ID        USERNAME                DISPLAY_NAME                    STATUS          SELECTED  SOURCE')
  for item in payload.get('accounts',[]):
   print(f"{str(item.get('account_key') or '-')[:12]:<12} {str(item.get('account_id') or '-')[:16]:<16} {str(item.get('username') or '-')[:22]:<22} {str(item.get('display_name') or '-')[:30]:<30} {str(item.get('status') or '-')[:14]:<14} {str(bool(item.get('selected'))).lower():<9} {str(item.get('source') or '-')}")
  print(f"TOTAL={len(payload.get('accounts',[]))}")
 return code

def verify_web(provider,persist=True):
 data=load(); p=data['providers'].get(provider,{})
 payload=make_event_payload(event='auth_verify',schema='media2md.cli.auth_verify/v1',data={'provider':provider,'browser_launch_allowed':False,'browser':p.get('browser'),'profile':p.get('profile'),'profile_configured':bool(p.get('mode')=='browser_profile' and p.get('browser') and p.get('profile')),'cookie_extraction_ready':False,'authenticated':False,'auth_state':'unconfigured','required_action':None,'guidance':[],'error':None})
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
   payload.update(auth_state=state,required_action=f'reauthenticate_{provider}_in_selected_profile',guidance=provider_profile_guidance(provider,browser=p.get("browser"),profile=p.get("profile_display_name") or p.get("profile"),action='login')); return payload
  state,status,final,error=_probe(provider,jar); payload.update(server_auth_probe=state,server_auth_status=status,server_final_url=final,error=error)
  if state=='authenticated': payload.update(authenticated=True,auth_state='authenticated')
  elif state=='platform_challenge': payload.update(auth_state='platform_challenge',required_action=f'complete_{provider}_challenge_in_selected_profile',guidance=provider_profile_guidance(provider,browser=p.get("browser"),profile=p.get("profile_display_name") or p.get("profile"),action='challenge'))
  elif state=='server_rejected': payload.update(auth_state='server_rejected',required_action=f'reauthenticate_{provider}_in_selected_profile',guidance=provider_profile_guidance(provider,browser=p.get("browser"),profile=p.get("profile_display_name") or p.get("profile"),action='refresh_login'))
  elif state=='probe_error' and _transient_probe_error(provider,error) and payload.get('auth_cookie_present'):
   payload.update(
    auth_state='configured_unverified',
    required_action=None,
    retryable=True,
   warning='Browser auth cookies are present, but the live server probe failed with a transient transport error.',
    guidance=[f'Retry: {auth_verify_command(provider)}',f'If normal commands work, treat this as a probe-only failure and continue.'],
   )
  else: payload.update(auth_state='configured_unverified',required_action=f'inspect_{provider}_access_error')
  if provider=='instagram' and payload.get('auth_cookie_present'):
   payload.update(_resolve_instagram_identity(jar))
   p,payload=_apply_instagram_account_tracking(dict(p),payload)
 except Exception as exc:
  text=str(exc); lower=text.lower(); state='cookie_store_locked' if any(x in lower for x in ('locked','database is locked','permission')) else 'dependency_missing' if 'browser-cookie3' in lower else 'cookie_extraction_failed'
  payload.update(auth_state=state,error=text,required_action='close_browser_and_check_profile_cookie_access' if state=='cookie_store_locked' else 'install_auth_browser_dependencies' if state=='dependency_missing' else f'reconnect_{provider}_browser_profile')
 if persist:
  data=load(); current=data['providers'].get(provider,{})
  if isinstance(current,dict) and isinstance(p,dict): current={**current,**p}
  else: current=p
  current['last_verified_at']=iso_now(); current['last_auth_state']=payload['auth_state']; current['last_authenticated']=payload['authenticated']; current['last_verify_error']=payload.get('error'); data['providers'][provider]=current; save(data)
 return payload

def verify(provider,video_id,output):
 payload=verify_youtube_session(video_id,persist=True) if provider=='youtube' else verify_web(provider,True)
 payload=ensure_schema(payload,event=payload.get('event') or 'auth_verify',schema='media2md.cli.auth_verify/v1')
 if output=='ndjson': emit_ndjson(payload)
 else: emit_human(f'{provider.upper()}_AUTH_VERIFY',payload)
 return 0 if payload.get('authenticated') else 2

def refresh(provider,quiet,output):
 if provider=='youtube': payload=make_event_payload(event='auth_refresh',schema='media2md.cli.auth_refresh/v1',data={'provider':'youtube','refreshed':True,'mode':'live_browser_read_on_demand'})
 else:
  try: payload=make_event_payload(event='auth_refresh',schema='media2md.cli.auth_refresh/v1',data={'provider':provider,**refresh_if_configured(provider)})
  except Exception as exc: payload=make_event_payload(event='auth_refresh',schema='media2md.cli.auth_refresh/v1',data={'provider':provider,'refreshed':False,'error':str(exc),'required_action':f'reauthenticate_{provider}_in_selected_profile'})
 if not quiet:
  if output=='ndjson': emit_ndjson(payload)
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
  emit_ndjson(payload)
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
 print('AUTH_CAPABILITIES'); print('browser_profile=instagram,youtube,tiktok'); print('live_cookie_refresh=instagram,youtube,tiktok'); print('server_session_verify=instagram,youtube,tiktok'); print('account_discovery=instagram-effective-session-only'); print('browser_launch_policy=never-for-agent-commands'); print('automatic_password_login=false'); print('human_required=password,2fa,captcha,platform_challenge'); return 0

def main():
 p=argparse.ArgumentParser(); s=p.add_subparsers(dest='cmd',required=True)
 x=s.add_parser('login'); x.add_argument('provider',choices=SUPPORTED); x.add_argument('--browser',default='chrome'); x.add_argument('--non-interactive',action='store_true'); x.add_argument('--output',choices=('human','ndjson'),default='human')
 x=s.add_parser('profiles'); x.add_argument('provider',choices=SUPPORTED); x.add_argument('--browser',choices=('chrome','chromium','brave','edge'),default='chrome'); x.add_argument('--output',choices=('human','ndjson'),default='human')
 x=s.add_parser('accounts'); x.add_argument('provider',choices=SUPPORTED); x.add_argument('--browser',choices=('chrome','chromium','brave','edge'),default='chrome'); x.add_argument('--profile',required=True); x.add_argument('--output',choices=('human','ndjson'),default='human')
 x=s.add_parser('connect'); x.add_argument('provider',choices=SUPPORTED); x.add_argument('--browser',choices=('chrome','chromium','brave','edge'),default='chrome'); x.add_argument('--profile',required=True); x.add_argument('--account'); x.add_argument('--output',choices=('human','ndjson'),default='human')
 x=s.add_parser('verify'); x.add_argument('provider',choices=SUPPORTED); x.add_argument('--video-id'); x.add_argument('--output',choices=('human','ndjson'),default='human')
 x=s.add_parser('refresh'); x.add_argument('provider',choices=SUPPORTED); x.add_argument('--quiet',action='store_true'); x.add_argument('--output',choices=('human','ndjson'),default='human')
 x=s.add_parser('status'); x.add_argument('--output',choices=('human','ndjson'),default='human')
 for name in ('logout','disconnect'):
  x=s.add_parser(name); x.add_argument('provider',choices=SUPPORTED); x.add_argument('--yes',action='store_true')
 s.add_parser('capabilities'); a=p.parse_args()
 if a.cmd=='login': return login(a.provider,a.browser,a.non_interactive,a.output)
 if a.cmd=='profiles': return list_profiles(a.provider,a.browser,a.output)
 if a.cmd=='accounts': return accounts(a.provider,a.browser,a.profile,a.output)
 if a.cmd=='connect': return connect(a.provider,a.browser,a.profile,a.output,a.account)
 if a.cmd=='verify': return verify(a.provider,a.video_id,a.output)
 if a.cmd=='refresh': return refresh(a.provider,a.quiet,a.output)
 if a.cmd=='status': return status(a.output)
 if a.cmd in ('logout','disconnect'): return disconnect(a.provider,a.yes)
 return capabilities()
if __name__=='__main__':
 try: raise SystemExit(main())
 except RuntimeError as exc: print(f'ERROR: {exc}',file=sys.stderr); raise SystemExit(2)
