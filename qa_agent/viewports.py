"""Viewport presets and parsing.

A :class:`Viewport` is a full device profile — size plus the emulation
attributes Playwright needs to make a site behave as it would on that device
(device pixel ratio, touch support, mobile flag, user agent). Testing at
``390x844`` with a desktop user agent and no touch support exercises a
desktop layout squeezed into a phone-sized window, which is not the same
thing as testing the phone experience; sites that switch layout on UA
sniffing or ``pointer: coarse`` would never show their mobile rendering.

The registry is deliberately a plain data table rather than a lookup into
``playwright.devices``: it is importable (and testable) without a browser or a
running Playwright instance, which the CLI needs for ``--list-viewports`` and
the web server needs to render its form.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Bounds for custom (non-preset) sizes. Wide enough for ultrawide monitors and
# portrait kiosks, tight enough to reject typos like "1280x72000".
MIN_DIMENSION = 100
MAX_DIMENSION = 10000

# User agents for the emulated device presets. Kept verbatim rather than
# generated so what a preset sends is greppable and reviewable.
_UA_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"
)
_UA_IPAD = (
    "Mozilla/5.0 (iPad; CPU OS 17_4 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"
)
_UA_ANDROID = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36"
)


@dataclass(frozen=True)
class Viewport:
    """A named viewport / device profile used for one test sweep.

    ``name`` is what appears in reports, screenshot paths, and finding labels,
    so it must be stable and human-meaningful.
    """

    name: str
    width: int
    height: int
    device_scale_factor: float = 1.0
    is_mobile: bool = False
    has_touch: bool = False
    user_agent: str | None = None
    description: str = ""

    @property
    def size(self) -> str:
        """Dimensions as ``WIDTHxHEIGHT``."""
        return f"{self.width}x{self.height}"

    @property
    def label(self) -> str:
        """Human-readable label, e.g. ``mobile (390x844)``."""
        if self.name == self.size:
            return self.size
        return f"{self.name} ({self.size})"

    @property
    def slug(self) -> str:
        """Filesystem-safe form of :attr:`name`, for screenshot subdirectories."""
        safe = re.sub(r"[^\w.\-]", "_", self.name)
        return safe or "viewport"

    def to_context_options(self) -> dict[str, Any]:
        """Return the ``browser.new_context()`` kwargs for this viewport.

        Only non-default emulation keys are included so a plain-size viewport
        produces exactly the context options the agent used before viewport
        profiles existed.
        """
        options: dict[str, Any] = {
            "viewport": {"width": self.width, "height": self.height},
        }
        if self.device_scale_factor != 1.0:
            options["device_scale_factor"] = self.device_scale_factor
        if self.is_mobile:
            options["is_mobile"] = True
        if self.has_touch:
            options["has_touch"] = True
        if self.user_agent:
            options["user_agent"] = self.user_agent
        return options

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "device_scale_factor": self.device_scale_factor,
            "is_mobile": self.is_mobile,
            "has_touch": self.has_touch,
            "user_agent": self.user_agent,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Viewport:
        """Build a Viewport from a dict (web request body, batch spec, JSON).

        Unknown keys are ignored; a missing ``name`` falls back to ``WxH``.
        """
        width = _validated_dimension(data["width"], "width")
        height = _validated_dimension(data["height"], "height")
        name = str(data.get("name") or f"{width}x{height}").strip()
        return cls(
            name=name or f"{width}x{height}",
            width=width,
            height=height,
            device_scale_factor=float(data.get("device_scale_factor", 1.0) or 1.0),
            is_mobile=bool(data.get("is_mobile", False)),
            has_touch=bool(data.get("has_touch", False)),
            user_agent=data.get("user_agent") or None,
            description=str(data.get("description") or ""),
        )


# Ordered registry — declaration order is the order shown by --list-viewports
# and in the web UI.
PRESETS: dict[str, Viewport] = {
    vp.name: vp
    for vp in (
        Viewport(
            name="desktop",
            width=1920,
            height=1080,
            description="Full HD desktop monitor",
        ),
        Viewport(
            name="laptop",
            width=1440,
            height=900,
            device_scale_factor=2.0,
            description="Retina laptop (MacBook-class)",
        ),
        Viewport(
            name="tablet",
            width=768,
            height=1024,
            device_scale_factor=2.0,
            is_mobile=True,
            has_touch=True,
            user_agent=_UA_IPAD,
            description="iPad-class tablet, portrait",
        ),
        Viewport(
            name="tablet-landscape",
            width=1024,
            height=768,
            device_scale_factor=2.0,
            is_mobile=True,
            has_touch=True,
            user_agent=_UA_IPAD,
            description="iPad-class tablet, landscape",
        ),
        Viewport(
            name="mobile",
            width=390,
            height=844,
            device_scale_factor=3.0,
            is_mobile=True,
            has_touch=True,
            user_agent=_UA_IPHONE,
            description="iPhone-class phone (14/15)",
        ),
        Viewport(
            name="mobile-small",
            width=375,
            height=667,
            device_scale_factor=2.0,
            is_mobile=True,
            has_touch=True,
            user_agent=_UA_IPHONE,
            description="Small phone (iPhone SE-class)",
        ),
        Viewport(
            name="android",
            width=412,
            height=915,
            device_scale_factor=2.625,
            is_mobile=True,
            has_touch=True,
            user_agent=_UA_ANDROID,
            description="Pixel-class Android phone",
        ),
    )
}

# The historical single viewport, used when nothing is specified so existing
# runs are byte-for-byte unchanged.
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720

# ``WIDTHxHEIGHT`` — 'x' or the multiplication sign, optional surrounding space.
_SIZE_RE = re.compile(r"^(\d+)\s*[x×]\s*(\d+)$", re.IGNORECASE)
# ``name=WIDTHxHEIGHT`` for named custom sizes, e.g. ``kiosk=1080x1920``.
_NAMED_SIZE_RE = re.compile(r"^([\w.\- ]+?)\s*=\s*(.+)$")


def _validated_dimension(value: Any, field: str) -> int:
    """Coerce and bounds-check a single viewport dimension."""
    try:
        dimension = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid viewport {field}: {value!r}") from None
    if not MIN_DIMENSION <= dimension <= MAX_DIMENSION:
        raise ValueError(
            f"Viewport {field} {dimension} is out of range "
            f"({MIN_DIMENSION}-{MAX_DIMENSION})"
        )
    return dimension


def default_viewport() -> Viewport:
    """The implicit viewport used when the caller specifies none."""
    return Viewport(
        name=f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}",
        width=DEFAULT_WIDTH,
        height=DEFAULT_HEIGHT,
    )


def get_preset(name: str) -> Viewport | None:
    """Look up a preset by name (case-insensitive), or ``None``."""
    return PRESETS.get(str(name).strip().lower())


def list_presets() -> list[Viewport]:
    """All presets in registry order."""
    return list(PRESETS.values())


def parse_viewport(spec: str) -> Viewport:
    """Parse one spec into a :class:`Viewport`.

    Accepts a preset name (``mobile``), a raw size (``1920x1080``), or a named
    custom size (``kiosk=1080x1920``). Raises :class:`ValueError` on anything
    else, with the valid preset names in the message.
    """
    text = str(spec).strip()
    if not text:
        raise ValueError("Empty viewport specification")

    custom_name: str | None = None
    named = _NAMED_SIZE_RE.match(text)
    if named:
        custom_name, text = named.group(1).strip(), named.group(2).strip()

    preset = get_preset(text)
    if preset is not None:
        if custom_name:
            # ``label=preset`` just renames an existing preset profile.
            return Viewport(**{**preset.to_dict(), "name": custom_name})
        return preset

    match = _SIZE_RE.match(text)
    if match:
        width = _validated_dimension(match.group(1), "width")
        height = _validated_dimension(match.group(2), "height")
        return Viewport(
            name=custom_name or f"{width}x{height}",
            width=width,
            height=height,
        )

    raise ValueError(
        f"Unknown viewport {spec!r}. Use WIDTHxHEIGHT (e.g. 1920x1080) or one of: "
        + ", ".join(PRESETS)
    )


def parse_viewports(spec: str | list[str] | None) -> list[Viewport]:
    """Parse a comma-separated spec (or list of specs) into viewports.

    Duplicates are collapsed on ``name`` while preserving first-seen order, so
    ``--viewport mobile,mobile`` sweeps once rather than twice. Returns an
    empty list for empty input; callers decide what the default should be.
    """
    if spec is None:
        return []

    parts: list[str] = []
    items = spec if isinstance(spec, list) else [spec]
    for item in items:
        parts.extend(p.strip() for p in str(item).split(","))

    viewports: list[Viewport] = []
    seen: set[str] = set()
    for part in parts:
        if not part:
            continue
        viewport = parse_viewport(part)
        if viewport.name in seen:
            continue
        seen.add(viewport.name)
        viewports.append(viewport)
    return viewports


def coerce_viewports(values: Any) -> list[Viewport]:
    """Best-effort conversion of arbitrary caller input into viewports.

    Accepts what SDK, web, and batch-file callers realistically pass: a comma
    separated string, or a list mixing :class:`Viewport` objects, preset-name
    strings, ``WxH`` strings, and full dicts. Invalid entries raise
    :class:`ValueError` so misconfiguration surfaces rather than silently
    testing the wrong size.
    """
    if values is None:
        return []
    if isinstance(values, Viewport):
        return [values]
    if isinstance(values, str):
        return parse_viewports(values)
    if isinstance(values, dict):
        return [Viewport.from_dict(values)]

    viewports: list[Viewport] = []
    seen: set[str] = set()
    for value in values:
        if isinstance(value, Viewport):
            candidates = [value]
        elif isinstance(value, dict):
            candidates = [Viewport.from_dict(value)]
        else:
            candidates = parse_viewports(str(value))
        for viewport in candidates:
            if viewport.name in seen:
                continue
            seen.add(viewport.name)
            viewports.append(viewport)
    return viewports


def format_preset_table() -> str:
    """Render the preset registry as a plain-text table for ``--list-viewports``."""
    rows = [("NAME", "SIZE", "DPR", "TOUCH", "DESCRIPTION")]
    rows += [
        (
            vp.name,
            vp.size,
            f"{vp.device_scale_factor:g}",
            "yes" if vp.has_touch else "no",
            vp.description,
        )
        for vp in list_presets()
    ]
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    lines = [
        "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip()
        for row in rows
    ]
    lines.insert(1, "  ".join("-" * w for w in widths))
    return "\n".join(lines)
