"""
Edição — Etapa 3: Montagem Ultra-Dinâmica (Transição Mix Cross-Dissolve + J-Cut Audio + Punch-In no Corpo).
Regras de Alto Dinamismo:
- ZERO Flash Branco artificial: extinto o clarão branco (RGB 255) que quebrava a naturalidade.
- Transição MIX (xfade=transition=fade de 0.08s / ~2-3 frames + acrossfade J-Cut de 0.08s no áudio):
  funde o final da última consoante do Take A com o ataque da 1ª sílaba do Take B sem nenhuma pausa.
- Dinamismo de Câmera (Punch-In 1.065x nos takes intermediários do Corpo/Mecanismo):
  muda o plano focal na virada do Hook para o Corpo, mantendo Sem Zoom no Hook (Take 1) e Sem Zoom no CTA (Último Take).
- Saída: 1080x1920, 30fps, H.264 (CRF ~20), AAC 128k, +faststart.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from edicao.davinci_bridge import sincronizar_timeline_davinci
from forja.ler_viral import obter_duracao_video

FORMATOS_COM_MIX = {
    "aplicando_bicarbonato_na_coxa",
    "aplicando_no_pe",
    "formato_ugc_padrao",
}


def _tem_stream_audio(video_path: Path) -> bool:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(video_path),
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
    ).strip()
    return bool(out)


def montar_video(
    clipes_cortados: list[Path],
    destino_mp4: Path,
    formato: str = "aplicando_bicarbonato_na_coxa",
    usar_flash_branco: bool | None = None,
    frames_flash: int = 3,
    fps: int = 30,
    crf: int = 20,
    sincronizar_resolve: bool = True,
    usar_punch_in_corpo: bool = True,
) -> dict[str, Any]:
    """
    Monta os clipes cortados em 1080x1920 30fps com Transição MIX (xfade + acrossfade J-Cut)
    e Punch-In dinâmico (1.065x) nos takes intermediários (Corpo), sem zoom no Hook nem no CTA
    e SEM flash branco artificial.
    """
    if not clipes_cortados:
        raise ValueError("Lista de clipes cortados está vazia.")

    destino_mp4.parent.mkdir(parents=True, exist_ok=True)

    # Duração do Mix (2 a 3 frames @ 30fps = ~0.08s) para colar as falas sem buraco e sem clarão branco
    usar_transicao_mix = True if usar_flash_branco is None else bool(usar_flash_branco)
    duracao_mix = round(max(2, min(4, frames_flash)) / float(fps), 4)  # ex: 2.5-3 frames = 0.08s..0.10s

    inputs: list[str] = []
    filtros: list[str] = []
    duracoes_individuais: list[float] = []

    n = len(clipes_cortados)
    for i, clipe in enumerate(clipes_cortados):
        inputs.extend(["-i", str(clipe)])
        dur = obter_duracao_video(clipe)
        duracoes_individuais.append(round(dur, 3))

        eh_hook = i == 0
        eh_cta = i == (n - 1)
        eh_corpo = (not eh_hook) and (not eh_cta)

        if eh_corpo and usar_punch_in_corpo:
            # Punch-In dinâmico de 1.065x nos takes do meio (muda o plano na transição do Mix!)
            cadeia_v = [
                "scale=1150:2044:force_original_aspect_ratio=increase",
                "crop=1080:1920:(iw-1080)/2:(ih-1920)/2",
                "setsar=1",
                f"fps={fps}",
                "format=yuv420p",
                "setpts=PTS-STARTPTS",
            ]
        else:
            # Hook e CTA 100% sem zoom para não deslocar elementos
            cadeia_v = [
                "scale=1080:1920:force_original_aspect_ratio=decrease",
                "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
                "setsar=1",
                f"fps={fps}",
                "format=yuv420p",
                "setpts=PTS-STARTPTS",
            ]

        filtros.append(f"[{i}:v:0]{','.join(cadeia_v)}[v{i}]")

        if _tem_stream_audio(clipe):
            filtros.append(
                f"[{i}:a:0]aresample=48000,atrim=duration={dur:.3f},asetpts=PTS-STARTPTS[a{i}]"
            )
        else:
            filtros.append(f"anullsrc=r=48000:cl=stereo:d={dur:.3f}[a{i}]")

    # Constrói a cadeia de Transição MIX (xfade + acrossfade) se houver >= 2 takes
    if n == 1 or not usar_transicao_mix:
        streams_concat = "".join(f"[v{i}][a{i}]" for i in range(n))
        filtros.append(f"{streams_concat}concat=n={n}:v=1:a=1[vout][aout]")
        overlap_efetivo = 0.0
    else:
        overlap_efetivo = duracao_mix
        v_prev = "[v0]"
        a_prev = "[a0]"
        dur_acumulada = duracoes_individuais[0]

        for i in range(1, n):
            offset_xfade = round(max(0.05, dur_acumulada - overlap_efetivo), 4)
            v_next = "[vout]" if i == (n - 1) else f"[vx{i}]"
            a_next = "[aout]" if i == (n - 1) else f"[ax{i}]"

            # Mix óptico suave e rápido (fade/mix entre os dois takes, ZERO tela branca!)
            filtros.append(
                f"{v_prev}[v{i}]xfade=transition=fade:duration={overlap_efetivo:.4f}:offset={offset_xfade:.4f}{v_next}"
            )
            # J-Cut / Audio Cross-Mix sem queda de volume (curva triangular/logarítmica)
            filtros.append(
                f"{a_prev}[a{i}]acrossfade=d={overlap_efetivo:.4f}:c1=tri:c2=tri{a_next}"
            )

            dur_acumulada = offset_xfade + duracoes_individuais[i]
            v_prev = v_next
            a_prev = a_next

    cmd_nvenc = [
        "ffmpeg",
        "-nostdin",
        "-y",
        "-loglevel",
        "error",
        *inputs,
        "-filter_complex",
        ";".join(filtros),
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        "-c:v",
        "h264_nvenc",
        "-preset",
        "p2",
        "-rc",
        "vbr",
        "-cq",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "48000",
        "-movflags",
        "+faststart",
        str(destino_mp4),
    ]
    if subprocess.run(cmd_nvenc).returncode != 0:
        cmd_cpu = [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-loglevel",
            "error",
            *inputs,
            "-filter_complex",
            ";".join(filtros),
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-crf",
            str(crf),
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            str(destino_mp4),
        ]
        subprocess.run(cmd_cpu, check=True)

    # Verifica especificações do arquivo montado
    probe_out = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(destino_mp4),
            ],
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    )
    v_stream = next(s for s in probe_out["streams"] if s.get("codec_type") == "video")
    a_stream = next(s for s in probe_out["streams"] if s.get("codec_type") == "audio")
    duracao_final = round(float(probe_out["format"]["duration"]), 3)

    # Calcula timestamps exatos de início/fim de cada take considerando o overlap do Mix (xfade/acrossfade)
    timestamps_takes = []
    cursor = 0.0
    for idx, d in enumerate(duracoes_individuais, start=1):
        eh_corpo = 1 < idx < n
        ini_take = round(max(0.0, cursor), 3)
        fim_take = round(ini_take + d, 3)
        timestamps_takes.append(
            {
                "take": idx,
                "papel": "hook" if idx == 1 else ("cta" if idx == n else "body"),
                "inicio_s": ini_take,
                "fim_s": fim_take,
                "duracao_s": d,
                "zoom_aplicado": bool(eh_corpo and usar_punch_in_corpo),
                "transicao_mix_s": overlap_efetivo if idx > 1 else 0.0,
                "flash_entrada_frames": 0,
            }
        )
        cursor = fim_take - overlap_efetivo

    status_davinci = {"conectado": False, "mensagem": "Sincronização desativada"}
    if sincronizar_resolve:
        status_davinci = sincronizar_timeline_davinci(
            nome_projeto="Esteira_Forja_Edicao",
            nome_timeline=f"Timeline_{destino_mp4.parent.name}",
            clipes_cortados=clipes_cortados,
            duracoes_s=duracoes_individuais,
            pasta_saida=destino_mp4.parent,
        )

    return {
        "arquivo_montado": str(destino_mp4),
        "resolucao": f"{v_stream.get('width')}x{v_stream.get('height')}",
        "codec_video": v_stream.get("codec_name"),
        "crf": crf,
        "codec_audio": a_stream.get("codec_name"),
        "bitrate_audio": "128k",
        "faststart": True,
        "transicao_tipo": "xfade_mix_jcut",
        "duracao_mix_s": overlap_efetivo,
        "flash_branco_aplicado": False,
        "frames_flash": 0,
        "punch_in_corpo": usar_punch_in_corpo,
        "zoom_hook": False,
        "zoom_cta": False,
        "duracao_final_s": duracao_final,
        "takes": timestamps_takes,
        "davinci_resolve": status_davinci,
    }
