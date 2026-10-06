# deejay

A catalog of songs for a DJ, built on Pixeltable. You upload a track. The database computes its BPM, Camelot key, genre, loudness, and beat grid, and splits it into 8-bar phrases. It then tells you which tracks already in the catalog are mixable with it: keys on the same Camelot T, tempos close enough to match, and the same genre family. You can also send a sentence, and the service picks one track from that mixable set. For any mixable pair, it renders a one-phrase sample of the handoff you can play. The original song always stays its own file.

The full spec is [`spec/deejay-spec.md`](spec/deejay-spec.md). The DJ knowledge it follows is in [`notes`](notes). The build phases for a coding agent are in [`AGENTS.md`](AGENTS.md).

## Environment

You need Python 3.11 or newer and `pixeltable[serve]` 0.7.14. The app also needs:

- `librosa`, for tempo, beats, key, and time stretch
- `pedalboard`, for pitch shift, filters, and effects on the sample
- `transformers` and `torch`, for genre

The install is several gigabytes, mostly `torch`. Do it before you start.

The project needs a lockfile at its root, because `pxt db update` builds the hosted image from that file. Any manager below works.

uv (recommended), lockfile `uv.lock`:

```bash
uv init --bare
uv add 'pixeltable[serve]==0.7.14' librosa pedalboard transformers torch
source .venv/bin/activate
```

venv and pip, lockfile `requirements.txt`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install 'pixeltable[serve]==0.7.14' librosa pedalboard transformers torch
pip freeze > requirements.txt
```

conda, lockfile `requirements.txt`:

```bash
conda create -n deejay python=3.12 -y
conda activate deejay
pip install 'pixeltable[serve]==0.7.14' librosa pedalboard transformers torch
pip freeze > requirements.txt
```

Make sure `pxt` resolves to the one you installed (`which pxt`). Another venv or conda base on your PATH can shadow it. Confirm the version.

```bash
pxt --version    # pxt 0.7.14
```

The first genre run downloads the `laion/larger_clap_music` model.

## Licenses

`pedalboard` is GPL-3.0. Check that before you distribute this project.

## Sign in

You need an account only for the cloud deploy in phase 3. `pxt login` signs this machine in to Pixeltable Cloud. `pxt org list` prints your org slug as the first word.

```bash
pxt login
pxt whoami
pxt org list
```
