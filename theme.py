from __future__ import annotations

import json
import os
import platform
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class Palette:
    """Papéis de cor do Material 3 usados pelo painel (os mesmos que o matugen gera)."""

    name: str
    surface: str
    surface_container: str
    surface_container_high: str
    surface_container_highest: str
    on_surface: str
    on_surface_variant: str
    outline: str
    outline_variant: str
    primary: str
    on_primary: str
    primary_container: str
    on_primary_container: str
    secondary_container: str
    on_secondary_container: str
    tertiary_container: str
    on_tertiary_container: str
    error: str
    field: str
    fonts: tuple[str, ...] = ("Inter", "Cantarell", "Noto Sans", "DejaVu Sans")


# Fallback do próprio app (seed laranja "etiqueta de preço"), gerado como tema Material 3.
LIGHT = Palette(
    name="light",
    surface="#fff8f5",
    surface_container="#fbebe2",
    surface_container_high="#f5e5dc",
    surface_container_highest="#efdfd6",
    on_surface="#221a15",
    on_surface_variant="#52443c",
    outline="#85736b",
    outline_variant="#d7c2b8",
    primary="#8c4f26",
    on_primary="#ffffff",
    primary_container="#ffdbc9",
    on_primary_container="#341100",
    secondary_container="#f6dccd",
    on_secondary_container="#2b160d",
    tertiary_container="#e3e4b0",
    on_tertiary_container="#1c1d00",
    error="#ba1a1a",
    field="#fff8f5",
)

DARK = Palette(
    name="dark",
    surface="#1a120d",
    surface_container="#271e19",
    surface_container_high="#322823",
    surface_container_highest="#3d332d",
    on_surface="#f0dfd7",
    on_surface_variant="#d7c2b8",
    outline="#a08d84",
    outline_variant="#52443c",
    primary="#ffb68b",
    on_primary="#532200",
    primary_container="#713710",
    on_primary_container="#ffdbc9",
    secondary_container="#5c4032",
    on_secondary_container="#ffdbca",
    tertiary_container="#474920",
    on_tertiary_container="#e3e4b0",
    error="#ffb4ab",
    field="#322823",
)

WINDOWS_DARK = Palette(
    name="windows-dark",
    surface="#202020",
    surface_container="#2b2b2b",
    surface_container_high="#323232",
    surface_container_highest="#3d3d3d",
    on_surface="#ffffff",
    on_surface_variant="#c8c8c8",
    outline="#9a9a9a",
    outline_variant="#3d3d3d",
    primary="#60cdff",
    on_primary="#000000",
    primary_container="#0f3a52",
    on_primary_container="#cfeeff",
    secondary_container="#3d3d3d",
    on_secondary_container="#ffffff",
    tertiary_container="#1f3d24",
    on_tertiary_container="#9fe0a8",
    error="#ff99a4",
    field="#2d2d2d",
    fonts=("Segoe UI Variable Text", "Segoe UI"),
)

WINDOWS_LIGHT = Palette(
    name="windows-light",
    surface="#f3f3f3",
    surface_container="#ffffff",
    surface_container_high="#f9f9f9",
    surface_container_highest="#e5e5e5",
    on_surface="#1a1a1a",
    on_surface_variant="#5c5c5c",
    outline="#8a8a8a",
    outline_variant="#e0e0e0",
    primary="#005fb8",
    on_primary="#ffffff",
    primary_container="#cce4f7",
    on_primary_container="#002a4d",
    secondary_container="#e5e5e5",
    on_secondary_container="#1a1a1a",
    tertiary_container="#dff6dd",
    on_tertiary_container="#0f5223",
    error="#c42b1c",
    field="#ffffff",
    fonts=("Segoe UI Variable Text", "Segoe UI"),
)


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")[:6]
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def mix(base: str, other: str, amount: float) -> str:
    """Mistura `other` sobre `base` (0 = base, 1 = other)."""
    b, o = _hex_to_rgb(base), _hex_to_rgb(other)
    return "#" + "".join(f"{round(bc + (oc - bc) * amount):02x}" for bc, oc in zip(b, o))


def _luminance(color: str) -> float:
    def channel(v: int) -> float:
        s = v / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in _hex_to_rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _readable_on(color: str) -> str:
    return "#000000" if _luminance(color) > 0.35 else "#ffffff"


