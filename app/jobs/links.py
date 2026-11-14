import re
from urllib.parse import quote

from app.core.config import logs_url_template, metrics_url_template, perses_url, prometheus_url
from app.schemas.ops import ObservabilityLink

_PLACEHOLDER = re.compile(r"{(\w+)}")


def render(template: str | None, values: dict[str, str | None]) -> str | None:
    """Fill {name} placeholders with URL-encoded values; None when the template needs a value we lack."""
    if not template:
        return None
    needed = _PLACEHOLDER.findall(template)
    if any(not values.get(name) for name in needed):
        return None
    return _PLACEHOLDER.sub(lambda m: quote(str(values[m.group(1)]), safe=""), template)


def link(url: str | None) -> ObservabilityLink:
    return ObservabilityLink(available=url is not None, url=url)


def logs_link(values: dict[str, str | None]) -> ObservabilityLink:
    return link(render(logs_url_template(), values))


def metrics_link(values: dict[str, str | None]) -> ObservabilityLink:
    return link(render(metrics_url_template(), values) or perses_url() or prometheus_url())
