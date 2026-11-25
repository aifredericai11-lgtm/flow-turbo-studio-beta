# -*- coding: utf-8 -*-
"""
forja/hw_accel.py — Camada Unificada Multiplataforma (Windows RTX NVENC + MacBook Apple Silicon VideoToolbox + Linux)
====================================================================================================================
Detecta automaticamente:
- Binários `ffmpeg` e `ffprobe` (`PATH`, `/opt/homebrew/bin` no Apple Silicon M1–M5, `/usr/local/bin` no Mac Intel e WinGet no Windows).
- Encoder de vídeo por hardware:
  * macOS (`darwin`): `h264_videotoolbox` (Apple Media Engine M1/M2/M3/M4/M5 — ~300+ fps sem gastar CPU)
  * Windows / Linux c/ GPU NVIDIA: `h264_nvenc`
  * Fallback universal: `libx264 -preset veryfast`
- Caminhos nativos do Google Chrome, pastas isoladas `FlowProfile` (`:9225..:9244`) e abertura persistente sem depender de WMI no Mac/Linux.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"


def _localizar_binario_midia(nome: str) -> str:
    # 1) Homebrew Apple Silicon / Intel Mac + locais Unix comuns
    if IS_MAC or not IS_WIN:
        for p in (
            f"/opt/homebrew/bin/{nome}",
            f"/usr/local/bin/{nome}",
            os.path.expanduser(f"~/.local/bin/{nome}"),
        ):
            if os.path.isfile(p) and os.access(p, os.X_OK):
                return p

    # 2) PATH global do sistema
    achado = shutil.which(nome)
    if achado:
        return achado

    # 3) WinGet / Chocolatey / Scoop no Windows
    if IS_WIN:
        padroes_win = [
            os.path.expandvars(rf"%LOCALAPPDATA%\Microsoft\WinGet\Packages\*FFmpeg*\**\bin\{nome}.exe"),
            rf"C:\ffmpeg\bin\{nome}.exe",
            os.path.expandvars(rf"%USERPROFILE%\scoop\apps\ffmpeg\current\bin\{nome}.exe"),
            rf"C:\ProgramData\chocolatey\bin\{nome}.exe",
        ]
        for pad in padroes_win:
            matches = glob.glob(pad, recursive=True)
            if matches:
                return matches[0]

    return nome


FFMPEG_BIN: str = _localizar_binario_midia("ffmpeg")
FFPROBE_BIN: str = _localizar_binario_midia("ffprobe")
_ENCODER_CACHE: str | None = None


def encontrar_ffmpeg_bin() -> str:
    return FFMPEG_BIN


def encontrar_ffprobe_bin() -> str:
    return FFPROBE_BIN


def _testar_encoder_ffmpeg(encoder: str) -> bool:
    try:
        proc = subprocess.run(
            [
                FFMPEG_BIN,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=256x256:d=0.1",
                "-frames:v",
                "1",
                "-c:v",
                encoder,
                "-pix_fmt",
                "yuv420p",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            timeout=6,
            check=False,
        )
        return proc.returncode == 0
    except Exception:
        return False


def detectar_encoder_h264() -> str:
    """Retorna 'h264_videotoolbox' (Mac), 'h264_nvenc' (Windows/Linux NVIDIA) ou 'libx264' (CPU)."""
    global _ENCODER_CACHE
    if _ENCODER_CACHE is not None:
        return _ENCODER_CACHE

    ordem = ["h264_videotoolbox", "libx264"] if IS_MAC else ["h264_nvenc", "libx264"]
    for enc in ordem:
        if enc == "libx264" or _testar_encoder_ffmpeg(enc):
            _ENCODER_CACHE = enc
            return enc
    _ENCODER_CACHE = "libx264"
    return _ENCODER_CACHE


def args_h264_hw(bitrate: str = "3.2M", maxrate: str = "4.5M", bufsize: str = "6M", cq: int = 22, fast: bool = False) -> list[str]:
    """
    Devolve a lista pronta de argumentos `-c:v ...` otimizada para a GPU local:
    - MacBook (M1/M2/M3/M4/M5 / Intel): `h264_videotoolbox` com `-allow_sw 1`
    - Windows/Linux RTX: `h264_nvenc`
    - Fallback CPU: `libx264`
    """
    enc = detectar_encoder_h264()
    if enc == "h264_videotoolbox":
        return [
            "-c:v",
            "h264_videotoolbox",
            "-b:v",
            bitrate,
            "-maxrate",
            maxrate,
            "-bufsize",
            bufsize,
            "-allow_sw",
            "1",
            "-pix_fmt",
            "yuv420p",
        ]
    if enc == "h264_nvenc":
        preset_nv = "p1" if fast else "p4"
        return [
            "-c:v",
            "h264_nvenc",
            "-preset",
            preset_nv,
            "-rc",
            "vbr",
            "-cq",
            str(cq),
            "-b:v",
            bitrate,
            "-maxrate",
            maxrate,
            "-bufsize",
            bufsize,
            "-pix_fmt",
            "yuv420p",
        ]
    return [
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast" if fast else "veryfast",
        "-crf",
        str(cq),
        "-pix_fmt",
        "yuv420p",
    ]


def resumo_hardware_local() -> tuple[str, str]:
    enc = detectar_encoder_h264()
    threads = os.cpu_count() or 8
    arch = platform.machine() or "x64"
    if IS_MAC:
        gpu_txt = f"Apple Silicon / macOS ({arch} · {enc} + Whisper int8)"
        cpu_txt = f"macOS {platform.mac_ver()[0] or ''} ({threads} Threads)".strip()
        return gpu_txt, cpu_txt
    if enc == "h264_nvenc":
        return "NVIDIA GPU (h264_nvenc + Whisper CUDA)", f"{platform.processor() or arch} ({threads} Threads)"
    return f"CPU Multi-Core ({enc} + Whisper int8)", f"{platform.processor() or arch} ({threads} Threads)"


def encontrar_chrome_bin() -> str:
    if IS_MAC:
        cands_mac = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
        for c in cands_mac:
            if os.path.isfile(c):
                return c
    elif IS_WIN:
        cands_win = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        for c in cands_win:
            if os.path.isfile(c):
                return c
    else:
        for b in ("google-chrome", "google-chrome-stable", "chromium-browser", "chromium"):
            p = shutil.which(b)
            if p:
                return p
    raise FileNotFoundError(
        "Google Chrome não encontrado. Instale em https://www.google.com/chrome/ "
        "(no Mac: /Applications/Google Chrome.app)."
    )


def pasta_perfil_flow(slot: int = 1) -> Path:
    suf = "" if slot <= 1 else f"_{slot:02d}"
    if IS_WIN:
        base = Path(os.path.expandvars(rf"%LOCALAPPDATA%\Google\Chrome\FlowProfile{suf}"))
    elif IS_MAC:
        base = Path(os.path.expanduser(f"~/Library/Application Support/Google/Chrome/FlowProfile{suf}"))
    else:
        base = Path(os.path.expanduser(f"~/.config/google-chrome-flow-profile{suf}"))
    base.mkdir(parents=True, exist_ok=True)
    return base


def caminho_telemetria_flow() -> Path:
    if IS_WIN and Path(r"C:\Hub001").exists():
        return Path(r"C:\Hub001\forja_live_telemetry.json")
    p = Path.home() / ".cache" / "flow_turbo_studio" / "forja_live_telemetry.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def disparar_chrome_persistente(
    porta: int,
    profile_dir: str | Path,
    ext_dir: str | Path,
    url_inicial: str = "https://flow.google.com/",
) -> int | None:
    """
    Abre uma instância isolada do Chrome que permanece viva após o término do script,
    tanto no MacBook (macOS) quanto no Windows e Linux, com todas as flags anti-App-Nap!
    """
    exe = encontrar_chrome_bin()
    prof_str = str(Path(profile_dir).resolve())
    ext_str = str(Path(ext_dir).resolve())
    os.makedirs(prof_str, exist_ok=True)

    args = [
        exe,
        f"--remote-debugging-port={porta}",
        "--remote-debugging-address=127.0.0.1",
        "--remote-allow-origins=http://127.0.0.1:8788,http://localhost:8788",
        f"--user-data-dir={prof_str}",
        f"--disable-extensions-except={ext_str}",
        f"--load-extension={ext_str}",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-features=CalculateNativeWinOcclusion,IntensiveWakeUpThrottling",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1420,900",
        url_inicial,
    ]

    if IS_WIN:
        creationflags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
        )
        proc = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
        )
        return proc.pid
    else:
        proc = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        return proc.pid
