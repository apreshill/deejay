"""Feature UDFs, the key relation, the phrase iterator, and the sample preview."""

import functools
import json
from pathlib import Path
from typing import Iterator, TypedDict

import numpy as np
import pixeltable as pxt
from pixeltable.utils.local_store import TempStore

GENRE_FAMILY: dict[str, str] = {
    'house': 'House',
    'deep house': 'House',
    'tech house': 'House',
    'disco': 'House',
    'techno': 'Techno',
    'trance': 'Techno',
    'drum and bass': 'Bass',
    'dubstep': 'Bass',
    'UK garage': 'Bass',
    'hip hop': 'Urban',
    'R&B': 'Urban',
    'afrobeats': 'Urban',
    'reggaeton': 'Urban',
    'pop': 'Pop',
    'ambient': 'Chill',
    'downtempo': 'Chill',
}
GENRE_LABELS: list[str] = list(GENRE_FAMILY)

# Camelot numbers for pitch classes starting at C.
MAJOR_FROM_C = [8, 3, 10, 5, 12, 7, 2, 9, 4, 11, 6, 1]
MINOR_FROM_C = [5, 12, 7, 2, 9, 4, 11, 6, 1, 8, 3, 10]
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
PHRASE_BEATS = 32


class Grid(TypedDict):
    audible_start: float
    audible_end: float
    bpm: float
    bucket: str
    beat_times: list[float]
    phrase_seconds: float
    phrase_count: int


class KeyEstimate(TypedDict):
    camelot: str
    key_runner_up: str
    key_score: float
    key_margin: float


class GenreEstimate(TypedDict):
    genre: str
    genre_runner_up: str
    genre_score: float
    genre_family: str


class KeyRelation(TypedDict):
    related: bool
    same_t: bool
    kind: str
    shift_semitones: int
    shift_track: str
    list_name: str
    list_rank: int
    rank: int


class PhraseRow(TypedDict):
    phrase_index: int
    section_index: int
    start: float
    end: float
    phrase_audio: pxt.Audio
    energy_change: float | None


class Preview(TypedDict):
    audio: pxt.Audio | None
    reason: str


def bucket_label(bpm: float) -> str:
    start = int(bpm // 5) * 5
    return f'{start}\u2013{start + 4}'


def _load(path: str) -> tuple[np.ndarray, int]:
    import librosa

    y, sr = librosa.load(path, sr=None, mono=True)
    return y, int(sr)


def _write_wav(y: np.ndarray, sr: int) -> str:
    import soundfile as sf

    path = str(TempStore.create_path(extension='.wav'))
    sf.write(path, np.asarray(y, dtype=np.float32), sr)
    return path


def _trim(y: np.ndarray, sr: int) -> tuple[float, float, np.ndarray]:
    import librosa

    trimmed, index = librosa.effects.trim(y, top_db=40)
    start = float(index[0]) / sr
    end = float(index[1]) / sr
    if len(trimmed) == 0:
        return 0.0, float(len(y)) / sr, y
    return start, end, trimmed


def _beat_grid(y: np.ndarray, sr: int) -> tuple[float, list[float]]:
    import librosa

    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units='time', trim=False)
    if isinstance(tempo, np.ndarray):
        bpm = float(tempo.reshape(-1)[0]) if tempo.size else 0.0
    else:
        bpm = float(tempo)
    times = [float(t) for t in np.asarray(beats).reshape(-1)]
    return bpm, times


def phrase_spans(beat_times: list[float]) -> list[tuple[float, float]]:
    """Full phrases of 32 beats. A shorter tail is dropped."""
    if len(beat_times) < PHRASE_BEATS:
        return []
    gaps = [beat_times[i + 1] - beat_times[i] for i in range(len(beat_times) - 1)]
    step = float(np.median(gaps)) if gaps else 0.5
    spans: list[tuple[float, float]] = []
    start_at = 0
    while start_at + PHRASE_BEATS <= len(beat_times):
        start = float(beat_times[start_at])
        end_at = start_at + PHRASE_BEATS
        if end_at < len(beat_times):
            end = float(beat_times[end_at])
        else:
            end = float(beat_times[end_at - 1]) + step
        if end > start:
            spans.append((start, end))
        start_at += PHRASE_BEATS
    return spans


def _slice(y: np.ndarray, sr: int, start: float, end: float) -> np.ndarray:
    a = max(0, int(start * sr))
    b = min(len(y), int(end * sr))
    if b <= a:
        return np.zeros(1, dtype=np.float32)
    return y[a:b]


def loudness_of(y: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(np.square(y)))) if len(y) else 0.0
    return float(20.0 * np.log10(rms + 1e-12))


