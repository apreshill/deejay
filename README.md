# deejay

Deejay is a catalog of songs for a DJ, built on Pixeltable. You upload a track. The new row comes back with its BPM, Camelot key, genre, loudness, and beat grid. The track is also split into phrases of 8 bars. You can ask which tracks already in the catalog mix with that one. A mixable track is on the same Camelot T and in the same tempo bucket or a neighboring one. It is also in the same genre family. You can send a sentence and get one track from that set. For a mixable pair, you can render one phrase of the handoff and play it. The original song stays its own file.

The full spec is [`spec/deejay-spec.md`](spec/deejay-spec.md). The DJ knowledge is in [`notes`](notes). The build phases for a coding agent are in [`AGENTS.md`](AGENTS.md).

## Environment

You need Python 3.11 or newer and `pixeltable[serve]` 0.7.14. The app also needs these packages.

- `librosa`, for tempo, beats, key, and time stretch
- `pedalboard`, for pitch shift, filters, and effects on the sample
- `transformers` and `torch`, for genre
- `openai`, for the sentence match

The install is several gigabytes, mostly `torch`. Install before you start the service.

The project needs a lockfile at its root, because `pxt db update` builds the hosted image from that file. This repo already has `uv.lock`. In this repo, install from that file.

```bash
uv sync
source .venv/bin/activate
```

The blocks below are for a new project that does not have a lockfile yet.

With uv, the lockfile is `uv.lock`.

```bash
uv init --bare
uv add 'pixeltable[serve]==0.7.14' librosa pedalboard transformers torch openai
source .venv/bin/activate
```

With venv and pip, the lockfile is `requirements.txt`.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install 'pixeltable[serve]==0.7.14' librosa pedalboard transformers torch openai
pip freeze > requirements.txt
```

With conda, the lockfile is `requirements.txt`.

```bash
conda create -n deejay python=3.12 -y
conda activate deejay
pip install 'pixeltable[serve]==0.7.14' librosa pedalboard transformers torch openai
pip freeze > requirements.txt
```

Make sure `pxt` is the one you installed. Another venv or a conda base on your PATH can shadow it.

```bash
which pxt
pxt --version
```

`pxt --version` should print `pxt 0.7.14`.

The first time you classify a genre, the app downloads the `laion/larger_clap_music` model.

## Endpoints

The same routes run on this machine and on Pixeltable Cloud. `endpoints.py` prints the address, lists the routes, and calls them.

On this machine the catalog is `/deejay`. A local call sends no Pixeltable API key. If the service is not running yet, start it, then list it.

```bash
pxt schema update app.py /deejay
pxt service update app.py /deejay -f
.venv/bin/python endpoints.py access
.venv/bin/python endpoints.py list
.venv/bin/python endpoints.py test
```

`access` prints the service URL and the docs page at `/docs`. Open that page in a browser to run a call from the form. `list` prints each route the server is serving. `test` loads the tracks, asks `/mixable` about the `9A` clip, and sends both `/match` sentences.

`pxt service list /deejay` prints `POST /tracks`, `GET /tracks`, `POST /mixable`, and `POST /samples`. `POST /match` is a custom route. It shows on the docs page and in `endpoints.py list`.

Add `--upload` to insert `testdata/8A.wav`, then `testdata/11A.wav`, then `testdata/9A.wav` before the test. You do not type BPM or key. A good test shows one mixable row, the `8A` clip as a fifth, and no key-sync row. The sentence "the track on the same Camelot T" matches `8A`. The sentence "a track two steps away on the wheel" matches nothing.

In the cloud, pass the database URI with no catalog path. `pxt org list` prints your org slug as the first word. The service lives at `pxt://<org>:<db>/deejay`. Commands use the API key from the `PIXELTABLE_API_KEY` environment variable. That value is what these commands send, in place of the key in your home Pixeltable config. A cloud HTTP call sends it as the `X-api-key` header. If the variable is unset, `endpoints.py` does not call the service. Keep the key out of the repo.

```bash
.venv/bin/python endpoints.py access --cloud pxt://<org>:<db>
.venv/bin/python endpoints.py list --cloud pxt://<org>:<db>
.venv/bin/python endpoints.py test --cloud pxt://<org>:<db>
```

`/match` calls the model only when `OPENAI_API_KEY` is set on the service. Keep that key out of the repo too. If it is unset, `/match` returns no match and the reason says the key is not set.

## Hear the files

`pxt rows` prints a file path for stored audio. Open a path to play it.

```bash
pxt rows /deejay/tracks --cols id,title,bpm,bucket,camelot,audio
pxt rows /deejay/phrases --cols id,phrase_index,start,end,loudness,energy_change,phrase_audio
pxt rows /deejay/samples --cols id,track_a_id,track_b_id,reason,preview
```

For the hosted tables, use the same commands with `pxt://<org>:<db>/deejay` in place of `/deejay`.

`audio` is the song you uploaded. `phrase_audio` is one phrase. `preview` is the sample.

`pxt dashboard` opens a read-only view of the local tables. Open `deejay`, then `tracks`, and play `audio`.

## Licenses

`pedalboard` is GPL-3.0. Check that before you distribute this project.

## Sign in

You need an account only for the cloud deploy in phase 3. `pxt login` signs this machine in to Pixeltable Cloud. `pxt org list` prints your org slug as the first word.

```bash
pxt login
pxt whoami
pxt org list
```
