"""테스트용 최소 SMF 파서.

생성한 MIDI 파일이 규격대로 읽히는지 **독립적으로** 확인하기 위한 코드입니다.
런타임에는 쓰이지 않으며 외부 라이브러리도 필요 없습니다.
"""

from __future__ import annotations

import struct
from typing import Dict, List, NamedTuple, Tuple


class ParsedNote(NamedTuple):
    track: int
    channel: int
    pitch: int
    velocity: int
    start: int
    duration: int


class ParsedFile(NamedTuple):
    fmt: int
    ppq: int
    tracks: List[Dict]
    notes: List[ParsedNote]


def _read_varlen(data: bytes, i: int) -> Tuple[int, int]:
    value = 0
    while True:
        byte = data[i]
        i += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, i


def parse(data: bytes) -> ParsedFile:
    if data[:4] != b"MThd":
        raise ValueError("MThd 헤더가 없습니다")
    (hdr_len,) = struct.unpack(">I", data[4:8])
    fmt, ntrks, ppq = struct.unpack(">HHH", data[8:8 + 6])
    pos = 8 + hdr_len

    tracks: List[Dict] = []
    notes: List[ParsedNote] = []

    for track_index in range(ntrks):
        if data[pos:pos + 4] != b"MTrk":
            raise ValueError(f"트랙 {track_index}: MTrk 청크가 없습니다")
        (length,) = struct.unpack(">I", data[pos + 4:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        pos += 8 + length

        info: Dict = {"name": None, "tempo": None, "time_signature": None,
                      "key_signature": None, "markers": [], "programs": []}
        open_notes: Dict[Tuple[int, int], Tuple[int, int]] = {}
        tick = 0
        i = 0
        status = 0
        saw_end = False

        while i < len(body):
            delta, i = _read_varlen(body, i)
            tick += delta
            byte = body[i]
            if byte & 0x80:
                status = byte
                i += 1
            elif not status:
                raise ValueError("러닝 스테이터스 없이 데이터 바이트가 나왔습니다")

            if status == 0xFF:                       # 메타
                kind = body[i]; i += 1
                size, i = _read_varlen(body, i)
                payload = body[i:i + size]; i += size
                if kind == 0x2F:
                    saw_end = True
                elif kind == 0x03:
                    info["name"] = payload.decode("latin-1")
                elif kind == 0x06:
                    info["markers"].append((tick, payload.decode("latin-1")))
                elif kind == 0x51:
                    info["tempo"] = 60_000_000 / int.from_bytes(payload, "big")
                elif kind == 0x58:
                    info["time_signature"] = (payload[0], 2 ** payload[1])
                elif kind == 0x59:
                    sharps = payload[0] - 256 if payload[0] > 127 else payload[0]
                    info["key_signature"] = (sharps, payload[1])
            elif status in (0xF0, 0xF7):             # 시스템 익스클루시브
                size, i = _read_varlen(body, i)
                i += size
            else:
                kind = status & 0xF0
                channel = status & 0x0F
                if kind in (0xC0, 0xD0):
                    i += 1
                    if kind == 0xC0:
                        info["programs"].append((tick, body[i - 1]))
                else:
                    d1, d2 = body[i], body[i + 1]
                    i += 2
                    if kind == 0x90 and d2 > 0:
                        open_notes[(channel, d1)] = (tick, d2)
                    elif kind == 0x80 or (kind == 0x90 and d2 == 0):
                        key = (channel, d1)
                        if key not in open_notes:
                            raise ValueError(f"열리지 않은 노트가 닫혔습니다: {key}")
                        start, velocity = open_notes.pop(key)
                        notes.append(ParsedNote(track_index, channel, d1, velocity,
                                                start, tick - start))

        if open_notes:
            raise ValueError(f"트랙 {track_index}: 닫히지 않은 노트 {sorted(open_notes)}")
        if not saw_end:
            raise ValueError(f"트랙 {track_index}: End of Track 메타가 없습니다")
        tracks.append(info)

    if pos != len(data):
        raise ValueError(f"파일 끝에 남은 바이트가 있습니다: {len(data) - pos}")
    return ParsedFile(fmt=fmt, ppq=ppq, tracks=tracks, notes=sorted(notes, key=lambda n: (n.start, n.pitch)))
