from jutsu.profiles import CleanupSettings, ColorSettings


def build_cleanup_filter(settings: CleanupSettings) -> str:
    parts = []
    if settings.denoise > 0:
        luma = settings.denoise * 2
        chroma = settings.denoise * 1.5
        parts.append(f"hqdn3d={luma:.1f}:{chroma:.1f}:{luma * 2:.1f}:{chroma * 2:.1f}")
    if settings.deblock > 0:
        quality = min(6, max(0, round(settings.deblock)))
        parts.append(f"spp=quality={quality}")
    if settings.deband:
        parts.append("deband")
    return ",".join(parts) if parts else "null"


def build_color_filter(settings: ColorSettings) -> str:
    return (
        f"eq=brightness={settings.brightness}:contrast={settings.contrast}"
        f":saturation={settings.saturation}:gamma={settings.gamma}"
    )
