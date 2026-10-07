"""List and call the deejay routes on this machine or on Pixeltable Cloud.

    .venv/bin/python endpoints.py access
    .venv/bin/python endpoints.py list
    .venv/bin/python endpoints.py test
    .venv/bin/python endpoints.py test --upload

    .venv/bin/python endpoints.py access --cloud pxt://org:db
    .venv/bin/python endpoints.py list --cloud pxt://org:db
    .venv/bin/python endpoints.py test --cloud pxt://org:db

Commands use the API key from the PIXELTABLE_API_KEY environment variable.
The script never prints that value. A local service call sends no key.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PXT = ROOT / '.venv' / 'bin' / 'pxt'
LOCAL = '/deejay'
CLIPS = ('8A.wav', '11A.wav', '9A.wav')
MATCH_SENTENCES = (
    'the track on the same Camelot T',
    'a track two steps away on the wheel',
)


def pxt_bin() -> str:
    if PXT.is_file():
        return str(PXT)
    return 'pxt'


def catalog(cloud: str | None) -> str:
    if not cloud:
        return LOCAL
    db = cloud.rstrip('/')
    if db.endswith('/deejay'):
        return db
    return f'{db}/deejay'


def service(target: str) -> dict:
    proc = subprocess.run(
        [pxt_bin(), 'service', 'list', target, '--json'],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr or proc.stdout)
        raise SystemExit(proc.returncode)
    rows = json.loads(proc.stdout or '[]')
    found = next((row for row in rows if row.get('name') == 'deejay'), None)
    if found is None or not found.get('endpoint'):
        sys.stderr.write(f'No deejay service is running at {target}.\n')
        raise SystemExit(1)
    return found


def api_key(cloud: str | None) -> str | None:
    if not cloud:
        return None
    return os.environ.get('PIXELTABLE_API_KEY') or None


def request(
    url: str,
    key: str | None,
    method: str = 'GET',
    body: dict | None = None,
    file: Path | None = None,
    title: str | None = None,
):
    headers = {}
    data = None
    if key:
        headers['X-api-key'] = key
    if file is not None:
        boundary = '----deejay'
        payload = (
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="audio"; filename="{file.name}"\r\n'
            f'Content-Type: audio/wav\r\n\r\n'
        ).encode()
        payload += file.read_bytes()
        if title:
            payload += (
                f'\r\n--{boundary}\r\n'
                f'Content-Disposition: form-data; name="given_title"\r\n\r\n'
                f'{title}'
            ).encode()
        payload += f'\r\n--{boundary}--\r\n'.encode()
        headers['content-type'] = f'multipart/form-data; boundary={boundary}'
        data = payload
    elif body is not None:
        headers['content-type'] = 'application/json'
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            parsed = json.loads(raw) if raw else {'error': exc.reason}
        except json.JSONDecodeError:
            parsed = {'error': raw or exc.reason}
        return exc.code, parsed


def live_routes(base: str, key: str | None) -> list[tuple[str, str]]:
    status, spec = request(f'{base}/openapi.json', key)
    if status == 200 and isinstance(spec, dict):
        found = []
        for path, methods in spec.get('paths', {}).items():
            for method in methods:
                if method in ('get', 'post', 'put', 'delete'):
                    found.append((method.upper(), path))
        found.sort(key=lambda item: (item[1], item[0]))
        if found:
            return found
    return []


def declared_routes(info: dict) -> list[tuple[str, str]]:
    routes = []
    for route in info.get('spec', {}).get('routes', []):
        routes.append((route.get('method', ''), route.get('path', '')))
    if ('POST', '/match') not in routes:
        routes.append(('POST', '/match'))
    return routes


def cmd_access(base: str) -> None:
    print(base)
    print(f'{base}/docs')


def cmd_list(base: str, info: dict, key: str | None) -> None:
    cmd_access(base)
    routes = live_routes(base, key) or declared_routes(info)
    for method, path in routes:
        print(f'{method:6} {path}')


def pick_track(rows: list[dict]) -> dict | None:
    for row in rows:
        if row.get('camelot') == '9A':
            return row
    return rows[-1] if rows else None


def show_tracks(rows: list[dict]) -> None:
    if not rows:
        print('tracks: none')
        return
    print(f'tracks: {len(rows)}')
    for row in rows:
        print(f"  {row.get('camelot')}  {row.get('bpm')}  {row.get('genre')}  {row.get('id')}")


def cmd_test(base: str, key: str | None, upload: bool) -> None:
    if upload:
        for name in CLIPS:
            path = ROOT / 'testdata' / name
            status, row = request(f'{base}/tracks', key, method='POST', file=path, title=path.stem)
            print(f'upload {name}: {status} {row.get("title")} {row.get("camelot")} {row.get("id")}')
    status, listed = request(f'{base}/tracks', key)
    if status != 200:
        print(f'GET /tracks: {status}')
        print(json.dumps(listed, indent=2)[:1000])
        raise SystemExit(1)
    rows = listed.get('rows') or []
    show_tracks(rows)
    track = pick_track(rows)
    if track is None:
        print('No track to test. Run the same command with --upload.')
        return
    mix_body = {
        'track_id': track['id'],
        'camelot': track['camelot'],
        'bpm': track['bpm'],
        'genre_family': track['genre_family'],
        'genre': track['genre'],
        'phrase_count': track['phrase_count'],
        'key_score': track['key_score'],
        'key_uncertain': track['key_uncertain'],
        'genre_uncertain': track['genre_uncertain'],
    }
    status, mix = request(f'{base}/mixable', key, method='POST', body=mix_body)
    print(f'POST /mixable for {track.get("camelot")}: {status}')
    for row in mix.get('rows') or []:
        print(f"  {row.get('list_name')}  {row.get('other_camelot')}  {row.get('key_kind')}")
    if status == 200 and not mix.get('rows'):
        print('  no rows')
    for sentence in MATCH_SENTENCES:
        status, match = request(
            f'{base}/match',
            key,
            method='POST',
            body={'track_id': track['id'], 'request': sentence},
        )
        chosen = (match.get('match') or {}).get('other_camelot') if isinstance(match, dict) else None
        reason = match.get('reason') if isinstance(match, dict) else match
        print(f'POST /match {status}: {sentence}')
        print(f'  {chosen or "no match"}  {reason}')


def main() -> None:
    parser = argparse.ArgumentParser(description='Access, list, or test the deejay routes.')
    parser.add_argument('command', choices=('access', 'list', 'test'))
    parser.add_argument('--cloud', metavar='pxt://org:db', help='hosted database, with no catalog path')
    parser.add_argument('--upload', action='store_true', help='insert testdata/8A.wav, 11A.wav, and 9A.wav before the test')
    args = parser.parse_args()

    if args.cloud and not os.environ.get('PIXELTABLE_API_KEY'):
        print('PIXELTABLE_API_KEY is unset. Commands use that variable, so these calls were not made.')
        raise SystemExit(1)

    target = catalog(args.cloud)
    info = service(target)
    base = info['endpoint'].rstrip('/')
    key = api_key(args.cloud)

    if args.command == 'access':
        cmd_access(base)
    elif args.command == 'list':
        cmd_list(base, info, key)
    else:
        cmd_test(base, key, args.upload)


if __name__ == '__main__':
    main()
