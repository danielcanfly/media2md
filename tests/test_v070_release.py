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
