"""Background worker composition root."""


def health() -> dict[str, str]:
    """Return a side-effect-free process health marker."""

    return {"status": "ok", "component": "worker"}


__all__ = ["health"]
