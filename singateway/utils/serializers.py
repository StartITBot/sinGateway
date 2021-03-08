import types


class Serializer:
    FORMATS = {
        'json',
        'yml',
        'yaml',
        'pickle',
    }

    @classmethod
    def check_format(cls, fmt):
        if fmt not in cls.FORMATS:
            raise ValueError('Unsupported serialization format: {}'.format(fmt))

    @staticmethod
    def json():
        from json import loads, dumps
        return loads, dumps

    @staticmethod
    def yaml():
        from yaml import full_load, dump
        return full_load, dump

    @staticmethod
    def yml():
        return Serializer.yaml()

    @staticmethod
    def pickle():
        from pickle import loads, dumps
        return loads, dumps

    @classmethod
    def loads(cls, fmt, raw):
        loads, _ = getattr(cls, fmt)()
        return loads(raw)

    @classmethod
    def dumps(cls, fmt, raw):
        _, dumps = getattr(cls, fmt)()
        return dumps(raw)


def dump_cell(cell):
    return cell.cell_contents


def load_cell(cell):
    return (lambda y: cell).__closure__[0]


def dump_function(func):
    return (
        func.__code__,
        func.__name__,
        func.__defaults__,
        list(map(dump_cell, func.__closure__)) if func.__closure__ else [],
    )


def load_function(args):
    code, name, defaults, closure = args
    closure = tuple(map(load_cell, closure))
    return types.FunctionType(code, globals(), name, defaults, closure)