def low_end_of(y: np.ndarray, sr: int) -> float:
    import librosa

    if len(y) < 256:
        return 0.0
    spectrum = np.abs(librosa.stft(y))
    freqs = librosa.fft_frequencies(sr=sr)
    total = float(np.square(spectrum).sum())
    if total <= 0:
        return 0.0
    low = float(np.square(spectrum[freqs < 150]).sum())
    return low / total


def _same_t(a: str, b: str) -> str | None:
    if a == b:
        return 'same'
    na, la = int(a[:-1]), a[-1]
    nb, lb = int(b[:-1]), b[-1]
    if na == nb and la != lb:
        return 'relative'
    if la == lb and (abs(na - nb) == 1 or {na, nb} == {1, 12}):
        return 'fifth'
    return None


def _shift_camelot(code: str, semitones: int) -> str:
    number, letter = int(code[:-1]), code[-1]
    table = MINOR_FROM_C if letter == 'A' else MAJOR_FROM_C
    pitch = table.index(number)
    return f'{table[(pitch + semitones) % 12]}{letter}'


def relate(caller: str, other: str) -> KeyRelation:
    """How `other` sits against `caller`. A 1-semitone shift is applied to `other`."""
    kind = _same_t(caller, other)
    if kind is not None:
        rank = {'same': 0, 'relative': 1, 'fifth': 2}[kind]
        return {
            'related': True,
            'same_t': True,
            'kind': kind,
            'shift_semitones': 0,
            'shift_track': '',
            'list_name': 'mixable',
            'list_rank': 0,
            'rank': rank,
        }
    for direction in (1, -1):
        shifted = _shift_camelot(other, direction)
        if _same_t(caller, shifted) is not None:
            return {
                'related': True,
                'same_t': False,
                'kind': 'sync',
                'shift_semitones': direction,
                'shift_track': 'other',
                'list_name': 'key_sync',
                'list_rank': 1,
                'rank': 3,
            }
    return {
        'related': False,
        'same_t': False,
        'kind': 'none',
        'shift_semitones': 0,
        'shift_track': '',
        'list_name': 'none',
        'list_rank': 2,
        'rank': 4,
    }


def _scores_from_pipeline(result: object) -> dict[str, float]:
    if isinstance(result, dict) and 'labels' in result and 'scores' in result:
        return {str(label): float(score) for label, score in zip(result['labels'], result['scores'])}
    if isinstance(result, list):
        return {str(item['label']): float(item['score']) for item in result}
    raise TypeError(f'unexpected genre pipeline result: {type(result).__name__}')


@functools.cache
def _genre_pipe():
    from transformers import pipeline

    return pipeline('zero-shot-audio-classification', model='laion/larger_clap_music')


def _middle_windows(y: np.ndarray, sr: int, start: float, end: float) -> list[np.ndarray]:
    """Three windows from the middle of the audible span, 10 seconds when it fits."""
    duration = end - start
    if duration <= 0 or len(y) == 0:
        return []
    win = min(10.0, duration)
    mid = (start + end) / 2.0
    edges = [mid - 15.0, mid - 5.0, mid + 5.0] if duration >= 30.0 else [mid - win]
    clips: list[np.ndarray] = []
    for edge in edges:
        s = min(max(edge, start), end - 0.25)
        e = min(end, s + win)
        clip = _slice(y, sr, s, e)
        if len(clip) > int(0.25 * sr):
            clips.append(clip)
    return clips[:3] or [_slice(y, sr, start, end)]


def _media_path(value: object) -> str:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        for key in ('src', 'path', 'localpath', 'url'):
            found = value.get(key)
            if isinstance(found, str) and found:
                return found
    raise RuntimeError(f'query result did not hand over an audio file: {value!r}'[:500])


def _as_row(value: object) -> dict:
    if isinstance(value, list):
        if not value:
            raise RuntimeError('track lookup returned no row')
        value = value[0]
    if not isinstance(value, dict):
        raise RuntimeError(f'track lookup returned {type(value).__name__}')
    return value


def _analyze(path: str) -> Grid:
    y, sr = _load(path)
    audible_start, audible_end, trimmed = _trim(y, sr)
    bpm, beat_times = _beat_grid(trimmed, sr)
    beat_times = [round(audible_start + t, 6) for t in beat_times if audible_start + t <= audible_end + 1e-3]
    phrase_seconds = (PHRASE_BEATS * 60.0 / bpm) if bpm > 0 else 0.0
    return {
        'audible_start': audible_start,
        'audible_end': audible_end,
        'bpm': bpm,
        'bucket': bucket_label(bpm) if bpm > 0 else '0\u20134',
        'beat_times': beat_times,
        'phrase_seconds': phrase_seconds,
        'phrase_count': len(beat_times) // PHRASE_BEATS,
    }


