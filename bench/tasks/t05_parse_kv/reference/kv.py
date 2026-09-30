def parse_kv(s):
    out = {}
    for seg in s.split(';'):
        seg = seg.strip()
        if not seg or '=' not in seg:
            continue
        k, v = seg.split('=', 1)
        out[k.strip()] = v.strip()
    return out
