"""Fast YAML load. CSafeLoader is libyaml's SafeLoader — same restricted tag set,
10-20x faster (tracks/ml.yaml 561ms -> 25ms). Falls back to the pure-Python
SafeLoader if libyaml isn't built in.
"""
import yaml

try:
    from yaml import CSafeLoader as _Loader
except ImportError:
    _Loader = yaml.SafeLoader

LOADER = _Loader


def load(text):
    return yaml.load(text, Loader=_Loader)


def load_path(path, encoding="utf-8"):
    with open(path, encoding=encoding) as f:
        return yaml.load(f, Loader=_Loader)
