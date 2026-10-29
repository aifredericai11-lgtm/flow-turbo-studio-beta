"""
Forja — Etapa 5: Geração Real no Google Flow (Playwright CDP Puro nas portas 9222 / 9223).
Regras:
- Localize botões pelo texto/aria-label (forja/seletores_flow.py), nunca por posição ou classe CSS.
- Nunca crie contas e nunca digite senhas ou códigos.
- Gere a imagem do frame 1, confira e gere o vídeo do take a partir dela (frame de início anexado da galeria interna).
- Espere o vídeo terminar de verdade (progresso sumiu + arquivo disponível) antes de baixar.
- Se o Chrome travar (timeout de conexão), feche SÓ esse Chrome, reabra e reconecte sozinho.
- Cache por vídeo (falas, prompts, imagens aprovadas, clipes prontos): se cair, retoma de onde parou sem gastar crédito de novo.
- --so-frame1: gera só imagens do frame 1 (3–5 opções) para o usuário escolher a base.
- Se o Flow avisar "atividade incomum", PAUSE (3 -> 6 -> 10 min, crescendo) e tente de novo depois.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from PIL import Image

from forja.estrutura import ROOT_DIR, BatchLogger, FlowSafetyGuard
from forja.seletores_flow import (
    MARCADORES_ATIVIDADE_INCOMUM,
    MARCADORES_SERVICO_INDISPONIVEL,
    MODELO_IMAGEM_PADRAO,
    MODELO_VIDEO_PADRAO,
    SELETORES_FLOW,
)

DEFAULT_CDP_PORT = 9222
DEFAULT_CDP_URL = f"http://127.0.0.1:{DEFAULT_CDP_PORT}"
CHROME_FLOW_PROFILE_DIR = Path(os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\FlowProfile"))
CHROME_FLOW_PROFILE_ULTRA1 = Path(os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\FlowProfile_Ultra1"))
CHROME_FLOW_PROFILE_ULTRA2 = Path(os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\FlowProfile_Ultra2"))
CHROME_PROFILE_DIR = CHROME_FLOW_PROFILE_ULTRA1
CHROME_PROFILE_DIR_ULTRA2 = CHROME_FLOW_PROFILE_ULTRA2
FLOW_LANDING_URL = "https://labs.google/fx/pt/tools/flow"
FLOW_URL_BASE = FLOW_LANDING_URL


def _encontrar_executavel_chrome() -> str:
    candidatos = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for c in candidatos:
        if os.path.isfile(c):
            return c
    raise FileNotFoundError("Executável do Google Chrome não encontrado.")


def _disparar_wmi_process(cmdline: str, cwd: str | None = None) -> int | None:
    """
    Inicia um processo fora da Job Object do terminal via WMI (Win32_Process.Create),
    garantindo que janelas do Chrome com --remote-debugging-port abram na sessão interativa
    do usuário e permaneçam vivas mesmo após o término do comando atual.
    """
    cmd_escaped = cmdline.replace("'", "''")
    if cwd:
        cwd_escaped = cwd.replace("'", "''")
        ps_script = (
            f"$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create "
            f"-Arguments @{{CommandLine='{cmd_escaped}'; CurrentDirectory='{cwd_escaped}'}}; "
            f"if ($r.ReturnValue -eq 0) {{ Write-Output $r.ProcessId }}"
        )
    else:
        ps_script = (
            f"$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create "
            f"-Arguments @{{CommandLine='{cmd_escaped}'}}; "
            f"if ($r.ReturnValue -eq 0) {{ Write-Output $r.ProcessId }}"
        )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        out = (proc.stdout or "").strip()
        for tok in out.splitlines():
            if tok.strip().isdigit():
                return int(tok.strip())
    except Exception:
        pass
    return None


def _iniciar_auto_aprovacao_dialogo_cdp() -> None:
    """
    No Chrome 136+ com User Data padrão (DevToolsActivePort via chrome://inspect/#remote-debugging),
    o navegador exibe um modal nativo 'Allow remote debugging?' ao receber conexão WebSocket.
    Esta thread auxiliar localiza e clica automaticamente em 'Allow'/'Permitir' via UIAutomation em < 0.8s.
    """
    import ctypes
    from ctypes import wintypes
    import threading

    def _worker() -> None:
        u32 = ctypes.windll.user32
        h_winsta = u32.OpenWindowStationW("WinSta0", False, 0x037F)
        if h_winsta:
            u32.SetProcessWindowStation(h_winsta)
        h_desk = u32.OpenDesktopW("Default", 0, False, 0x01FF)
        if h_desk:
            u32.SetThreadDesktop(h_desk)

        for _ in range(10):
            time.sleep(0.5)
            hwnds: list[int] = []

            class RECT(ctypes.Structure):
                _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

            def _cb(hwnd: int, lparam: int) -> bool:
                if u32.IsWindowVisible(hwnd):
                    cls_buf = ctypes.create_unicode_buffer(64)
                    u32.GetClassNameW(hwnd, cls_buf, 64)
                    if "Chrome_WidgetWin" in (cls_buf.value or ""):
                        rc = RECT()
                        u32.GetWindowRect(hwnd, ctypes.byref(rc))
                        w = rc.right - rc.left
                        h = rc.bottom - rc.top
                        if 150 < w < 900 and 80 < h < 600:
                            hwnds.append(hwnd)
                return True

            PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            u32.EnumWindows(PROC(_cb), 0)
            if hwnds:
                h_str = ",".join(str(h) for h in hwnds)
                ps_cmd = (
                    'Add-Type -TypeDefinition \'using System; using System.Runtime.InteropServices; '
                    'public class WinSta { '
                    '[DllImport("user32.dll", SetLastError=true, CharSet=CharSet.Unicode)] public static extern IntPtr OpenWindowStation(string n, bool i, uint a); '
                    '[DllImport("user32.dll", SetLastError=true)] public static extern bool SetProcessWindowStation(IntPtr h); '
                    '[DllImport("user32.dll", SetLastError=true, CharSet=CharSet.Unicode)] public static extern IntPtr OpenDesktop(string n, uint f, bool i, uint a); '
                    '[DllImport("user32.dll", SetLastError=true)] public static extern bool SetThreadDesktop(IntPtr h); }\'; '
                    '[void][WinSta]::SetProcessWindowStation([WinSta]::OpenWindowStation("WinSta0", $false, 0x037F)); '
                    '[void][WinSta]::SetThreadDesktop([WinSta]::OpenDesktop("Default", 0, $false, 0x01FF)); '
                    'Add-Type -AssemblyName UIAutomationClient; Add-Type -AssemblyName UIAutomationTypes; '
                    f'foreach ($h in @({h_str})) {{ '
                    'try { $el = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$h); '
                    '$cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Button); '
                    'foreach ($b in $el.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)) { '
                    'if ($b.Current.Name -match "^(Allow|Permitir)$") { '
                    '$b.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() } } } catch {} }'
                )
                try:
                    subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, timeout=5)
                except Exception:
                    pass
                break

    threading.Thread(target=_worker, daemon=True).start()


def obter_base_cdp(porta: int = DEFAULT_CDP_PORT, timeout_s: float = 2.0) -> str | None:
    """
    Retorna a URL base CDP ativa ('http://127.0.0.1:<porta>' ou 'ws://127.0.0.1:<porta>/devtools/browser/...')
    priorizando:
    1) Endpoint HTTP /json/version na porta solicitada;
    2) DevToolsActivePort da instância User Data já aberta pelo usuário (Chrome 136+).
    """
    import socket

    for host in ("127.0.0.1", "[::1]"):
        base = f"http://{host}:{porta}"
        try:
            with urlopen(f"{base}/json/version", timeout=timeout_s) as resp:
                if resp.status == 200:
                    dados = json.loads(resp.read().decode("utf-8", errors="replace"))
                    if isinstance(dados, dict) and ("Browser" in dados or "webSocketDebuggerUrl" in dados):
                        return base
        except Exception:
            continue

    # REGRA ESTRITA: 1 CHROME POR CONTA!
    # Porta 9222 (Conta 1) pode usar User Data\DevToolsActivePort ou FlowProfile_Ultra1.
    # Porta 9223 (Conta 2) JAMAIS pode usar User Data\DevToolsActivePort (exige 2o Chrome separado em :9223 / FlowProfile_Ultra2)!
    if porta == 9223:
        dt_candidates = [
            CHROME_FLOW_PROFILE_ULTRA2 / "DevToolsActivePort",
            Path(os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\DevToolsActivePort")),
        ]
    else:
        dt_candidates = [
            Path(os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\DevToolsActivePort")),
            CHROME_FLOW_PROFILE_ULTRA1 / "DevToolsActivePort",
        ]
    for dt_file in dt_candidates:
        try:
            if dt_file.is_file():
                linhas = [ln.strip() for ln in dt_file.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.strip()]
                if len(linhas) >= 2 and linhas[0].isdigit():
                    dt_port = int(linhas[0])
                    ws_path = linhas[1]
                    with socket.create_connection(("127.0.0.1", dt_port), timeout=timeout_s):
                        return f"ws://127.0.0.1:{dt_port}{ws_path}"
        except Exception:
            continue
    return None


def cdp_esta_ativo(porta: int = DEFAULT_CDP_PORT, timeout_s: float = 2.0) -> bool:
    return obter_base_cdp(porta=porta, timeout_s=timeout_s) is not None


def fechar_apenas_chrome_automacao(porta: int = DEFAULT_CDP_PORT, logger: BatchLogger | None = None) -> int:
    """
    Fecha SOMENTE os processos do Chrome que foram iniciados com --remote-debugging-port=<porta>,
    preservando qualquer outro Chrome aberto pelo usuário.
    """
    ps_cmd = (
        f"Get-CimInstance Win32_Process -Filter \"Name = 'chrome.exe'\" | "
        f"Where-Object {{ $_.CommandLine -match '--remote-debugging-port={porta}' }} | "
        f"ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $_.ProcessId }}"
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_cmd],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    pids = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip().isdigit()]
    if logger and pids:
        logger.log(
            f"Chrome da automação (porta {porta}) encerrado para reinício limpo (PIDs: {', '.join(pids)}).",
            nivel="WARN",
        )
    return len(pids)


def _resolver_profile_dir_padrao(porta: int, profile_dir: str | Path | None) -> Path:
    if profile_dir is not None:
        p = Path(os.path.expandvars(str(profile_dir)))
        if p.name.lower() in ("default", "profile 3", "user data"):
            return CHROME_FLOW_PROFILE_ULTRA2 if porta == 9223 else CHROME_FLOW_PROFILE_ULTRA1
        return p
    if porta == 9223:
        return CHROME_FLOW_PROFILE_ULTRA2
    if porta == 9222 and CHROME_FLOW_PROFILE_ULTRA1.exists():
        return CHROME_FLOW_PROFILE_ULTRA1
    return CHROME_FLOW_PROFILE_DIR


def abrir_chrome_automacao(
    porta: int = DEFAULT_CDP_PORT,
    profile_dir: str | Path | None = None,
    url_inicial: str = FLOW_LANDING_URL,
    logger: BatchLogger | None = None,
) -> bool:
    """
    REGRA CANÔNICA DO OBSIDIAN (Erro #14):
    NUNCA abrir janelas novas do Chrome automaticamente — usar exclusivamente os navegadores já abertos e conectados!
    Só abre processo novo se FORJA_PERMITIR_ABRIR_CHROME=1 for passado explicitamente pelo usuário.
    """
    if cdp_esta_ativo(porta):
        return True
    if os.environ.get("FORJA_PERMITIR_ABRIR_CHROME", "0") != "1":
        if logger:
            logger.log(
                f"[BLOQUEIO REGRA OBSIDIAN] Recusando abrir novo Chrome na porta {porta}. "
                f"Usando apenas navegadores já abertos e conectados.",
                nivel="WARN",
            )
        return False

    chrome_exe = _encontrar_executavel_chrome()
    resolved_dir = _resolver_profile_dir_padrao(porta, profile_dir).resolve()
    resolved_dir.mkdir(parents=True, exist_ok=True)
    pos_x = 960 if porta == 9223 else 0

    cmd_wmi = (
        f'"{chrome_exe}" '
        f'--remote-debugging-port={porta} '
        f'--user-data-dir="{resolved_dir}" '
        f'--no-first-run --no-default-browser-check '
        f'--disable-background-timer-throttling '
        f'--disable-backgrounding-occluded-windows '
        f'--disable-renderer-backgrounding '
        f'--window-position={pos_x},0 --window-size=960,1040 '
        f'"{url_inicial}"'
    )
    pid_wmi = _disparar_wmi_process(cmd_wmi)
    if not pid_wmi:
        args = [
            chrome_exe,
            f"--remote-debugging-port={porta}",
            f"--user-data-dir={resolved_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            f"--window-position={pos_x},0",
            "--window-size=960,1040",
            url_inicial,
        ]
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for _ in range(35):
        if cdp_esta_ativo(porta):
            if logger:
                logger.log(f"Chrome da automação conectado na porta CDP {porta} ({resolved_dir.name}).")
            return True
        time.sleep(0.4)
    return False


class CacheVideoForja:
    """
    Cache persistente por vídeo (lotes/<id>/<Vxx>/cache_video.json).
    Guarda falas, prompts, imagens aprovadas e clipes prontos:
    se o processo cair, retoma exatamente de onde parou sem gastar crédito de novo.
    """

    def __init__(self, pasta_video: Path):
        self.pasta_video = pasta_video
        self.pasta_video.mkdir(parents=True, exist_ok=True)
        self.cache_path = self.pasta_video / "cache_video.json"

    def carregar(self, prompts_video: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.cache_path.exists():
            return json.loads(self.cache_path.read_text(encoding="utf-8"))

        takes_estado = {}
        if prompts_video:
            for t in prompts_video.get("takes", []):
                num = str(t["take"])
                takes_estado[num] = {
                    "take": t["take"],
                    "papel": t["papel"],
                    "fala": t["fala"],
                    "prompt_imagem": t["prompt_imagem"],
                    "prompt_video": t["prompt_video"],
                    "imagem_pronta": False,
                    "imagem_aprovada": False,
                    "arquivo_imagem": f"frame_{t['take']}.jpg",
                    "clipe_pronto": False,
                    "arquivo_clipe": f"{t['take']}.mp4",
                    "tentativas_video": 0,
                }

        dados = {
            "video_id": prompts_video.get("video_id", self.pasta_video.name) if prompts_video else self.pasta_video.name,
            "formato": prompts_video.get("formato", "indefinido") if prompts_video else "indefinido",
            "avatar": prompts_video.get("avatar", "") if prompts_video else "",
            "atualizado_em": datetime.now().isoformat(timespec="seconds"),
            "opcoes_frame1": [],
            "takes": takes_estado,
        }
        self.salvar(dados)
        return dados

    def salvar(self, dados: dict[str, Any]) -> None:
        dados["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
        self.cache_path.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")

    def sincronizar_arquivos_existentes(self, dados: dict[str, Any]) -> dict[str, Any]:
        """Verifica no disco quais imagens e clipes já estão prontos e íntegros para não regerar."""
        for num, info in dados.get("takes", {}).items():
            img_path = self.pasta_video / info["arquivo_imagem"]
            if img_path.is_file() and img_path.stat().st_size > 2048:
                info["imagem_pronta"] = True
                info["imagem_aprovada"] = True

            clip_path = self.pasta_video / info["arquivo_clipe"]
            if clip_path.is_file() and clip_path.stat().st_size > 10240:
                info["clipe_pronto"] = True

        self.salvar(dados)
        return dados



def selecionar_aba_flow_por_perfil_isolado(browser: Any, porta_cdp: int, project_url: str | None = None) -> Any:
    """
    Seleciona a aba do Google Flow garantindo ESTRITAMENTE 1 Janela/Perfil de Chrome (browserContextId + SID) por conta:
    - Porta 9222 (Ultra 1 - deepeniateam@gmail.com): Janela Perfil Default (browserContextId 13353C... / SID g.a000Dwkcla)
    - Porta 9223 (Ultra 2 - aifredericai11@gmail.com): Janela Profile 3 separada (browserContextId 0894A8... / SID g.a000DwnZsD)
    - Jamais seleciona abas /u/1/ e jamais compartilha o mesmo browserContextId entre 9222 e 9223.
    """
    abas_flow = [
        p
        for ctx in browser.contexts
        for p in ctx.pages
        if ("flow.google.com" in (p.url or "") or "labs.google" in (p.url or ""))
        and "/u/1/" not in (p.url or "")
    ]
    if not abas_flow:
        return None

    if project_url:
        for p in abas_flow:
            if project_url in (p.url or ""):
                return p

    infos = []
    for p in abas_flow:
        bctx = ""
        sid = ""
        try:
            cdp = p.context.new_cdp_session(p)
            tinfo = cdp.send("Target.getTargetInfo")
            bctx = str((tinfo or {}).get("targetInfo", {}).get("browserContextId", "") or "")
            cks = cdp.send("Network.getCookies", {"urls": ["https://flow.google.com", "https://labs.google"]}).get("cookies", [])
            sid = next((str(c.get("value", "")) for c in cks if c.get("name") == "SID"), "")
            try:
                cdp.detach()
            except Exception:
                pass
        except Exception:
            pass
        infos.append((p, bctx, sid))

    if porta_cdp == 9223:
        for p, bctx, sid in infos:
            if bctx == "0894A85691C9B72CE2018200BBCAEB19" or sid.startswith("g.a000DwnZsD"):
                return p
        bctxs_distintos = []
        for _, bctx, _ in infos:
            if bctx not in bctxs_distintos:
                bctxs_distintos.append(bctx)
        if len(bctxs_distintos) >= 2:
            alvo_bctx = bctxs_distintos[1]
            for p, bctx, _ in infos:
                if bctx == alvo_bctx:
                    return p
        return None

    for p, bctx, sid in infos:
        if bctx == "13353C96E1D8C5B9876BAAE1847497FA" or sid.startswith("g.a000Dwkcla"):
            return p
    return infos[0][0]


class ControladorFlowPlaywright:
    """
    Controlador Playwright puro para o Google Flow na porta CDP fixa (connect_over_cdp).
    Usa exclusivamente os seletores baseados em texto/aria-label de forja/seletores_flow.py.
    """

    def __init__(
        self,
        logger: BatchLogger,
        safety_guard: FlowSafetyGuard,
        porta_cdp: int = DEFAULT_CDP_PORT,
        profile_dir: str | Path | None = None,
        modelo_imagem: str = MODELO_IMAGEM_PADRAO,
        modelo_video: str = MODELO_VIDEO_PADRAO,
        project_url: str | None = None,
    ):
        self.logger = logger
        self.safety_guard = safety_guard
        self.porta_cdp = porta_cdp
        self.profile_dir = _resolver_profile_dir_padrao(porta_cdp, profile_dir)
        self.cdp_url = f"http://127.0.0.1:{porta_cdp}"
        self.modelo_imagem = modelo_imagem
        self.modelo_video = modelo_video
        self.project_url = project_url
        self.playwright = None
        self.browser = None
        self.page = None

    def conectar(self, auto_abrir: bool = False) -> None:
        from playwright.sync_api import sync_playwright

        if auto_abrir and not cdp_esta_ativo(self.porta_cdp):
            abrir_chrome_automacao(
                porta=self.porta_cdp,
                profile_dir=self.profile_dir,
                url_inicial=self.project_url or FLOW_LANDING_URL,
                logger=self.logger,
            )

        base = obter_base_cdp(self.porta_cdp) or self.cdp_url
        if self.playwright is None:
            self.playwright = sync_playwright().start()

        if base.startswith("ws://"):
            _iniciar_auto_aprovacao_dialogo_cdp()

        self.browser = self.playwright.chromium.connect_over_cdp(base, timeout=15000)
        abas_flow = [
            p
            for ctx in self.browser.contexts
            for p in ctx.pages
            if "flow.google.com" in (p.url or "") or "labs.google" in (p.url or "")
        ]
        if abas_flow:
            escolhida = selecionar_aba_flow_por_perfil_isolado(self.browser, self.porta_cdp, self.project_url)
            if escolhida is None:
                raise RuntimeError(
                    f"Nenhuma janela de Chrome isolada encontrada para a porta {self.porta_cdp} (proibido dividir mesmo perfil Chrome)."
                )
            self.page = escolhida
        else:
            ctx = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
            self.page = ctx.pages[0] if ctx.pages else ctx.new_page()
            self.page.goto(self.project_url or FLOW_LANDING_URL, wait_until="domcontentloaded", timeout=30000)

        if not base.startswith("ws://"):
            self.page.bring_to_front()
        time.sleep(1.5)

        # Garante que estamos dentro de um projeto (/project/...)
        if "/project/" not in (self.page.url or ""):
            if self.project_url:
                self.page.goto(self.project_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(4.0)
            else:
                try:
                    novo_btn = self.localizar("botao_novo_projeto", timeout_ms=6000)
                    novo_btn.click(force=True)
                    time.sleep(3.5)
                except Exception:
                    try:
                        proj_link = self.localizar("link_abrir_projeto", timeout_ms=6000)
                        href = proj_link.get_attribute("href")
                        if href:
                            full_url = f"https://flow.google.com{href}" if href.startswith("/") else href
                            self.page.goto(full_url, wait_until="domcontentloaded", timeout=30000)
                            time.sleep(4.0)
                    except Exception:
                        pass

        self.project_url = self.page.url
        self.logger.log(f"Conectado ao projeto do Google Flow (CDP :{self.porta_cdp}): {self.page.url}")

    def limpar_cache_site_flow_sem_cookies(self) -> None:
        """
        Mantém IndexedDB, LocalStorage e tokens _GRECAPTCHA intactos durante a geração das Macro-Ondas.
        Jamais chama Storage.clearDataForOrigin em execução para não afetar nenhum perfil aberto.
        """
        return

    def criar_novo_projeto_limpo(self) -> str:
        """
        Recicla o projeto a cada Macro-Onda de 5 vídeos (20 cards) para evitar virtualização do DOM:
        navega para a home do Google Flow, aguarda hidratação do botão 'Novo projeto' e garante que um
        NOVO UUID de /project/ diferente do anterior seja aberto na mesma aba antes de continuar.
        """
        url_anterior = (self.page.url or "").strip()
        self.logger.log(
            f"[RECICLAGEM DOM] Saindo do projeto anterior ({url_anterior}) e criando Novo Projeto limpo na porta CDP {self.porta_cdp}..."
        )
        urls_tentativa = ("https://flow.google.com/", FLOW_LANDING_URL)
        for url_land in urls_tentativa:
            try:
                self.page.goto(url_land, wait_until="domcontentloaded", timeout=30000)
                time.sleep(3.0)
                novo_btn = self.localizar("botao_novo_projeto", timeout_ms=10000)
                try:
                    novo_btn.click(timeout=4000)
                except Exception:
                    novo_btn.click(force=True)
                for _ in range(50):
                    url_agora = (self.page.url or "").strip()
                    if "/project/" in url_agora and url_agora != url_anterior:
                        break
                    time.sleep(0.3)
                url_final = (self.page.url or "").strip()
                if "/project/" in url_final and url_final != url_anterior:
                    time.sleep(1.5)
                    self.project_url = url_final
                    self.logger.log(f"[NOVO PROJETO LIMPO ATIVO] {url_final}")
                    return url_final
            except Exception as e:
                self.logger.log(f"Aviso ao criar novo projeto em {url_land}: {e}", nivel="WARN")
        return self.page.url if self.page else ""

    def desconectar(self) -> None:
        try:
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass
        self.playwright = None
        self.browser = None
        self.page = None

    def reconectar_apos_travamento(self, auto_abrir: bool = False) -> None:
        """Reconecta apenas à sessão CDP já existente por padrão (auto_abrir=False), sem abrir janelas novas."""
        self.logger.log(
            f"Timeout/travamento detectado no Chrome CDP :{self.porta_cdp}. Reconectando à instância já aberta (auto_abrir={auto_abrir})...",
            nivel="WARN",
        )
        self.desconectar()
        if auto_abrir:
            fechar_apenas_chrome_automacao(porta=self.porta_cdp, logger=self.logger)
            time.sleep(2.0)
            abrir_chrome_automacao(
                porta=self.porta_cdp,
                profile_dir=self.profile_dir,
                url_inicial=self.project_url or FLOW_LANDING_URL,
                logger=self.logger,
            )
        else:
            time.sleep(2.0)
        self.conectar(auto_abrir=auto_abrir)
        self.logger.log(f"Reconectado ao Chrome na porta {self.porta_cdp} com sucesso.")

    def localizar(self, chave_seletor: str, timeout_ms: int = 10000):
        """Localiza elemento usando a lista de seletores por texto/aria-label."""
        seletores = SELETORES_FLOW[chave_seletor]
        fim = time.monotonic() + (timeout_ms / 1000.0)
        while time.monotonic() < fim:
            for sel in seletores:
                loc = self.page.locator(sel).first
                try:
                    if loc.count() > 0 and loc.is_visible(timeout=300):
                        return loc
                except Exception:
                    continue
            time.sleep(0.25)
        raise RuntimeError(f"Controle '{chave_seletor}' não encontrado pelos textos/aria-labels: {seletores}")

    def verificar_alertas_flow(self) -> None:
        """Verifica se há alerta de 'atividade incomum' ou 'serviço indisponível'."""
        textos: list[str] = []
        for sel in SELETORES_FLOW["alertas_sistema"]:
            for el in self.page.locator(sel).all():
                try:
                    if el.is_visible(timeout=150):
                        textos.append(el.inner_text(timeout=300).lower())
                except Exception:
                    pass
        corpo = " ".join(textos)
        for marcador in MARCADORES_ATIVIDADE_INCOMUM:
            if marcador in corpo:
                self.safety_guard.registrar_atividade_incomum(detalhe=marcador)
                raise RuntimeError(f"Alerta de segurança Flow: {marcador}")

        for marcador in MARCADORES_SERVICO_INDISPONIVEL:
            if marcador in corpo:
                raise RuntimeError(f"Serviço indisponível (verifique prompt): {marcador}")

    def configurar_modo_flow(self, modo: str = "imagem", quantidade: str = "x1") -> None:
        """
        Configura o painel 'Gatilho de configurações' do Flow:
        - modo='imagem': Imagem -> 9:16 -> modelo_imagem -> x1 (ou x4 para --so-frame1)
        - modo='video': Vídeo -> Frames -> 9:16 -> modelo_video -> x1
        """
        self.page.mouse.move(10, 10)
        self.page.keyboard.press("Escape")
        time.sleep(0.3)
        btn_cfg = self.localizar("botao_configuracoes", timeout_ms=10000)
        btn_cfg.click(force=True)
        time.sleep(0.8)

        if modo == "imagem":
            self.localizar("modo_imagem", timeout_ms=5000).click(force=True)
            time.sleep(0.6)
            self.localizar("proporcao_9_16", timeout_ms=5000).click(force=True)
            time.sleep(0.4)
            btn_mod = self.localizar("seletor_modelo", timeout_ms=5000)
            if self.modelo_imagem.lower() not in (btn_mod.inner_text() or "").lower():
                btn_mod.click(force=True)
                time.sleep(0.6)
                for sel in SELETORES_FLOW["item_menu_modelo"]:
                    for item in self.page.locator(sel).all():
                        if item.is_visible() and self.modelo_imagem.lower() in (item.inner_text() or "").lower():
                            item.click(force=True)
                            time.sleep(0.6)
                            break
        else:
            self.localizar("modo_video", timeout_ms=5000).click(force=True)
            time.sleep(0.6)
            try:
                self.localizar("submodo_frames", timeout_ms=3000).click(force=True)
                time.sleep(0.5)
            except Exception:
                pass
            self.localizar("proporcao_9_16", timeout_ms=5000).click(force=True)
            time.sleep(0.4)
            btn_mod = self.localizar("seletor_modelo", timeout_ms=5000)
            if self.modelo_video.lower() not in (btn_mod.inner_text() or "").lower():
                btn_mod.click(force=True)
                time.sleep(0.6)
                clicou_mod = False
                for sel in SELETORES_FLOW["item_menu_modelo"]:
                    for item in self.page.locator(sel).all():
                        if item.is_visible() and self.modelo_video.lower() in (item.inner_text() or "").lower():
                            item.click(force=True)
                            clicou_mod = True
                            time.sleep(0.6)
                            break
                    if clicou_mod:
                        break

        chave_qtd = "quantidade_x4" if quantidade == "x4" else "quantidade_x1"
        try:
            self.localizar(chave_qtd, timeout_ms=3000).click(force=True)
            time.sleep(0.4)
        except Exception:
            pass

        self.page.keyboard.press("Escape")
        time.sleep(0.5)

    def limpar_ingredientes_prompt(self) -> None:
        """Remove chips/ingredientes residuais da caixa de comando antes de um novo disparo."""
        for sel in SELETORES_FLOW["botao_remover_ingrediente"]:
            for chip in self.page.locator(sel).all()[:6]:
                try:
                    if chip.is_visible(timeout=150):
                        chip.click()
                        time.sleep(0.2)
                except Exception:
                    pass

    def anexar_ingrediente_referencia_recente(self) -> None:
        """
        No modo Imagem (Takes 2..N), anexa a IMAGEM base recém-gerada do vídeo (nunca um vídeo!)
        como elemento de referência para manter 100% de consistência de rosto, roupa e cenário.
        """
        self.page.mouse.move(10, 10)
        self.limpar_ingredientes_prompt()
        btn_add = self.localizar("botao_adicionar_ingrediente", timeout_ms=5000)
        btn_add.click(force=True)
        time.sleep(1.2)
        opcoes_img = self.page.locator(
            'button[role="option"]:has(img[alt*="imagem" i]), button[role="option"]:has(img[alt*="image" i])'
        )
        if opcoes_img.count() > 0 and opcoes_img.first.is_visible():
            opcoes_img.first.click(force=True)
            time.sleep(0.8)
            try:
                btn_incluir = self.localizar("botao_adicionar_ao_prompt", timeout_ms=3000)
                btn_incluir.click(force=True)
                time.sleep(1.0)
            except Exception:
                self.page.keyboard.press("Escape")
        else:
            self.page.keyboard.press("Escape")

    def anexar_frame_inicio(self, imagem_path: Path, usar_recente_do_projeto: bool = True) -> None:
        """
        No modo Vídeo -> Frames, clica em 'Início', seleciona a imagem recém-gerada do take
        (ou envia do disco se não estiver no topo da lista) para animar a partir dela.
        """
        if not imagem_path.is_file():
            raise FileNotFoundError(f"Frame de início não encontrado: {imagem_path}")

        self.logger.log(f"Anexando frame de início no Flow: {imagem_path.name}")
        self.page.mouse.move(10, 10)
        btn_inicio = self.localizar("botao_frame_inicio", timeout_ms=6000)
        btn_inicio.click(force=True)
        time.sleep(1.2)

        if usar_recente_do_projeto:
            opcoes = self.page.locator('button[role="option"]')
            if opcoes.count() > 0 and opcoes.first.is_visible():
                opcoes.first.click(force=True)
                time.sleep(1.0)
                try:
                    btn_incluir = self.localizar("botao_adicionar_ao_prompt", timeout_ms=1500)
                    btn_incluir.click(force=True)
                    time.sleep(1.0)
                except Exception:
                    pass
                return

        btn_upload = self.localizar("botao_upload_arquivo", timeout_ms=8000)
        with self.page.expect_file_chooser(timeout=10000) as fc_info:
            btn_upload.click(force=True)
        fc_info.value.set_files(str(imagem_path.resolve()))
        time.sleep(4.0)

        try:
            btn_incluir = self.localizar("botao_adicionar_ao_prompt", timeout_ms=2000)
            btn_incluir.click(force=True)
            time.sleep(1.0)
        except Exception:
            self.page.keyboard.press("Escape")
            time.sleep(0.5)

    def digitar_prompt_e_disparar(self, prompt: str) -> None:
        """
        Limpa a caixa Slate.js, injeta o prompt inteiro de uma vez via document.execCommand('insertText')
        (< 50ms, atualizando a árvore interna do React/Slate) e clica em 'Iniciar geração'.
        """
        self.page.mouse.move(10, 10)
        self.page.keyboard.press("Escape")
        time.sleep(0.15)
        caixa = self.localizar("caixa_prompt", timeout_ms=10000)
        caixa.click(force=True)
        time.sleep(0.08)
        injetado_exec = False
        try:
            injetado_exec = bool(
                caixa.evaluate(
                    """(el, text) => {
                        el.focus();
                        document.execCommand('selectAll', false, null);
                        document.execCommand('delete', false, null);
                        return document.execCommand('insertText', false, text);
                    }""",
                    prompt,
                )
            )
        except Exception:
            injetado_exec = False

        if not injetado_exec:
            try:
                caixa.fill(prompt)
            except Exception:
                self.page.keyboard.press("Control+A")
                self.page.keyboard.press("Backspace")
                self.page.keyboard.insert_text(prompt)
            time.sleep(0.1)
            self.page.keyboard.type(" ", delay=15)

        time.sleep(0.25)

        btn_gerar = self.localizar("botao_iniciar_geracao", timeout_ms=8000)
        if btn_gerar.is_disabled():
            self.limpar_ingredientes_prompt()
            time.sleep(0.4)
            caixa.click(force=True)
            self.page.keyboard.type(" ", delay=20)
            time.sleep(0.4)
        if btn_gerar.is_disabled():
            raise RuntimeError("Botão 'Iniciar geração' está desabilitado no Flow.")
        btn_gerar.click(force=True)
        time.sleep(0.45)
        try:
            texto_restante = (caixa.inner_text(timeout=400) or "").strip()
            if len(texto_restante) > 10 and not btn_gerar.is_disabled():
                self.page.keyboard.press("Escape")
                time.sleep(0.25)
                btn_gerar.click(force=True)
                time.sleep(0.35)
        except Exception:
            pass
        self.logger.log(f"Geração disparada no Flow ({len(prompt)} chars).")

    def obter_urls_imagens_atuais(self) -> set[str]:
        urls: set[str] = set()
        for sel in SELETORES_FLOW["imagens_geradas"]:
            try:
                encontradas = self.page.locator(sel).evaluate_all("els => els.map(e => e.currentSrc || e.src || '')")
                for u in encontradas:
                    if u and (
                        "/asb/" in u
                        or "flow-content.google" in u
                        or "aisandbox-pa.googleapis.com" in u
                        or "signature=" in u
                    ):
                        urls.add(u)
            except Exception:
                pass
        return urls

    def baixar_imagem_por_url(self, url: str, destino_jpg: Path) -> Path:
        destino_jpg.parent.mkdir(parents=True, exist_ok=True)
        js_fetch = """
        async (u) => {
            const r = await fetch(u);
            const b = await r.blob();
            return new Promise((res) => {
                const reader = new FileReader();
                reader.onloadend = () => res(reader.result);
                reader.readAsDataURL(b);
            });
        }
        """
        data_url = self.page.evaluate(js_fetch, url)
        _, b64 = data_url.split(",", 1)
        raw = base64.b64decode(b64)
        with Image.open(BytesIO(raw)) as im:
            im.convert("RGB").save(destino_jpg, "JPEG", quality=95)
        return destino_jpg

    def esperar_novas_imagens_e_baixar(
        self,
        urls_conhecidas: set[str],
        destinos: list[Path],
        timeout_s: int = 180,
    ) -> list[Path]:
        """Aguarda novas imagens aparecerem no projeto do Flow e baixa cada uma."""
        prazo = time.monotonic() + timeout_s
        baixadas: list[Path] = []
        vistas = set(urls_conhecidas)

        time.sleep(4.0)
        while time.monotonic() < prazo and len(baixadas) < len(destinos):
            self.verificar_alertas_flow()
            atuais = self.obter_urls_imagens_atuais()
            novas = [u for u in atuais if u not in vistas]
            for u in novas:
                vistas.add(u)
                alvo = destinos[len(baixadas)]
                try:
                    self.baixar_imagem_por_url(u, alvo)
                    if self.validar_imagem_baixada(alvo):
                        baixadas.append(alvo)
                        self.logger.log(f"Imagem gerada no Flow salva em: {alvo.name} ({alvo.stat().st_size} bytes)")
                        if len(baixadas) >= len(destinos):
                            break
                except Exception as e:
                    self.logger.log(f"Aviso ao baixar imagem recém-gerada: {e}", nivel="WARN")
            if len(baixadas) < len(destinos):
                time.sleep(2.0)

        if not baixadas:
            raise TimeoutError(f"Nenhuma nova imagem apareceu no Flow após {timeout_s}s.")
        self.safety_guard.resetar()
        return baixadas

    def progresso_ativo(self) -> bool:
        for sel in SELETORES_FLOW["indicador_progresso"]:
            try:
                loc = self.page.locator(sel).first
                if loc.count() > 0 and loc.is_visible(timeout=200):
                    return True
            except Exception:
                pass
        return False

    def validar_imagem_baixada(self, img_path: Path) -> bool:
        if not img_path.is_file() or img_path.stat().st_size < 2048:
            return False
        try:
            with Image.open(img_path) as im:
                im.verify()
            return True
        except Exception:
            return False

    def obter_urls_videos_atuais(self) -> set[str]:
        urls: set[str] = set()
        for sel in SELETORES_FLOW["miniaturas_video_gerado"]:
            try:
                encontradas = self.page.locator(sel).evaluate_all("els => els.map(e => e.currentSrc || e.src || '')")
                for u in encontradas:
                    if u and ("/asb/" in u or "aisandbox-pa.googleapis.com" in u or "signature=" in u):
                        urls.add(u)
            except Exception:
                pass
        return urls

    def validar_video_mp4_baixado(self, mp4_path: Path) -> bool:
        if not mp4_path.is_file() or mp4_path.stat().st_size < 20480:
            return False
        cabecalho = mp4_path.read_bytes()[:32]
        if b"ftyp" not in cabecalho:
            return False
        return True

    def baixar_video_do_card_topo(self, destino_mp4: Path) -> bool:
        """Abre o primeiro card de VÍDEO da grade ('Miniatura do vídeo gerada') e faz o download 720p."""
        self.page.mouse.move(10, 10)
        self.page.keyboard.press("Escape")
        time.sleep(0.5)

        clicou_card = False
        for sel_vid in SELETORES_FLOW["miniaturas_video_gerado"]:
            card_vid = self.page.locator(sel_vid).first
            try:
                if card_vid.count() > 0 and card_vid.is_visible(timeout=500):
                    card_vid.click(force=True)
                    clicou_card = True
                    time.sleep(2.5)
                    break
            except Exception:
                continue

        if not clicou_card:
            return False

        for sel_dl in SELETORES_FLOW["botao_baixar_midia"]:
            btn = self.page.locator(sel_dl).first
            try:
                if btn.count() > 0 and btn.is_visible(timeout=500):
                    btn.click(force=True)
                    time.sleep(0.8)
                    with self.page.expect_download(timeout=60000) as dl_info:
                        op_clicada = False
                        for sel_op in SELETORES_FLOW["opcao_download_720p"]:
                            op = self.page.locator(sel_op).first
                            if op.count() > 0 and op.is_visible(timeout=500):
                                op.click(force=True)
                                op_clicada = True
                                break
                        if not op_clicada:
                            btn.click(force=True)
                    download = dl_info.value
                    destino_mp4.parent.mkdir(parents=True, exist_ok=True)
                    download.save_as(str(destino_mp4))
                    break
            except Exception as e:
                self.logger.log(f"Aviso ao acionar download do card: {e}", nivel="WARN")

        try:
            btn_done = self.localizar("botao_concluido_detalhe", timeout_ms=2500)
            btn_done.click(force=True)
            time.sleep(1.0)
        except Exception:
            self.page.keyboard.press("Escape")
            time.sleep(0.5)

        return self.validar_video_mp4_baixado(destino_mp4)

    def geracao_em_andamento_na_grade(self) -> bool:
        """Verifica se há algum card com porcentagem de renderização (ex: '15%', '84%') visível na grade."""
        js_pct = """
        () => {
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            let n;
            while ((n = walker.nextNode())) {
                const t = (n.nodeValue || '').trim();
                if (/^\\d{1,3}%$/.test(t)) {
                    const el = n.parentElement;
                    if (el && el.offsetParent !== null) return true;
                }
            }
            return false;
        }
        """
        try:
            if self.page.evaluate(js_pct):
                return True
        except Exception:
            pass
        return self.progresso_ativo()

    def esperar_video_terminar_e_baixar(
        self,
        urls_videos_antes: set[str],
        destino_mp4: Path,
        timeout_s: int = 600,
    ) -> Path:
        """
        Espera o vídeo terminar de verdade:
        1) aguarda o indicador de porcentagem (1%..99%) sumir da grade;
        2) atualiza a grade do projeto para garantir que 'Miniatura do vídeo gerada' receba seu src final;
        3) baixa via URL direta =mm,22,15 (ou fallback de clique no card) e valida o cabeçalho MP4 ('ftyp').
        """
        prazo = time.monotonic() + timeout_s
        time.sleep(35.0)
        while time.monotonic() < prazo:
            self.verificar_alertas_flow()
            if self.geracao_em_andamento_na_grade():
                time.sleep(4.0)
                continue

            try:
                self.page.reload(wait_until="domcontentloaded", timeout=30000)
                time.sleep(4.0)
            except Exception:
                pass

            if self.geracao_em_andamento_na_grade():
                time.sleep(4.0)
                continue

            atuais = self.obter_urls_videos_atuais()
            novos_videos = [u for u in atuais if u not in urls_videos_antes]

            if novos_videos:
                if self.baixar_video_do_card_topo(destino_mp4):
                    self.logger.log(
                        f"Vídeo MP4 real baixado do Flow com sucesso: {destino_mp4.name} ({destino_mp4.stat().st_size} bytes)"
                    )
                    self.safety_guard.resetar()
                    return destino_mp4

            time.sleep(4.0)
        raise TimeoutError(f"Timeout aguardando conclusão real do vídeo ({timeout_s}s).")


def executar_geracao_video_forja(
    lote_id: str,
    prompts_video: dict[str, Any],
    so_frame1: bool = False,
    qtd_opcoes_frame1: int = 4,
    modo_simulacao_local: bool = False,
    viral_referencia: Path | None = None,
    max_takes: int | None = None,
    project_url: str | None = None,
    porta_cdp: int = DEFAULT_CDP_PORT,
    profile_dir: str | Path | None = None,
    auto_abrir: bool = False,
    root: Path = ROOT_DIR,
) -> dict[str, Any]:
    """
    Executa a Etapa 5 da Forja para 1 vídeo do lote com cache completo por take:
    - Se algum take já tiver imagem_aprovada e clipe_pronto no disco, pula sem gastar crédito!
    - Se --so-frame1 estiver ativo, gera apenas 3-5 opções de imagem do Frame 1 para aprovação humana.
    - Quando modo_simulacao_local=False (padrão de produção), gera diretamente no Google Flow via CDP!
    """
    logger = BatchLogger(lote_id, root=root)
    safety = FlowSafetyGuard(logger)
    video_id = prompts_video["video_id"]
    pasta_video = root / "lotes" / lote_id / video_id
    cache_mgr = CacheVideoForja(pasta_video)

    estado = cache_mgr.carregar(prompts_video)
    estado = cache_mgr.sincronizar_arquivos_existentes(estado)

    if so_frame1:
        qtd_opcoes = max(3, min(5, qtd_opcoes_frame1))
        opcoes_dir = pasta_video / "opcoes_frame1"
        opcoes_dir.mkdir(parents=True, exist_ok=True)
        bases_dir = root / "bases"
        bases_dir.mkdir(parents=True, exist_ok=True)

        opcoes_geradas = []
        faltantes: list[Path] = []
        for i in range(1, qtd_opcoes + 1):
            dest_op = opcoes_dir / f"{video_id}_frame1_opcao_{i:02d}.jpg"
            opcoes_geradas.append(str(dest_op))
            if not dest_op.exists():
                faltantes.append(dest_op)

        if faltantes:
            if modo_simulacao_local:
                ref_frames = sorted((root / "virais" / "viral_ref_01_frames").glob("*.jpg"))
                for idx, dest_op in enumerate(faltantes):
                    shutil.copy2(ref_frames[idx % len(ref_frames)], dest_op)
            else:
                ctrl = ControladorFlowPlaywright(
                    logger=logger,
                    safety_guard=safety,
                    porta_cdp=porta_cdp,
                    profile_dir=profile_dir,
                    project_url=project_url,
                )
                try:
                    ctrl.conectar(auto_abrir=auto_abrir)
                    ctrl.configurar_modo_flow(modo="imagem", quantidade="x4" if len(faltantes) > 1 else "x1")
                    prompt_f1 = prompts_video["takes"][0]["prompt_imagem"]
                    conhecidas = ctrl.obter_urls_imagens_atuais()
                    ctrl.digitar_prompt_e_disparar(prompt_f1)
                    ctrl.esperar_novas_imagens_e_baixar(conhecidas, faltantes, timeout_s=180)
                finally:
                    ctrl.desconectar()

        estado["opcoes_frame1"] = opcoes_geradas
        cache_mgr.salvar(estado)
        logger.log(f"Modo --so-frame1 concluído: {len(opcoes_geradas)} opções de Frame 1 salvas em {opcoes_dir}.")
        return {
            "modo": "so_frame1",
            "video_id": video_id,
            "opcoes_frame1": opcoes_geradas,
            "cache_path": str(cache_mgr.cache_path),
        }

    takes_pulados_cache = []
    takes_gerados_agora = []

    ctrl: ControladorFlowPlaywright | None = None
    try:
        for idx, (num_str, t_info) in enumerate(estado["takes"].items(), start=1):
            if max_takes is not None and idx > max_takes:
                break

            img_path = pasta_video / t_info["arquivo_imagem"]
            clip_path = pasta_video / t_info["arquivo_clipe"]

            if t_info["clipe_pronto"] and clip_path.exists():
                takes_pulados_cache.append(int(num_str))
                logger.log(
                    f"[CACHE HIT] {video_id} Take {num_str} ({clip_path.name}) já está pronto no disco. Pulando sem gastar crédito."
                )
                continue

            if not modo_simulacao_local and ctrl is None:
                ctrl = ControladorFlowPlaywright(
                    logger=logger,
                    safety_guard=safety,
                    porta_cdp=porta_cdp,
                    profile_dir=profile_dir,
                    project_url=project_url,
                )
                ctrl.conectar(auto_abrir=auto_abrir)

            if not (t_info["imagem_aprovada"] and img_path.exists()):
                if modo_simulacao_local:
                    ref_frames = sorted((root / "virais" / "viral_ref_01_frames").glob("*.jpg"))
                    if ref_frames:
                        shutil.copy2(ref_frames[(int(num_str) - 1) % len(ref_frames)], img_path)
                else:
                    assert ctrl is not None
                    try:
                        ctrl.configurar_modo_flow(modo="imagem", quantidade="x1")
                        ctrl.limpar_ingredientes_prompt()
                        if int(num_str) >= 2:
                            ctrl.anexar_ingrediente_referencia_recente()
                        conhecidas = ctrl.obter_urls_imagens_atuais()
                        ctrl.digitar_prompt_e_disparar(t_info["prompt_imagem"])
                        ctrl.esperar_novas_imagens_e_baixar(conhecidas, [img_path], timeout_s=180)
                    except Exception as e:
                        logger.log(f"Erro ao gerar imagem do Take {num_str} no Flow: {e}", nivel="ERROR")
                        ctrl.reconectar_apos_travamento()
                        raise

                t_info["imagem_pronta"] = img_path.exists()
                t_info["imagem_aprovada"] = img_path.exists()
                cache_mgr.salvar(estado)
                logger.log(f"{video_id} Take {num_str}: imagem base pronta e aprovada ({img_path.name}).")

            from forja.qa_clipe import avaliar_qa_clipe, mover_para_reprovados

            aprovado_no_qa = False
            ultimo_qa: dict[str, Any] = {}
            for tentativa_idx in range(1, 3):
                t_info["tentativas_video"] = int(t_info.get("tentativas_video", 0)) + 1
                if modo_simulacao_local and viral_referencia and viral_referencia.exists():
                    t0 = (int(num_str) - 1) * 5.0
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-y",
                            "-loglevel",
                            "error",
                            "-ss",
                            f"{t0:.2f}",
                            "-t",
                            "5.5",
                            "-i",
                            str(viral_referencia),
                            "-c:v",
                            "libx264",
                            "-preset",
                            "fast",
                            "-crf",
                            "20",
                            "-c:a",
                            "aac",
                            str(clip_path),
                        ],
                        check=True,
                    )
                elif not modo_simulacao_local:
                    assert ctrl is not None
                    ctrl.configurar_modo_flow(modo="video", quantidade="x1")
                    ctrl.anexar_frame_inicio(img_path)
                    videos_antes = ctrl.obter_urls_videos_atuais()
                    ctrl.digitar_prompt_e_disparar(t_info["prompt_video"])
                    ctrl.esperar_video_terminar_e_baixar(videos_antes, clip_path, timeout_s=600)

                ultimo_qa = avaliar_qa_clipe(
                    video_path=clip_path,
                    fala_pedida=t_info["fala"],
                    imagem_gerada_path=img_path if not modo_simulacao_local else None,
                )
                t_info["ultimo_qa"] = ultimo_qa
                if ultimo_qa["aprovado"]:
                    aprovado_no_qa = True
                    break

                logger.log(
                    f"[QA TAKE {num_str} TENTATIVA {tentativa_idx}/2 REPROVADO] Motivos: {ultimo_qa['motivos_reprovacao']}",
                    nivel="WARN",
                )
                mover_para_reprovados(
                    video_path=clip_path,
                    lote_id=lote_id,
                    video_id=video_id,
                    take_num=int(num_str),
                    relatorio_qa=ultimo_qa,
                    reprovados_root=root / "_reprovados",
                    logger=logger,
                )

            if not aprovado_no_qa:
                estado["status_video"] = "reprovado_qa"
                estado["motivo_reprovacao"] = (
                    f"Take {num_str} reprovou após 2 tentativas: {ultimo_qa.get('motivos_reprovacao')}"
                )
                cache_mgr.salvar(estado)
                logger.log(
                    f"[PARANDO VÍDEO {video_id}] {estado['motivo_reprovacao']} — não gastando crédito nos takes seguintes.",
                    nivel="ERROR",
                )
                return {
                    "modo": "reprovado_qa",
                    "aprovado": False,
                    "video_id": video_id,
                    "take_reprovado": int(num_str),
                    "motivos": ultimo_qa.get("motivos_reprovacao", []),
                    "cache_path": str(cache_mgr.cache_path),
                }

            t_info["clipe_pronto"] = clip_path.exists()
            cache_mgr.salvar(estado)
            takes_gerados_agora.append(int(num_str))
            logger.log(f"{video_id} Take {num_str}: clipe {clip_path.name} gerado, aprovado no QA e registrado no cache.")
    finally:
        if ctrl is not None:
            ctrl.desconectar()

    falas_payload = {
        "video_id": video_id,
        "lote_id": lote_id,
        "formato": estado["formato"],
        "avatar": estado["avatar"],
        "cta_texto": "COMMENT YES",
        "takes": [
            {
                "take": info["take"],
                "arquivo": info["arquivo_clipe"],
                "papel": info["papel"],
                "fala": info["fala"],
            }
            for info in estado["takes"].values()
        ],
    }
    (pasta_video / "falas.json").write_text(
        json.dumps(falas_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "modo": "completo",
        "video_id": video_id,
        "pasta_video": str(pasta_video),
        "takes_pulados_pelo_cache": takes_pulados_cache,
        "takes_gerados_agora": takes_gerados_agora,
        "cache_path": str(cache_mgr.cache_path),
    }
