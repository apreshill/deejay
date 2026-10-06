"""Deejay catalog: tracks, phrases, mixable pairs, and one-phrase samples."""

import json
import os

import pixeltable as pxt
import pixeltable.functions as pxtf
from pixeltable.serving import FastAPIRouter
from pydantic import BaseModel

from features import (
    analyze_grid,
    bpm_bucket,
    choose_match,
    classify_genre,
    detect_key,
    genre_is_uncertain,
    key_is_uncertain,
    key_relation,
    keys_related,
    phrase_loudness,
    loudness_db,
    phrase_low_end,
    phrase_splitter,
    render_preview,
    resolve_title,
    tempos_match,
)

TableModel = pxt.model_base()


class Tracks(TableModel, name='tracks'):
    audio: pxt.Audio
    given_title: pxt.String | None
    id = pxt.Column(value=pxtf.uuid.uuid7().to_string(), primary_key=True)
    title = resolve_title(given_title, audio)
    meta = pxtf.audio.get_metadata(audio)
    duration = meta.streams[0].duration_seconds
    grid = analyze_grid(audio)
    audible_start = grid.audible_start
    audible_end = grid.audible_end
    bpm = grid.bpm
    bucket = grid.bucket
    beat_times = grid.beat_times
    phrase_seconds = grid.phrase_seconds
    phrase_count = grid.phrase_count
    key = detect_key(audio)
    camelot = key.camelot
    key_runner_up = key.key_runner_up
    key_score = key.key_score
    key_margin = key.key_margin
    key_uncertain = key_is_uncertain(key_margin, camelot, key_runner_up)
    genre_result = classify_genre(audio)
    genre = genre_result.genre
    genre_runner_up = genre_result.genre_runner_up
    genre_score = genre_result.genre_score
    genre_family = genre_result.genre_family
    genre_uncertain = genre_is_uncertain(genre_score, genre, genre_runner_up)
    loudness = loudness_db(audio)


class Phrases(
    TableModel,
    name='phrases',
    base=Tracks.select(
        Tracks.id,
        Tracks.title,
        Tracks.audio,
        Tracks.beat_times,
        Tracks.audible_start,
        Tracks.audible_end,
        Tracks.bpm,
    ),
    iterator=phrase_splitter(Tracks.audio, Tracks.beat_times, Tracks.audible_start, Tracks.audible_end),
):
    loudness = phrase_loudness(phrase_audio)
    low_end_energy = phrase_low_end(phrase_audio)


def mixable_query(
    table,
    track_id: str,
    camelot: str,
    bpm: float,
    genre_family: str,
    genre: str,
    phrase_count: int,
    key_score: float,
    key_uncertain: bool,
    genre_uncertain: bool,
):
    relation = key_relation(camelot, table.camelot)
    difference = pxtf.math.abs(table.bpm - bpm)
    # A live table call passes a Python int. The query route passes an expression.
    caller_has_phrase = phrase_count >= 1
    where = (
        (table.id != track_id)
        & (table.phrase_count >= 1)
        & tempos_match(bpm, table.bpm)
        & (table.genre_family == genre_family)
        & keys_related(camelot, table.camelot)
    )
    if isinstance(caller_has_phrase, bool):
        if not caller_has_phrase:
            where = (table.id != table.id) & where
    else:
        where = caller_has_phrase & where
    return (
        table.where(where)
        .order_by(difference)
        .select(
            other_id=table.id,
            other_title=table.title,
            list_name=relation.list_name,
            key_kind=relation.kind,
            shift_semitones=relation.shift_semitones,
            shift_track=relation.shift_track,
            caller_camelot=camelot,
            other_camelot=table.camelot,
            caller_bpm=bpm,
            other_bpm=table.bpm,
            caller_bucket=bpm_bucket(bpm),
            other_bucket=table.bucket,
            tempo_ratio=table.bpm / bpm,
            bpm_difference=difference,
            caller_genre=genre,
            other_genre=table.genre,
            caller_family=genre_family,
            other_family=table.genre_family,
            caller_key_score=key_score,
            other_key_score=table.key_score,
            caller_key_uncertain=key_uncertain,
            other_key_uncertain=table.key_uncertain,
            caller_genre_uncertain=genre_uncertain,
            other_genre_uncertain=table.genre_uncertain,
        )
    )


@pxt.query
def mixable_tracks(
    track_id: str,
    camelot: str,
    bpm: float,
    genre_family: str,
    genre: str,
    phrase_count: int,
    key_score: float,
    key_uncertain: bool,
    genre_uncertain: bool,
):
    return mixable_query(
        Tracks, track_id, camelot, bpm, genre_family, genre, phrase_count, key_score, key_uncertain, genre_uncertain
    )


