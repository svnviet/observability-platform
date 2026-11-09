import os


def database_url() -> str:
    url = os.environ.get("OBSKIT_PLATFORM_DATABASE_URL")
    if not url:
        raise RuntimeError("OBSKIT_PLATFORM_DATABASE_URL is not set")
    return url


def api_key() -> str:
    key = os.environ.get("OBSKIT_PLATFORM_API_KEY")
    if not key:
        raise RuntimeError("OBSKIT_PLATFORM_API_KEY is not set")
    return key


def default_page_size() -> int:
    return int(os.environ.get("OBSKIT_PLATFORM_DEFAULT_PAGE_SIZE", "50"))


def max_page_size() -> int:
    return int(os.environ.get("OBSKIT_PLATFORM_MAX_PAGE_SIZE", "200"))


def jaeger_url() -> str | None:
    """Browser-facing base URL of the Jaeger UI. When set, runs and attempts carry a link to their trace."""
    return os.environ.get("OBSKIT_PLATFORM_JAEGER_URL") or None


def perses_url() -> str | None:
    return os.environ.get("OBSKIT_PLATFORM_PERSES_URL") or None


def prometheus_url() -> str | None:
    return os.environ.get("OBSKIT_PLATFORM_PROMETHEUS_URL") or None


def heartbeat_timeout_s() -> float:
    return float(os.environ.get("OBSKIT_PLATFORM_HEARTBEAT_TIMEOUT_S", "30"))


def heartbeat_scan_interval_s() -> float:
    """0 disables the background scan (tests and one-off tooling)."""
    return float(os.environ.get("OBSKIT_PLATFORM_HEARTBEAT_SCAN_INTERVAL_S", "10"))