def _from_m3_json(data: dict) -> Palette | None:
    """Arquivo com papéis em snake_case (ex.: gerado por um template do matugen)."""
    colors = data.get("colors", data)
    try:
        surface = colors["surface"]
        on_surface = colors["on_surface"]
        primary = colors["primary"]
    except KeyError:
        return None

    def get(key: str, fallback: str) -> str:
        value = colors.get(key)
        return value if isinstance(value, str) and value.startswith("#") else fallback

    container = get("surface_container", mix(surface, on_surface, 0.06))
    high = get("surface_container_high", mix(surface, on_surface, 0.10))
    return Palette(
        name="matugen",
        surface=surface,
        surface_container=container,
        surface_container_high=high,
        surface_container_highest=get("surface_container_highest", mix(surface, on_surface, 0.14)),
        on_surface=on_surface,
        on_surface_variant=get("on_surface_variant", mix(on_surface, surface, 0.25)),
        outline=get("outline", mix(on_surface, surface, 0.45)),
        outline_variant=get("outline_variant", mix(surface, on_surface, 0.22)),
        primary=primary,
        on_primary=get("on_primary", _readable_on(primary)),
        primary_container=get("primary_container", mix(surface, primary, 0.25)),
        on_primary_container=get("on_primary_container", on_surface),
        secondary_container=get("secondary_container", mix(surface, primary, 0.18)),
        on_secondary_container=get("on_secondary_container", on_surface),
        tertiary_container=get("tertiary_container", mix(surface, get("tertiary", primary), 0.22)),
        on_tertiary_container=get("on_tertiary_container", get("tertiary", primary)),
        error=get("error", "#ffb4ab" if _luminance(surface) < 0.2 else "#ba1a1a"),
        field=high,
    )


def _from_noctalia_json(data: dict) -> Palette | None:
    """~/.config/noctalia/colors.json (chaves mPrimary, mSurface…)."""
    try:
        surface = data["mSurface"]
        on_surface = data["mOnSurface"]
        primary = data["mPrimary"]
    except KeyError:
        return None
    surface_variant = data.get("mSurfaceVariant", mix(surface, on_surface, 0.08))
    tertiary = data.get("mTertiary", primary)
    secondary = data.get("mSecondary", primary)
    outline = data.get("mOutline", mix(on_surface, surface, 0.45))
    high = mix(surface_variant, on_surface, 0.06)
    return Palette(
        name="noctalia",
        surface=surface,
        surface_container=surface_variant,
        surface_container_high=high,
        surface_container_highest=mix(surface_variant, on_surface, 0.12),
        on_surface=on_surface,
        on_surface_variant=data.get("mOnSurfaceVariant", mix(on_surface, surface, 0.25)),
        outline=outline,
        outline_variant=mix(surface, outline, 0.45),
        primary=primary,
        on_primary=data.get("mOnPrimary", _readable_on(primary)),
        primary_container=mix(surface, primary, 0.25),
        on_primary_container=on_surface,
        secondary_container=mix(surface, secondary, 0.30),
        on_secondary_container=on_surface,
        tertiary_container=mix(surface, tertiary, 0.22),
        on_tertiary_container=tertiary,
        error=data.get("mError", "#ffb4ab"),
        field=high,
    )


def _config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def _load_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _system_palette() -> Palette | None:
    """Cores geradas pelo matugen / Noctalia, se existirem."""
    custom = _load_json(_config_home() / "deal-hunter" / "colors.json")
    if custom:
        palette = _from_m3_json(custom)
        if palette:
            return palette
    noctalia = _load_json(_config_home() / "noctalia" / "colors.json")
    if noctalia:
        return _from_noctalia_json(noctalia)
    return None


def _run(cmd: list[str]) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return ""
    return res.stdout.strip()


def _linux_prefers_dark() -> bool:
    if "prefer-dark" in _run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"]):
        return True
    if "dark" in os.environ.get("GTK_THEME", "").lower():
        return True
    if "dark" in _run(["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"]).lower():
        return True
    try:
        kdeglobals = (_config_home() / "kdeglobals").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    for line in kdeglobals.splitlines():
        if line.startswith("ColorScheme=") and "dark" in line.lower():
            return True
    return False


def _windows_palette() -> Palette:
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            light = winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 1
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM") as key:
            abgr = int(winreg.QueryValueEx(key, "AccentColor")[0])
    except (ImportError, OSError, ValueError):
        return WINDOWS_DARK

    accent = f"#{abgr & 0xFF:02x}{(abgr >> 8) & 0xFF:02x}{(abgr >> 16) & 0xFF:02x}"
    if light:
        primary = mix(accent, "#000000", 0.15)
        return replace(
            WINDOWS_LIGHT,
            primary=primary,
            on_primary=_readable_on(primary),
            primary_container=mix("#ffffff", accent, 0.2),
        )
    primary = mix(accent, "#ffffff", 0.45)
    return replace(
        WINDOWS_DARK,
        primary=primary,
        on_primary=_readable_on(primary),
        primary_container=mix("#202020", accent, 0.35),
    )


def load_palette() -> Palette:
    """
    Ordem: DEAL_HUNTER_THEME (light/dark/windows) → cores do matugen/Noctalia
    → Windows (tema + cor de destaque) → claro/escuro do sistema.
    """
    forced = os.environ.get("DEAL_HUNTER_THEME", "").strip().lower()
    if forced == "light":
        return LIGHT
    if forced == "dark":
        return DARK
    if forced == "windows":
        return _windows_palette()

    system = platform.system().lower()
    if system == "windows":
        return _windows_palette()

    palette = _system_palette()
    if palette:
        return palette

    if system == "darwin":
        return DARK if _run(["defaults", "read", "-g", "AppleInterfaceStyle"]) == "Dark" else LIGHT
    return DARK if _linux_prefers_dark() else LIGHT
