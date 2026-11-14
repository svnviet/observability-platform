import re

_STACK_KEYS = ("stack_trace", "stack", "traceback")
_PYTHON_FRAME = re.compile(r'File "(.+?)", line (\d+), in (\S+)')
_NODE_FRAME = re.compile(r"at (?:async )?(\S+) \((.+?):(\d+):\d+\)")

# Checked in order; the first rule that matches wins, so the more specific causes come first.
_TEXT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "DEPENDENCY",
        (
            "autoreconnect", "connection", "refused", "forcibly closed", "unreachable", "name resolution",
            "econn", "broken pipe", "bad gateway", "service unavailable", "serverselectiontimeout",
        ),
    ),  # fmt: skip
    ("TIMEOUT", ("timeout", "timed out", "deadline exceeded")),
    ("RESOURCE", ("memoryerror", "out of memory", "no space left", "disk full", "quota", "rate limit", "too many requests")),
    ("AUTH", ("unauthorized", "forbidden", "permission denied", "invalid api key", "authentication")),
    ("CRASH", ("crashed", "restarting", "killed", "sigkill", "segfault", "exited unexpectedly")),
)
_CODE_TYPES = frozenset(
    {
        "TypeError", "KeyError", "AttributeError", "ValueError", "IndexError", "NameError", "AssertionError",
        "ZeroDivisionError", "ImportError", "ModuleNotFoundError", "NotImplementedError", "UnicodeDecodeError",
        "UnicodeEncodeError", "JSONDecodeError", "ValidationError",
    }
)  # fmt: skip
_STATUS_CODES = {r"\b429\b": "RESOURCE", r"\b40[13]\b": "AUTH", r"\b50[23]\b": "DEPENDENCY"}


class ErrorClassifier:
    """Rule-based reading of an error record. A heuristic that narrows the search, not a verdict."""

    @staticmethod
    def stack_trace(error: dict | None) -> str | None:
        for key in _STACK_KEYS:
            value = (error or {}).get(key)
            if isinstance(value, str) and value:
                return value
        return None

    @staticmethod
    def signature(error: dict | None) -> str:
        """What makes two failures 'the same error': the type, or the start of the message when there is none."""
        error = error or {}
        return str(error.get("type") or str(error.get("message") or "unknown")[:80])

    @classmethod
    def classify(cls, error: dict | None) -> tuple[str, str | None]:
        error = error or {}
        text = f"{error.get('type', '')} {error.get('message', '')}".lower()
        for category, words in _TEXT_RULES:
            hit = next((w for w in words if w in text), None)
            if hit:
                return category, f"matched '{hit}'"
        for pattern, category in _STATUS_CODES.items():
            found = re.search(pattern, text)
            if found:
                return category, f"matched status {found.group(0)}"
        if error.get("type") in _CODE_TYPES:
            return "CODE", f"{error['type']} usually means a bug or unexpected data"
        return "UNKNOWN", None

    @staticmethod
    def location(stack_trace: str | None) -> str | None:
        """The innermost frame: the last Python frame, or the first Node frame."""
        if not stack_trace:
            return None
        python = _PYTHON_FRAME.findall(stack_trace)
        if python:
            path, line, function = python[-1]
            return f"{'/'.join(path.replace(chr(92), '/').split('/')[-3:])}:{line} in {function}"
        node = _NODE_FRAME.search(stack_trace)
        if node:
            function, path, line = node.groups()
            return f"{'/'.join(path.replace(chr(92), '/').split('/')[-3:])}:{line} in {function}"
        return None
