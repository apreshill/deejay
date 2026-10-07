# deejay

Deejay is a catalog of songs. You add a track. Pixeltable computes the Camelot key, the BPM, the genre, the loudness, and the beat grid, and it stores the original file. You then ask which songs already in the catalog can mix with that one. The answer is a list, with the key relationship, both tempos, and the tempo ratio. You can also send a sentence, such as "something darker in the same key, a little faster," and get one track from that list. For a pair, you can render one phrase of the handoff and play it.

This is not a playlist reorder. A song stays in the catalog even when nothing else mixes with it.

The DJ rules are in [`notes`](notes). The full schema is in [`spec/deejay-spec.md`](spec/deejay-spec.md).

## Add a song

A row is a file. You do not type the BPM or the key. The upload response is the new row, with those values filled in.

Start the local service once.

```bash
uv sync
source .venv/bin/activate
pxt schema update app.py /deejay
pxt service update app.py /deejay -f
export URL=$(.venv/bin/python endpoints.py access | head -1)
echo "$URL"
```

`echo` prints an address like `http://127.0.0.1:56258`. Open `$URL/docs` in a browser if you want the form for each route. A local call sends no API key.

This machine already has the three clips in `/deejay`. Their titles are uuid filenames, because those uploads left `given_title` off. Their Camelot keys are `8A`, `11A`, and `9A`. If `GET $URL/tracks` shows those keys, skip the upload and run the query in the next section.

Add the three clips when the list is empty. The first upload downloads the genre model, so it is the slow one.

```bash
curl -s -F "audio=@testdata/8A.wav" -F "given_title=8A" "$URL/tracks" -o /tmp/8A.json
curl -s -F "audio=@testdata/11A.wav" -F "given_title=11A" "$URL/tracks" -o /tmp/11A.json
curl -s -F "audio=@testdata/9A.wav" -F "given_title=9A" "$URL/tracks" -o /tmp/9A.json
```

`given_title` is the name you will see later. If you leave it off, the title is a uuid filename. Open `/tmp/9A.json`. The fields you need for the next call are `id`, `camelot`, `bpm`, `genre`, `genre_family`, `phrase_count`, `key_score`, `key_uncertain`, and `genre_uncertain`.

To add any other song, use the same call with your file and a title.

```bash
curl -s -F "audio=@/path/to/song.wav" -F "given_title=Song name" "$URL/tracks"
```

`GET $URL/tracks` lists every row already stored.

## Ask which songs mix

`POST /mixable` is the query. You send one song that is already stored. You get back the other songs that can mix with it, and a second list for a one-semitone key sync.

This loads the catalog, picks the row whose Camelot key is `9A`, and prints the matches. Run the upload above first if `GET /tracks` is empty.

```bash
.venv/bin/python - <<'PY'
import json, os, urllib.request
base = os.environ["URL"].rstrip("/")

def call(path, body=None):
    data = None if body is None else json.dumps(body).encode()
    headers = {} if body is None else {"content-type": "application/json"}
    req = urllib.request.Request(base + path, data=data, headers=headers)
    return json.load(urllib.request.urlopen(req))

rows = call("/tracks").get("rows") or []
row = next((item for item in rows if item.get("camelot") == "9A"), None)
if row is None:
    raise SystemExit("No 9A row yet. Add testdata/9A.wav first.")
body = {
    "track_id": row["id"],
    "camelot": row["camelot"],
    "bpm": row["bpm"],
    "genre_family": row["genre_family"],
    "genre": row["genre"],
    "phrase_count": row["phrase_count"],
    "key_score": row["key_score"],
    "key_uncertain": row["key_uncertain"],
    "genre_uncertain": row["genre_uncertain"],
}
for match in call("/mixable", body).get("rows") or []:
    print(match.get("list_name"), match.get("other_title"), match.get("other_camelot"), match.get("key_kind"))
PY
```

With these three clips, that prints one line. `mixable`, then the stored title of the `8A` clip, then `8A`, then `fifth`. `11A` is absent. One semitone is not enough to put `11A` on the same Camelot T as `9A`. The title is `8A` when the upload set `given_title`. It is a uuid filename when the upload left the title off.

The `body` in that script is what you paste into `$URL/docs` under `POST /mixable`.

## Ask in a sentence

`POST /match` takes the track id and a sentence. It looks up that row, runs the same mix list, and returns one track from it.

```bash
.venv/bin/python - <<'PY'
import json, os, urllib.request
base = os.environ["URL"].rstrip("/")
listed = json.load(urllib.request.urlopen(base + "/tracks"))
row = next(item for item in listed["rows"] if item.get("camelot") == "9A")
body = {"track_id": row["id"], "request": "the track on the same Camelot T"}
req = urllib.request.Request(
    base + "/match",
    data=json.dumps(body).encode(),
    headers={"content-type": "application/json"},
)
print(urllib.request.urlopen(req).read().decode())
PY
```

