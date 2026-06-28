from __future__ import annotations
import http.cookiejar, json, zipfile
from pathlib import Path
import pytest


def _cookie(name: str, value: str, expires: int):
    return http.cookiejar.Cookie(
        version=0, name=name, value=value, port=None, port_specified=False,
        domain='.instagram.com', domain_specified=True, domain_initial_dot=True,
        path='/', path_specified=True, secure=True, expires=expires,
        discard=False, comment=None, comment_url=None, rest={}, rfc2109=False,
    )


def test_instagram_expired_cookie_state(tmp_path, monkeypatch):
    import media2md_auth as auth
    jar=http.cookiejar.MozillaCookieJar(str(tmp_path/'instagram-cookies.txt'))
    jar.set_cookie(_cookie('sessionid','x',1)); jar.save(ignore_discard=True,ignore_expires=True)
    profile={'mode':'browser_cookie','cookie_file':str(tmp_path/'instagram-cookies.txt'),'browser':'chrome','profile':'Default'}
    state={'schema_version':5,'providers':{'instagram':profile}}
    monkeypatch.setattr(auth,'load',lambda: json.loads(json.dumps(state)))
    monkeypatch.setattr(auth,'save',lambda payload: None)
    payload=auth.verify_web('instagram',persist=False)
    assert payload['authenticated'] is False
    assert payload['auth_state']=='cookie_expired'
    assert payload['required_action']=='reauthenticate_instagram_in_selected_profile'


def test_instagram_server_authenticated(tmp_path, monkeypatch):
    import media2md_auth as auth
    jar=http.cookiejar.MozillaCookieJar(str(tmp_path/'instagram-cookies.txt'))
    jar.set_cookie(_cookie('sessionid','x',2147483647)); jar.save(ignore_discard=True,ignore_expires=True)
    state={'schema_version':5,'providers':{'instagram':{'mode':'browser_cookie','cookie_file':str(tmp_path/'instagram-cookies.txt')}}}
    monkeypatch.setattr(auth,'load',lambda: json.loads(json.dumps(state)))
    monkeypatch.setattr(auth,'save',lambda payload: None)
    monkeypatch.setattr(auth,'_probe',lambda provider,jar:('authenticated',200,'https://www.instagram.com/accounts/edit/',None))
    payload=auth.verify_web('instagram',persist=False)
    assert payload['authenticated'] is True
    assert payload['auth_state']=='authenticated'


def test_safe_extract_rejects_traversal(tmp_path):
    import media2md_update as update
    archive_path=tmp_path/'bad.zip'
    with zipfile.ZipFile(archive_path,'w') as archive: archive.writestr('../escape.txt','bad')
    with zipfile.ZipFile(archive_path) as archive:
        with pytest.raises(RuntimeError,match='Unsafe path'):
            update._safe_extract(archive,tmp_path/'target')


def test_managed_runtime_import_legacy(monkeypatch,tmp_path):
    import media2md.bootstrap as bootstrap
    monkeypatch.setenv('HOME',str(tmp_path/'home'))
    source=tmp_path/'legacy'; (source/'config').mkdir(parents=True); (source/'config'/'custom.json').write_text('{}')
    result=bootstrap.import_legacy(source)
    assert result['count']==1
    assert (bootstrap.state_root()/'config'/'custom.json').is_file()

def test_managed_runtime_bootstrap_seeds_legacy_config_from_project_registry(monkeypatch,tmp_path):
    import media2md.bootstrap as bootstrap

    home = tmp_path / 'home'
    monkeypatch.setenv('HOME', str(home))
    legacy = tmp_path / 'legacy-project'
    (legacy / 'config').mkdir(parents=True)
    (legacy / 'config' / 'auth_profiles.json').write_text(
        '{"schema_version":5,"providers":{"tiktok":{"mode":"browser_profile","browser":"chrome","profile":"Default"}}}\n'
    )
    (legacy / 'config' / 'social2md.json').write_text('{"timezone":"UTC"}\n')
    registry = home / '.config' / 'media2md' / 'project.json'
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({
        'schema_version': 2,
        'project_root': str(legacy),
        'managed_runtime': False,
        'version': '0.9.1',
    }) + '\n')

    bootstrap.ensure_runtime(force=True)

    auth = bootstrap.state_root() / 'config' / 'auth_profiles.json'
    config = bootstrap.state_root() / 'config' / 'social2md.json'
    assert auth.is_file()
    assert config.is_file()
    assert json.loads(auth.read_text())['providers']['tiktok']['profile'] == 'Default'
    assert json.loads(config.read_text())['timezone'] == 'UTC'

def test_real_ffmpeg_chunk_split(tmp_path):
    import shutil, subprocess
    import generic_media
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:
        pytest.skip('ffmpeg unavailable')
    media=tmp_path/'tone.mp3'
    subprocess.run([ffmpeg,'-v','error','-f','lavfi','-i','sine=frequency=440:duration=4','-c:a','libmp3lame',str(media)],check=True)
    chunks,reused=generic_media._split_audio(media,tmp_path/'chunks',2,4.0)
    assert reused is False
    assert len(chunks)>=2
    again,reused2=generic_media._split_audio(media,tmp_path/'chunks',2,4.0)
    assert reused2 is True
    assert [p.name for p in again]==[p.name for p in chunks]