def _estimate_key(path: str) -> KeyEstimate:
    import librosa

    y, sr = _load(path)
    _, _, trimmed = _trim(y, sr)
    harmonic = librosa.effects.harmonic(trimmed)
    chroma = librosa.feature.chroma_cqt(y=harmonic, sr=sr).mean(axis=1)
    scored: list[tuple[float, str]] = []
    for pitch in range(12):
        rotated_major = np.roll(MAJOR_PROFILE, pitch)
        rotated_minor = np.roll(MINOR_PROFILE, pitch)
        major_code = f'{MAJOR_FROM_C[pitch]}B'
        minor_code = f'{MINOR_FROM_C[pitch]}A'
        scored.append((_corr(chroma, rotated_major), major_code))
        scored.append((_corr(chroma, rotated_minor), minor_code))
    scored.sort(key=lambda item: item[0], reverse=True)
    best, runner = scored[0], scored[1]
    return {
        'camelot': best[1],
        'key_runner_up': runner[1],
        'key_score': best[0],
        'key_margin': best[0] - runner[0],
    }


def _corr(chroma: np.ndarray, profile: np.ndarray) -> float:
    if float(np.std(chroma)) < 1e-8 or float(np.std(profile)) < 1e-8:
        return 0.0
    return float(np.corrcoef(chroma, profile)[0, 1])


def _estimate_genre(path: str) -> GenreEstimate:
    y, sr = _load(path)
    start, end, _ = _trim(y, sr)
    totals = {label: 0.0 for label in GENRE_LABELS}
    clips = _middle_windows(y, sr, start, end)
    pipe = _genre_pipe()
    for clip in clips:
        scores = _scores_from_pipeline(
            pipe({'raw': np.asarray(clip, dtype=np.float32), 'sampling_rate': sr}, candidate_labels=GENRE_LABELS)
        )
        for label, score in scores.items():
            if label in totals:
                totals[label] += score
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    best, runner = ranked[0], ranked[1]
    count = max(len(clips), 1)
    return {
        'genre': best[0],
        'genre_runner_up': runner[0],
        'genre_score': best[1] / count,
        'genre_family': GENRE_FAMILY[best[0]],
    }


@pxt.udf
def resolve_title(given_title: str | None, audio: pxt.Audio) -> str:
    if given_title and given_title.strip():
        return given_title.strip()
    return Path(str(audio)).name


@pxt.udf
def analyze_grid(audio: pxt.Audio) -> Grid:
    return _analyze(str(audio))


@pxt.udf
def detect_key(audio: pxt.Audio) -> KeyEstimate:
    return _estimate_key(str(audio))


@pxt.udf
def classify_genre(audio: pxt.Audio) -> GenreEstimate:
    return _estimate_genre(str(audio))


@pxt.udf
def loudness_db(audio: pxt.Audio) -> float:
    y, sr = _load(str(audio))
    _, _, trimmed = _trim(y, sr)
    return loudness_of(trimmed)


@pxt.udf
def phrase_loudness(audio: pxt.Audio) -> float:
    y, _sr = _load(str(audio))
    return loudness_of(y)


@pxt.udf
def phrase_low_end(audio: pxt.Audio) -> float:
    y, sr = _load(str(audio))
    return low_end_of(y, sr)


@pxt.udf
def key_is_uncertain(margin: float, best: str, runner_up: str) -> bool:
    return margin < 0.05 and _same_t(best, runner_up) is None


@pxt.udf
def genre_is_uncertain(score: float, best: str, runner_up: str) -> bool:
    return score < 0.4 and GENRE_FAMILY.get(best) != GENRE_FAMILY.get(runner_up)


@pxt.udf
def key_relation(caller: str, other: str) -> KeyRelation:
    return relate(caller, other)


