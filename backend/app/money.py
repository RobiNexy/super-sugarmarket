"""Integer-fen formatting helpers used at HTTP boundaries."""


def format_yuan(fen: int) -> str:
    """Format non-negative integer fen as a two-decimal yuan string."""
    if fen < 0:
        raise ValueError("fen must be non-negative")
    return f"{fen // 100}.{fen % 100:02d}"
