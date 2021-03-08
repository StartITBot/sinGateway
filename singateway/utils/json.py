try:
    import ujson as json
except ImportError:
    import json


def to_json(obj):
    return json.dumps(obj, ensure_ascii=True, separators=(',', ':'))
