"""
Ponte DaVinci Resolve (Scripting API + FCPXML Timeline + Servidor MCP) para a Esteira de Edição.
1. Conecta ao DaVinci Resolve local via fusionscript.dll / DaVinciResolveScript.py quando aberto.
2. Gera sempre um arquivo de timeline FCPXML (.fcpxml) compatível com DaVinci Resolve (File -> Import -> Timeline),
   garantindo importação instantânea mesmo com o Resolve fechado ou na versão Free.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

RESOLVE_SCRIPT_MODULES = r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules"
RESOLVE_SCRIPT_LIB = r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll"


def conectar_davinci() -> tuple[Any | None, str]:
    """Tenta conectar à instância aberta do DaVinci Resolve via API oficial."""
    try:
        if os.path.isdir(RESOLVE_SCRIPT_MODULES) and RESOLVE_SCRIPT_MODULES not in sys.path:
            sys.path.append(RESOLVE_SCRIPT_MODULES)
        if os.path.isfile(RESOLVE_SCRIPT_LIB):
            os.environ.setdefault("RESOLVE_SCRIPT_LIB", RESOLVE_SCRIPT_LIB)
        import DaVinciResolveScript as dvr  # type: ignore

        resolve = dvr.scriptapp("Resolve")
        if resolve is None:
            return None, "DaVinci Resolve fechado ou 'External scripting using' desativado nas Preferências."
        return resolve, "Conectado ao DaVinci Resolve via fusionscript.dll."
    except Exception as exc:
        return None, f"Indisponível ({exc})"


def gerar_fcpxml_davinci(
    nome_timeline: str,
    clipes_cortados: list[Path],
    duracoes_s: list[float],
    destino_fcpxml: Path,
    fps: int = 30,
) -> Path:
    """
    Gera timeline FCPXML 1.9 vertical (1080x1920, 30fps) nativa para o DaVinci Resolve.
    Pode ser importada via API (ImportTimelineFromFile) ou manualmente em File -> Import -> Timeline.
    """
    destino_fcpxml.parent.mkdir(parents=True, exist_ok=True)
    total_frames = sum(max(1, int(round(d * fps))) for d in duracoes_s)

    resources_xml = [
        f'    <format id="r1" name="FFVideoFormat1080x1920p{fps}" frameDuration="1/{fps}s" width="1080" height="1920" colorSpace="1-1-1 (Rec. 709)"/>'
    ]
    spine_xml = []
    offset_frames = 0

    for idx, (clipe, dur) in enumerate(zip(clipes_cortados, duracoes_s), start=1):
        res_id = f"r{idx + 1}"
        frames = max(1, int(round(dur * fps)))
        uri = clipe.resolve().as_uri()
        nome_esc = escape(clipe.name)
        resources_xml.append(
            f'    <asset id="{res_id}" name="{nome_esc}" src="{escape(uri)}" start="0s" duration="{frames}/{fps}s" hasVideo="1" hasAudio="1" format="r1"/>'
        )
        spine_xml.append(
            f'            <asset-clip name="{nome_esc}" ref="{res_id}" offset="{offset_frames}/{fps}s" duration="{frames}/{fps}s" start="0s" format="r1"/>'
        )
        offset_frames += frames

    conteudo = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!DOCTYPE fcpxml>\n"
        '<fcpxml version="1.9">\n'
        "  <resources>\n"
        + "\n".join(resources_xml)
        + "\n  </resources>\n"
        '  <library>\n'
        f'    <event name="{escape(nome_timeline)}">\n'
        f'      <project name="{escape(nome_timeline)}">\n'
        f'        <sequence format="r1" duration="{total_frames}/{fps}s" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">\n'
        "          <spine>\n"
        + "\n".join(spine_xml)
        + "\n          </spine>\n"
        "        </sequence>\n"
        "      </project>\n"
        "    </event>\n"
        "  </library>\n"
        "</fcpxml>\n"
    )
    destino_fcpxml.write_text(conteudo, encoding="utf-8")
    return destino_fcpxml


def sincronizar_timeline_davinci(
    nome_projeto: str,
    nome_timeline: str,
    clipes_cortados: list[Path],
    duracoes_s: list[float] | None = None,
    pasta_saida: Path | None = None,
) -> dict[str, Any]:
    """
    1. Salva a timeline vertical 1080x1920 em FCPXML (.fcpxml) na pasta de trabalho.
    2. Se o DaVinci Resolve estiver aberto com External Scripting ativo, importa os clipes
       e cria a timeline 1080x1920 diretamente no projeto ativo.
    """
    out_dir = pasta_saida or (clipes_cortados[0].parent.parent if clipes_cortados else Path.cwd())
    durs = duracoes_s or [5.0 for _ in clipes_cortados]
    fcpxml_path = gerar_fcpxml_davinci(
        nome_timeline=nome_timeline,
        clipes_cortados=clipes_cortados,
        duracoes_s=durs,
        destino_fcpxml=out_dir / f"{nome_timeline}.fcpxml",
    )

    resolve, msg = conectar_davinci()
    if resolve is None:
        return {
            "conectado": False,
            "fcpxml_gerado": str(fcpxml_path),
            "mensagem": f"{msg} Timeline FCPXML pronta para importação imediata em {fcpxml_path.name}.",
        }

    try:
        pm = resolve.GetProjectManager()
        proj = pm.LoadProject(nome_projeto) or pm.CreateProject(nome_projeto) or pm.GetCurrentProject()
        if not proj:
            return {
                "conectado": True,
                "sincronizado": False,
                "fcpxml_gerado": str(fcpxml_path),
                "mensagem": "Não foi possível obter projeto no Resolve.",
            }

        proj.SetSetting("timelineResolutionWidth", "1080")
        proj.SetSetting("timelineResolutionHeight", "1920")
        proj.SetSetting("timelineFrameRate", "30")

        mp = proj.GetMediaPool()
        itens = mp.ImportMedia([str(c.resolve()) for c in clipes_cortados])
        timeline = mp.CreateTimelineFromClips(nome_timeline, itens)
        if not timeline:
            timeline = mp.ImportTimelineFromFile(str(fcpxml_path))

        return {
            "conectado": True,
            "sincronizado": bool(timeline),
            "projeto": proj.GetName(),
            "timeline": nome_timeline,
            "fcpxml_gerado": str(fcpxml_path),
            "clipes_importados": len(clipes_cortados),
            "mensagem": "Timeline 1080x1920 sincronizada ao vivo no DaVinci Resolve.",
        }
    except Exception as exc:
        return {
            "conectado": True,
            "sincronizado": False,
            "fcpxml_gerado": str(fcpxml_path),
            "mensagem": f"Erro na API do Resolve ({exc}); FCPXML salvo.",
        }
