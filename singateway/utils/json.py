try:
    import ujson
except ImportError:
    import json

    def to_json(obj):
        return json.dumps(obj, ensure_ascii=True, separators=(',', ':'))
finally:
    def to_json(obj):
        return ujson.dumps(obj, ensure_ascii=True)