@pxt.query
def list_tracks():
    return Tracks.select(
        Tracks.id,
        Tracks.title,
        Tracks.audio,
        Tracks.duration,
        Tracks.bpm,
        Tracks.bucket,
        Tracks.camelot,
        Tracks.key_margin,
        Tracks.key_score,
        Tracks.key_uncertain,
        Tracks.genre,
        Tracks.genre_score,
        Tracks.genre_family,
        Tracks.genre_uncertain,
        Tracks.loudness,
        Tracks.phrase_count,
    ).order_by(Tracks.id)


@pxt.query
def track_by_id(track_id: str):
    return (
        Tracks.where(Tracks.id == track_id)
        .select(
            Tracks.audio,
            Tracks.beat_times,
            Tracks.camelot,
            Tracks.bpm,
            Tracks.bucket,
            Tracks.genre,
            Tracks.genre_family,
            Tracks.phrase_count,
        )
        .limit(1)
    )


class Samples(TableModel, name='samples'):
    track_a_id: pxt.String
    track_b_id: pxt.String
    id = pxt.Column(value=pxtf.uuid.uuid7().to_string(), primary_key=True)
    track_a = track_by_id(track_a_id)
    track_b = track_by_id(track_b_id)
    rendered = render_preview(track_a, track_b)
    preview = rendered.audio
    reason = rendered.reason


api = FastAPIRouter(name='deejay')
api.add_insert_route(
    Tracks,
    path='/tracks',
    uploadfile_inputs=[Tracks.audio],
    inputs=[Tracks.given_title],
    outputs=[
        Tracks.id,
        Tracks.title,
        Tracks.audio,
        Tracks.duration,
        Tracks.audible_start,
        Tracks.audible_end,
        Tracks.bpm,
        Tracks.bucket,
        Tracks.camelot,
        Tracks.key_runner_up,
        Tracks.key_score,
        Tracks.key_margin,
        Tracks.key_uncertain,
        Tracks.genre,
        Tracks.genre_runner_up,
        Tracks.genre_score,
        Tracks.genre_family,
        Tracks.genre_uncertain,
        Tracks.loudness,
        Tracks.phrase_seconds,
        Tracks.phrase_count,
    ],
)
api.add_query_route(path='/tracks', query=list_tracks, method='get')
api.add_query_route(path='/mixable', query=mixable_tracks, method='post')
api.add_insert_route(
    Samples,
    path='/samples',
    inputs=[Samples.track_a_id, Samples.track_b_id],
    outputs=[Samples.id, Samples.track_a_id, Samples.track_b_id, Samples.preview, Samples.reason],
)


class MatchIn(BaseModel):
    track_id: str
    request: str


@api.post('/match')
def match(body: MatchIn) -> dict:
    tracks = pxt.get_table('deejay.tracks')
    found = list(tracks.where(tracks.id == body.track_id).collect())
    if not found:
        return {'match': None, 'reason': 'track not found'}
    caller = found[0]
    if int(caller.get('phrase_count') or 0) < 1:
        return {'match': None, 'reason': 'fewer than 32 beats'}
    rows = list(
        mixable_query(
            tracks,
            caller['id'],
            caller['camelot'],
            float(caller['bpm']),
            caller['genre_family'],
            caller['genre'],
            int(caller['phrase_count']),
            float(caller['key_score']),
            bool(caller['key_uncertain']),
            bool(caller['genre_uncertain']),
        ).collect()
    )
    if not rows:
        return {'match': None, 'reason': 'no mixable track'}
    # Two wheel steps are never on the T, so they never appear in this candidate set.
    request = body.request.lower()
    if 'two step' in request or '2 step' in request:
        return {'match': None, 'reason': 'no candidate is two steps away on the wheel'}
    if not os.environ.get('OPENAI_API_KEY'):
        return {'match': None, 'reason': 'OPENAI_API_KEY is not set'}
    brief = [
        {
            'track_id': row['other_id'],
            'title': row['other_title'],
            'camelot': row['other_camelot'],
            'bpm': row['other_bpm'],
            'genre': row['other_genre'],
            'genre_family': row['other_family'],
            'list': row['list_name'],
            'key_kind': row['key_kind'],
            'shift_semitones': row['shift_semitones'],
        }
        for row in rows
    ]
    picked = json.loads(choose_match.exec([body.request, json.dumps(brief)], {}))
    chosen = str(picked.get('track_id') or '')
    reason = str(picked.get('reason') or '')
    for row in rows:
        if row['other_id'] == chosen:
            return {'match': row, 'reason': reason}
    return {'match': None, 'reason': reason or 'no candidate fit the request'}