That sentence should return `8A`. The sentence `a track two steps away on the wheel` should return no match. A sentence can only choose among songs already in the catalog.

`/match` calls `gpt-4o-mini`. Set `OPENAI_API_KEY` in the environment before you start the local service, and keep the key out of the repo. If it is unset, the route returns no match and the reason says so.

## Hear one phrase of the handoff

`POST /samples` takes the two ids. The response includes a URL for the audio.

```bash
.venv/bin/python - <<'PY'
import json, os, urllib.request
base = os.environ["URL"].rstrip("/")
rows = json.load(urllib.request.urlopen(base + "/tracks"))["rows"]
by_key = {item.get("camelot"): item["id"] for item in rows}
body = {"track_a_id": by_key["8A"], "track_b_id": by_key["9A"]}
req = urllib.request.Request(
    base + "/samples",
    data=json.dumps(body).encode(),
    headers={"content-type": "application/json"},
)
print(urllib.request.urlopen(req).read().decode())
PY
```

An empty `reason` means the preview was written. Open the `preview` URL.

One command does the three uploads, `/mixable`, and both sentences.

```bash
.venv/bin/python endpoints.py test --upload
```

## What a mix is

Two tracks mix when both have at least 32 beats, they sit on the same Camelot T, and their tempos are in the same 5 BPM bucket or a neighboring one. That is under about 10 BPM, close enough to match speed.

The same T means the same code, the same number with the other letter, or the next number on the wheel. `9A` with `8A` is a fifth. `8A` with `8B` is the relative key.

A second list is key sync. Tempo and length still hold. The keys are one semitone apart, and the sample pitch-shifts the incoming track by that one semitone. A shift of two semitones is not offered.

Genre is computed and shown. It does not block a pair. Hip hop is in the Urban family. House is in the House family. Those two can still come back together when the key and the tempo work. If you want one genre, ask for it in the sentence on `/match`. If nothing in the list has that genre, you get no match.

Each track is also split into phrases of 8 bars, which is 32 beats, counted from the first beat librosa finds. That first beat may not be bar 1 of the song. You can play each phrase. The sample uses the last phrase of the outgoing track and the first phrase of the incoming track.

## Routes

`pxt --version` should print `pxt 0.7.14`. `.venv/bin/python endpoints.py list` prints the routes.

- `POST /tracks` adds a song. The response is the new row.
- `GET /tracks` lists what is stored.
- `POST /mixable` takes that row and returns the other songs that mix, plus the key-sync list.
- `POST /match` takes the track id and a sentence.
- `POST /samples` takes two track ids and returns one phrase of the handoff.

`pxt service list` prints the first four. `POST /match` is on the same service. It shows on `$URL/docs` and in `$URL/openapi.json`.

## Hear a result

`pxt rows` prints a file path. Open it to play it.

```bash
pxt rows /deejay/tracks --cols id,title,bpm,bucket,camelot,genre,audio
pxt rows /deejay/phrases --cols id,phrase_index,start,end,loudness,energy_change,phrase_audio
pxt rows /deejay/samples --cols id,track_a_id,track_b_id,reason,preview
```

`audio` is the song you uploaded. `phrase_audio` is one phrase. `preview` is the handoff. An empty preview means the pair failed a check, and `reason` says which one.

`pxt dashboard` opens the local tables. Open `deejay`, then `tracks`, and play `audio`.

## Same calls on Pixeltable Cloud

The hosted service is already running.

```text
https://deejay-main.svc.pxt.run/deejay/deejay
```

`pxt://deejay:main` is the database address inside Pixeltable. It is not a page you open. The `https://` address above is the one you call.

A browser visit to that address sends no API key, so the page answers "Missing or invalid API key" even when the key is saved on your machine. Put the key in `PIXELTABLE_API_KEY` and send it on the request. `Authorization: Bearer` with the same key also works. Anyone with a valid key for this org can call it.

List the songs.

```bash
curl -s -H "X-api-key: $PIXELTABLE_API_KEY" \
  "https://deejay-main.svc.pxt.run/deejay/deejay/tracks"
```

Add a song the same way as locally. The header is the only extra piece. The first cloud upload loads the genre model inside the hosted database. This database has 1024 MB, and that load restarted the pod, so use the local URL above to see a match. The query below is the same call. It returns `8A` once an upload has finished.

```bash
curl -s -H "X-api-key: $PIXELTABLE_API_KEY" \
  -F "audio=@testdata/9A.wav" -F "given_title=9A" \
  "https://deejay-main.svc.pxt.run/deejay/deejay/tracks" -o /tmp/9A.json
```

Ask what mixes. This is the same query as the local one. It lists the catalog, picks the `9A` row, and prints the other songs.

