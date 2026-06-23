"""Generic, target-agnostic feature access.

The harness never knows a victim's field names at write time; it reads them by
the names a SealedSpec declares. `feature` pulls a spec-named attribute off an
opaque sample, raising a clear error (never a silent default) if it is absent.
"""


def feature(sample: object, name: str) -> object:
    """Read the spec-named feature `name` off an opaque `sample`.

    Raises AttributeError (with a clear message) if the sample lacks it, so a
    spec that names a feature the victim does not expose fails loudly.
    """
    try:
        return getattr(sample, name)
    except AttributeError as exc:
        raise AttributeError(
            f"sample of type {type(sample).__name__!r} has no spec-named "
            f"feature {name!r}"
        ) from exc
