"""Read plaintext and OpenClaw Zstandard transcript events without changing sources."""
import ctypes
import ctypes.util
import os
import json

_zstd = None
MAX_EVENT_BYTES = 64 * 1024 * 1024


def decode_event(row):
    global _zstd
    raw = row['event_json']
    if raw is None:
        keys = row.keys()
        if 'event_zstd' not in keys or row['event_zstd'] is None:
            raise ValueError('transcript_event_payload_missing')
        size = row['event_utf8_bytes'] if 'event_utf8_bytes' in keys else None
        if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= MAX_EVENT_BYTES:
            raise ValueError('transcript_event_size_invalid')
        if _zstd is None:
            library = os.environ.get('NEXUS_ZSTD_LIBRARY') or ctypes.util.find_library('zstd')
            if not library:
                raise ValueError('zstd_library_unavailable: install libzstd or set NEXUS_ZSTD_LIBRARY')
            lib = ctypes.CDLL(library)
            lib.ZSTD_decompress.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
            lib.ZSTD_decompress.restype = ctypes.c_size_t
            lib.ZSTD_isError.argtypes = [ctypes.c_size_t]
            lib.ZSTD_isError.restype = ctypes.c_uint
            _zstd = lib
        blob = row['event_zstd']
        output = ctypes.create_string_buffer(size)
        decoded = _zstd.ZSTD_decompress(output, size, blob, len(blob))
        if _zstd.ZSTD_isError(decoded) or decoded != size:
            raise ValueError('transcript_event_decompression_failed')
        raw = output.raw
    event = json.loads(raw)
    if not isinstance(event, dict):
        raise ValueError('transcript_event_object_required')
    return event