@pxt.udf
def buckets_neighbor(bpm_a: float, bpm_b: float) -> bool:
    if bpm_a <= 0 or bpm_b <= 0:
        return False
    return abs(int(bpm_a // 5) - int(bpm_b // 5)) <= 1


@pxt.udf
def tempos_match(bpm_a: float, bpm_b: float) -> bool:
    return buckets_neighbor(bpm_a, bpm_b)


@pxt.udf
def bpm_bucket(bpm: float) -> str:
    return bucket_label(bpm) if bpm > 0 else '0\u20134'


@pxt.udf
def genre_rank(caller_genre: str, other_genre: str) -> int:
    return 0 if caller_genre == other_genre else 1


@pxt.iterator
def phrase_splitter(
    audio: pxt.Audio,
    beat_times: list[float],
    audible_start: float,
    audible_end: float,
) -> Iterator[PhraseRow]:
    del audible_start, audible_end  # bounds are already applied to beat_times
    y, sr = _load(str(audio))
    previous: float | None = None
    for index, (start, end) in enumerate(phrase_spans(list(beat_times))):
        clip = _slice(y, sr, start, end)
        level = loudness_of(clip)
        change = None if previous is None else level - previous
        previous = level
        yield {
            'phrase_index': index,
            'section_index': index // 2,
            'start': start,
            'end': end,
            'phrase_audio': _write_wav(clip, sr),
            'energy_change': change,
        }


def _fail(reason: str) -> Preview:
    return {'audio': None, 'reason': reason}


@pxt.udf
def render_preview(track_a: pxt.Json, track_b: pxt.Json) -> Preview:
    import librosa
    import pedalboard

    try:
        first = _as_row(track_a)
        second = _as_row(track_b)
    except RuntimeError as exc:
        return _fail(str(exc))
    path_a = _media_path(first.get('audio'))
    path_b = _media_path(second.get('audio'))
    beats_a = [float(t) for t in first.get('beat_times') or []]
    beats_b = [float(t) for t in second.get('beat_times') or []]
    if len(beats_a) < PHRASE_BEATS or len(beats_b) < PHRASE_BEATS:
        return _fail('fewer than 32 beats')
    relation = relate(str(first['camelot']), str(second['camelot']))
    if not relation['related']:
        return _fail('key')
    if not buckets_neighbor(float(first['bpm']), float(second['bpm'])):
        return _fail('tempo')
    if first.get('genre_family') != second.get('genre_family'):
        return _fail('genre')

    spans_a = phrase_spans(beats_a)
    spans_b = phrase_spans(beats_b)
    y_a, sr = _load(path_a)
    y_b, sr_b = _load(path_b)
    if sr_b != sr:
        y_b = librosa.resample(y_b, orig_sr=sr_b, target_sr=sr)
    outgoing = _slice(y_a, sr, *spans_a[-1])
    incoming = _slice(y_b, sr, *spans_b[0])
    rate = float(first['bpm']) / float(second['bpm'])
    if rate > 0 and abs(rate - 1.0) > 1e-3:
        incoming = librosa.effects.time_stretch(incoming, rate=rate)
    shift = int(relation['shift_semitones'])
    if shift != 0:
        incoming = _through(incoming, sr, pedalboard.Pedalboard([pedalboard.PitchShift(semitones=shift)]))
    outgoing = _through(
        outgoing,
        sr,
        pedalboard.Pedalboard([
            pedalboard.HighpassFilter(cutoff_frequency_hz=200),
            pedalboard.Delay(delay_seconds=0.25, feedback=0.15, mix=0.25),
            pedalboard.Reverb(room_size=0.2, damping=0.5, wet_level=0.15, dry_level=0.85),
        ]),
    )
    length = min(len(outgoing), len(incoming))
    mixed = outgoing[:length] + incoming[:length]
    peak = float(np.max(np.abs(mixed))) if length else 1.0
    if peak > 1.0:
        mixed = mixed / peak
    return {'audio': _write_wav(mixed, sr), 'reason': ''}


def _through(y: np.ndarray, sr: int, board: object) -> np.ndarray:
    audio = np.asarray(y, dtype=np.float32).reshape(1, -1)
    out = board(audio, sr)  # type: ignore[operator]
    return np.asarray(out, dtype=np.float32).reshape(-1)


@pxt.udf
def choose_match(sentence: str, candidates_json: str) -> str:
    """Ask gpt-4o-mini to pick one candidate id, or none."""
    from openai import OpenAI

    client = OpenAI()
    response = client.chat.completions.create(
        model='gpt-4o-mini',
        temperature=0,
        response_format={'type': 'json_object'},
        messages=[
            {
                'role': 'system',
                'content': (
                    'You choose one DJ mix candidate. The list already passed key, tempo, and genre checks. '
                    'Reply with JSON only: {"track_id": "<id from the list, or empty>", "reason": "<one sentence>"}. '
                    'Copy track_id from the list. If none of the candidates fit the request, use an empty track_id. '
                    'Do not invent an id.'
                ),
            },
            {
                'role': 'user',
                'content': json.dumps({'request': sentence, 'candidates': json.loads(candidates_json)}),
            },
        ],
    )
    content = response.choices[0].message.content or '{}'
    return content
