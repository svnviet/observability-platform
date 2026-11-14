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


def lost_after_s() -> float:
    """An UNHEALTHY instance/worker silent this long is presumed gone and becomes STOPPED. 0 disables."""
    return float(os.environ.get("OBSKIT_PLATFORM_LOST_AFTER_S", "86400"))


def purge_after_s() -> float:
    """STOPPED instances/workers silent this long are deleted. 0 disables (keep forever)."""
    return float(os.environ.get("OBSKIT_PLATFORM_PURGE_AFTER_S", "604800"))


def health_probe_interval_s() -> float:
    """How often the platform probes every instance's health_url. 0 disables active probing."""
    return float(os.environ.get("OBSKIT_PLATFORM_HEALTH_PROBE_INTERVAL_S", "30"))


def health_probe_timeout_s() -> float:
    return float(os.environ.get("OBSKIT_PLATFORM_HEALTH_PROBE_TIMEOUT_S", "5"))


def health_fail_threshold() -> int:
    """Consecutive failed probes that open an incident and count as an outage."""
    return int(os.environ.get("OBSKIT_PLATFORM_HEALTH_FAIL_THRESHOLD", "3"))


def health_retention_days() -> float:
    """Probe history older than this is deleted. 0 keeps everything."""
    return float(os.environ.get("OBSKIT_PLATFORM_HEALTH_RETENTION_DAYS", "14"))


def logs_url_template() -> str | None:
    """Link template to a job's logs, e.g. http://grafana/explore?query={trace_id}. None hides the log link."""
    return os.environ.get("OBSKIT_PLATFORM_LOGS_URL_TEMPLATE") or None


def metrics_url_template() -> str | None:
    """Link template to a service's metrics, e.g. http://perses/d/service?service={service}. Falls back to the Perses URL."""
    return os.environ.get("OBSKIT_PLATFORM_METRICS_URL_TEMPLATE") or None


def dashboard_url_template() -> str | None:
    """Link template to a dashboard, e.g. http://perses/d/service?var-service={service}&var-instance={instance}.

    Placeholders (URL-encoded): {service} {instance} {worker} {environment} {workflow_id}. None hides the link.
    """
    return os.environ.get("OBSKIT_PLATFORM_DASHBOARD_URL_TEMPLATE") or None
