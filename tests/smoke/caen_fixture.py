"""Small independent oracle for the specific single-board CAEN v3.3 fixtures.

This is not a replacement decoder or a specification for every CAEN mode.
It deliberately accepts nonmonotonic trigger IDs: Run36 contains a reset.
"""
import math
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "caen"


def parse_capture(raw):
    lines = raw.decode("ascii").splitlines()
    if "// File Format Version 3.3" not in lines:
        raise ValueError("unsupported format")
    try:
        column = next(i for i, line in enumerate(lines) if line.startswith("Brd"))
    except StopIteration as error:
        raise ValueError("missing column header") from error
    events = []
    i = column + 1
    while i < len(lines):
        header = lines[i].split()
        if len(header) != 7:
            raise ValueError("short event header")
        board, channel, low, high = map(int, header[:4])
        stamp, trigger, nhits = float(header[4]), int(header[5]), int(header[6])
        if not math.isfinite(stamp) or nhits != 3:
            raise ValueError("expected finite timestamp and three hits")
        hits = [[board, channel, low, high]]
        for offset in range(1, nhits):
            if i + offset >= len(lines):
                raise ValueError("truncated hit block")
            fields = lines[i + offset].split()
            if len(fields) != 4:
                raise ValueError("bad continuation hit")
            hits.append(list(map(int, fields)))
        if [(h[0], h[1]) for h in hits] != [(0, 32), (0, 33), (0, 34)]:
            raise ValueError("unexpected board/channel order")
        events.append({"id": trigger, "time": stamp,
                       "tiles": [[cell, h[2], h[3]] for cell, h in enumerate(hits)]})
        i += nhits
    if not events:
        raise ValueError("empty capture")
    return events


def malformed_variants(raw):
    """Deterministic, one-defect variants of the first two complete events.

    Normalize CRLF explicitly, so known format rejection cannot masquerade as
    successful validation of malformed event content. No raw fixture is edited.
    """
    parse_capture(raw)
    lines = raw.replace(b"\r\n", b"\n").splitlines(keepends=True)
    first = next(i for i, line in enumerate(lines) if line.startswith(b"Brd")) + 1
    lines = lines[:first + 6]
    valid = b"".join(lines)
    short = lines.copy()
    short[first] = b" ".join(short[first].split()[:-1]) + b"\n"
    nonnumeric = lines.copy()
    hit = nonnumeric[-1].split()
    hit[3] = b"BROKEN"
    nonnumeric[-1] = b" ".join(hit) + b"\n"
    return {
        "unsupported_format": valid.replace(b"Version 3.3", b"Version 9.9", 1),
        "short_header": b"".join(short),
        "truncated_hit": b"".join(lines[:-1]),
        "nonnumeric_adc": b"".join(nonnumeric),
    }