```bash
.venv/bin/python - <<'PY'
import json, os, urllib.request
base = "https://deejay-main.svc.pxt.run/deejay/deejay"
key = os.environ["PIXELTABLE_API_KEY"]

def call(path, body=None):
    data = None if body is None else json.dumps(body).encode()
    headers = {"X-api-key": key}
    if body is not None:
        headers["content-type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, headers=headers)
    return json.load(urllib.request.urlopen(req))

rows = call("/tracks").get("rows") or []
row = next((item for item in rows if item.get("camelot") == "9A"), None)
if row is None:
    raise SystemExit("No 9A row yet. Add testdata/9A.wav with the upload above.")
body = {
    "track_id": row["id"],
    "camelot": row["camelot"],
    "bpm": row["bpm"],
    "genre_family": row["genre_family"],
    "genre": row["genre"],
    "phrase_count": row["phrase_count"],
    "key_score": row["key_score"],
    "key_uncertain": row["key_uncertain"],
    "genre_uncertain": row["genre_uncertain"],
}
for match in call("/mixable", body).get("rows") or []:
    print(match.get("list_name"), match.get("other_title"), match.get("other_camelot"), match.get("key_kind"))
PY
```

A sentence uses only the id from that same list.

```bash
.venv/bin/python - <<'PY'
import json, os, urllib.request
base = "https://deejay-main.svc.pxt.run/deejay/deejay"
key = os.environ["PIXELTABLE_API_KEY"]
req = urllib.request.Request(base + "/tracks", headers={"X-api-key": key})
rows = json.load(urllib.request.urlopen(req))["rows"]
row = next(item for item in rows if item.get("camelot") == "9A")
body = {"track_id": row["id"], "request": "the track on the same Camelot T"}
req = urllib.request.Request(
    base + "/match",
    data=json.dumps(body).encode(),
    headers={"content-type": "application/json", "X-api-key": key},
)
print(urllib.request.urlopen(req).read().decode())
PY
```

`/match` on the hosted service also needs `OPENAI_API_KEY` stored for the org, then a service restart.

```bash
pxt secret set pxt://deejay OPENAI_API_KEY=<your-openai-key>
pxt service restart pxt://deejay:main/deejay
```

The OpenAPI schema is at `https://deejay-main.svc.pxt.run/deejay/deejay/openapi.json` with the same header. That is the contract for a frontend.

One command lists the routes, or uploads the three clips and runs both questions, when `PIXELTABLE_API_KEY` is set.

```bash
.venv/bin/python endpoints.py list --cloud pxt://deejay:main
.venv/bin/python endpoints.py test --cloud pxt://deejay:main --upload
```

You add songs with the upload above. `GET /tracks` is how you see them. Ask `/mixable` with the `9A` row and the match is `8A`, a fifth.

To publish this app on your own org, create an account and an API key in [Pixeltable Cloud](https://docs.pixeltable.com). Put the key in `PIXELTABLE_API_KEY`, or in the `api_key` field under `[pixeltable]` in your home Pixeltable config. Commands use whichever is set. The environment variable wins. Keep the key out of this repo. Cloud does not connect to this GitHub repo. You publish `app.py` with the CLI.

```bash
pxt whoami
pxt org list
```

The first word from `pxt org list` is your org slug. Use the database `main` when that is the one your org already has. Add a hosted entry in `pyproject.toml` and leave the local entry unnamed.

```toml
[[tool.pixeltable.database]]
name = 'pxt://<org>:main'
```

Then publish, in this order. `<org>` is your slug.

```bash
pxt db update pxt://<org>:main -f
pxt schema update app.py pxt://<org>:main/deejay
pxt service update app.py pxt://<org>:main/deejay -f
pxt service list pxt://<org>:main/deejay
```

`pxt db update` uploads the project and builds the image from `uv.lock`. It does not insert songs, and it does not start HTTP. The first build takes several minutes because of `torch`. `pxt schema update` creates `tracks`, the `phrases` view, and `samples`. `pxt service update` starts the routes.

`pxt service list` prints the `https://` address. Use that the same way as the address above. Add the three clips with the upload curl and the key header, then send the `9A` row to `/mixable`.

Hosted rows use the same column list, with the cloud path.

```bash
pxt rows pxt://<org>:main/deejay/tracks --cols id,title,bpm,bucket,camelot,genre,audio
```

An insert runs the audio functions and the genre model in Python, as part of saving the row. Locally that Python runs on your machine. In the cloud it runs in the image `pxt db update` built from this repo. You do not compute the features in a separate step and then insert them. You do not type BPM or key. If a computed column fails, the insert stores nothing.

This app does not embed the audio. It stores the key, the tempo, the genre, and the phrases on the row. A sentence on `/match` can ask for a genre, a key, or a tempo among songs already in the catalog. It cannot find an artist who is not in the catalog.

A hosted database does not scale to zero when it is idle. The pods stay at the CPU, memory, disk, and worker count set for that database. You can sleep them yourself. Sleep stops the pods and keeps the data. Start wakes them.

```bash
pxt db stop pxt://<org>:main
pxt db start pxt://<org>:main
```

## License

`pedalboard` is GPL-3.0. Check that before you distribute this project.
