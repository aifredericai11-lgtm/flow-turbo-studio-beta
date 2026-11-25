# 🚀 Flow Turbo Studio — v3.0 UltraBatch Edition (27 Workers/Conta + Pool Multi-Contas + Anti-Unusual Activity)

Motor autônomo de alta concorrência para dissecação de vídeos virais, clonagem estrutural e geração massiva em lote via **Google Flow (BELUGA / Nano Banana 2 + Veo 3.1 I2V Lite Low Priority — 0 créditos + Omni 1.2 Flash)** com **Blindagem Anti-Unusual Activity**, **27 Workers por Conta (escalável para +100 workers em multi-contas)**, **Juiz Visual GPU (`SFace/ResNet50 + MediaPipe`)** e montagem acelerada em 1 passe (`h264_nvenc` / `h264_videotoolbox`).

---

## 🔥 O Que Mudou na v3.0 UltraBatch (20+ / 27 Workers & Zero `UNUSUAL_ACTIVITY`)

1. **WebSocket CDP Assíncrono com 27 Workers por Conta (`forja/flow_rpc_direto.py`)**:
   - Semáforo ampliado para **`BoundedSemaphore(27)` por conta Chrome** (`:9225..:9236`), mantendo todos os slots de GPU do Google Flow ocupados em janela deslizante contínua.
   - Com 4 a 6 contas abertas no pool (`gerenciar_contas_flow.py`), opera **100+ takes simultâneos** sem gargalo de CPU ou lock serializado.
   - Todos os downloads de `.jpg`/`.mp4` (`flow-content.google`) rodam **100% fora do lock CDP**.

2. **UltraBatch 1-Token (`c.imagemLote` e `c.videoLote` em `extensao_flow_rpc/flow-core.js`)**:
   - O principal gatilho de `UNUSUAL_ACTIVITY` (`INCOMUM`) no Google Flow é pedir dezenas de tokens `grecaptcha.enterprise.execute` seguidos na mesma aba.
   - `gerar_imagens_lote_rpc` (`c.imagemLote` → RPC `ogiZ0b`) e `gerar_videos_lote_rpc` (`c.videoLote` → RPC `eb1hJf`) empacotam múltiplas imagens ou **3 a 9 cenas de vídeo em 1 única requisição Protobuf**, assinada por **1 único token reCAPTCHA Enterprise** (reduzindo o consumo de tokens em **70% a 85%**).

3. **Poller Central Coalescido (`_consultar_status_video_coalescido` via `jwpduf`)**:
   - Em vez de 27 threads fazendo polling individual no endpoint `as29s` (`GetMedia`), **1 única requisição `jwpduf` (`BatchCheckAsyncVideoGenerationStatus`) a cada `2.4s`** consulta o status de todos os 27 vídeos simultâneos da conta e notifica todas as threads em memória (`threading.Condition`).
   - Descarta automaticamente `workflowId`s intermediários para jamais spammar `as29s`.

4. **Pool Multi-Contas (`:9225` a `:9236`) + Ponte Automática de `mediaId` (`_garantir_ref_na_conta`)**:
   - Gerenciador integrado (`GERENCIAR_CONTAS_FLOW.bat` / `python gerenciar_contas_flow.py`) para abrir e monitorar até 12 instâncias isoladas do Chrome (`FlowProfile`, `FlowProfile_02`..`12`).
   - Roteador inteligente `escolher_conta_flow(exige_omni=...)`: distribui lotes gratuitos (`veo_3_1_i2v_lite_low_priority`) em **Round-Robin** entre todas as contas saudáveis e direciona pilotos Omni Flash para as contas com saldo de créditos.
   - **Ponte Automática de `mediaId`**: se um `frame_1` ou matriz foi subido/gerado na Conta 1 (`:9225`) e o worker cair na Conta 2 (`:9226`), `_garantir_ref_na_conta` re-sobe e cacheia automaticamente o arquivo original na Conta 2 sem quebrar a execução.

5. **Purga Cirúrgica Anti-Tráfego + Failover Instantâneo (`recarregar_aba_flow_anti_traffic`)**:
   - Se qualquer conta receber `INCOMUM` (`UNUSUAL_ACTIVITY` / `TOO_MUCH_TRAFFIC`), ela entra em **cooldown de 30s** e o worker faz **failover imediato (0.5s)** para outra conta saudável do pool.
   - Em background, a conta afetada abre uma aba limpa, fecha a aba marcada e executa `Storage.clearDataForOrigin` via CDP (limpando `local_storage, session_storage, indexeddb, cache_storage, service_workers` de `flow.google.com`, `google.com`, `gstatic.com` e `labs.google` **sem apagar os cookies de login**), re-injetando `trap-main.js` + `flow-core.js` via `Page.addScriptToEvaluateOnNewDocument` com score reCAPTCHA zerado.

6. **Motor UltraBatch 500 Vídeos/Hora (`forja/motor_500h_ultrabatch.py`) + Juiz Visual GPU (`forja/juiz_visual_gpu.py`)**:
   - **Tesoura Fonética Zero-Encode**: calcula `(trim_start, duracao_final_s)` via Faster-Whisper GPU sem re-encodar clipes intermediários.
   - **Fusão NVENC em 1 Único Passe (`montar_video_1_passe_nvenc`)**: corta, concatena, aplica legenda `.ass` / botão CTA e normaliza áudio em `~0.55s` por vídeo.
   - **Juiz Visual GPU (`forja/juiz_visual_gpu.py`)**: auditoria anti-3º braço, anti-troca de apresentadora (`SFace`/`ResNet50` + `MediaPipe`) e detector OpenCV determinístico anti-barra de UI falsa ou texto queimado no rodapé.

---

## 🛠️ Pré-Requisitos (Windows & MacBook)

1. **Python 3.10 ou 3.11+** instalado.
2. **FFmpeg** instalado no sistema (`PATH` — no Mac: `brew install ffmpeg`).
3. **Google Chrome** instalado.
4. 1 ou mais contas logadas no **Google Flow** (`https://flow.google.com/`).

---

## ⚡ Como Iniciar no Windows (RTX NVENC) ou MacBook (Apple Silicon M1–M5 VideoToolbox)

O motor detecta automaticamente o sistema operacional (`forja/hw_accel.py`):
- **MacBook (M1 / M2 / M3 / M4 / M5 & Intel):** usa aceleração de hardware nativa **`h264_videotoolbox`** + `faster-whisper` (`int8` multi-core) + `caffeinate -dimsu` anti-sono + perfis isolados em `~/Library/Application Support/Google/Chrome/FlowProfile*`.
- **Windows (NVIDIA RTX):** usa **`h264_nvenc`** + `faster-whisper` (`CUDA float16`) + perfis isolados em `%LOCALAPPDATA%\Google\Chrome\FlowProfile*`.

### Passo 1 — Instalar Dependências
- **Windows:** dê dois cliques em `1_INSTALAR_DEPENDENCIAS.bat` (ou `pip install -r requirements.txt`)
- **MacBook:** dê dois cliques em **`1_INSTALAR_DEPENDENCIAS_MAC.command`** (ou no Terminal: `chmod +x *.command && ./1_INSTALAR_DEPENDENCIAS_MAC.command`)

### Passo 2 — Abrir 1 Conta (`:9225`) ou Pool Multi-Contas (`:9225..:9236`)
- **Para 1 conta principal (`:9225`):**
  - Windows: `2_ABRIR_CHROME_FLOW.bat` (ou `python abrir_chrome_flow.py`)
  - MacBook: **`2_ABRIR_CHROME_FLOW_MAC.command`** (ou `python3 abrir_chrome_flow.py`)
- **Para Pool Multi-Contas (`:9225`, `:9226`, `:9227`, ...):**
  - Windows: dê dois cliques em **`GERENCIAR_CONTAS_FLOW.bat`**
  - MacBook: dê dois cliques em **`GERENCIAR_CONTAS_FLOW_MAC.command`**
  - Terminal (Windows / MacBook):
    ```bash
    # Abrir slots 1 e 2 (:9225 e :9226) em janelas isoladas para login:
    python3 gerenciar_contas_flow.py --abrir 1 2

    # Verificar status, e-mail, projeto e saldo de créditos de todas as contas:
    python3 gerenciar_contas_flow.py --status

    # Reabrir automaticamente todas as contas salvas no pool:
    python3 gerenciar_contas_flow.py --subir-todas
    ```
  - Em cada janela aberta, faça login numa conta **Google AI Ultra** e deixe aberta dentro de um projeto (`https://flow.google.com/project/<ID>`).

### Passo 3 — Usar o Studio Web ou a API Python UltraBatch
- **Interface Web:**
  - Windows: `3_INICIAR_STUDIO_BETA.bat` (`http://localhost:8788`)
  - MacBook: **`3_INICIAR_STUDIO_BETA_MAC.command`** *(já sobe com `caffeinate -dimsu` para o Mac não dormir nos lotes!)*
- **Exemplo em Python (UltraBatch 1-Token + Multi-Contas Automático):**
  ```python
  from forja.flow_rpc_direto import (
      gerar_imagem_rpc,
      gerar_videos_lote_rpc,
      aguardar_midia_rpc,
  )

  # 1. Gera o start frame no BELUGA (roteado automaticamente para uma conta saudável do pool):
  r_img = gerar_imagem_rpc("Raw iPhone 0.5x vertical 9:16 photo of a nurse in a kitchen", modelo="BELUGA")
  w_img = aguardar_midia_rpc(r_img, tipo="image", destino_arquivo="./frame_1.jpg")
  f1_id = w_img["mediaId"]

  # 2. Dispara as 3 cenas de vídeo em 1 ÚNICO RPC eb1hJf com 1 ÚNICO token reCAPTCHA Enterprise:
  r_lote = gerar_videos_lote_rpc([
      {"prompt": "Scene 1 action and dialogue...", "img": f1_id},
      {"prompt": "Scene 2 action and dialogue...", "img": f1_id},
      {"prompt": "Scene 3 action and dialogue...", "img": f1_id},
  ], modelo="veo_3_1_i2v_lite_low_priority")

  # 3. Coleta os 3 MP4 usando o Poller Central Coalescido (jwpduf):
  for idx, item in enumerate(r_lote["items"], start=1):
      aguardar_midia_rpc(item, tipo="video", destino_arquivo=f"./cena_{idx}.mp4")
  ```

---

## 📂 Estrutura Principal do Repositório

```text
├── 1_INSTALAR_DEPENDENCIAS.bat        # Instala bibliotecas Python necessárias
├── 2_ABRIR_CHROME_FLOW.bat            # Abre Chrome principal na porta :9225 com a extensão
├── 3_INICIAR_STUDIO_BETA.bat          # Inicia o Studio Web em http://localhost:8788
├── GERENCIAR_CONTAS_FLOW.bat          # Painel interativo do Pool Multi-Contas (:9225..:9236)
├── gerenciar_contas_flow.py           # CLI/Gerenciador do Pool Multi-Contas Google Flow
├── abrir_chrome_flow.py               # Inicializador multiplataforma (MacBook / Windows / Linux)
├── studio_web.py                      # Servidor Web + Pipeline Completo (Modo Turbo + GPU)
├── motor_turbo_cdp.py                 # Cliente CDP direto v1 (legado)
├── motor_turbo_cdp_v2.py              # Wrapper v3.0 UltraBatch & Multi-Contas compatível com v2
├── extensao_flow_rpc/                 # Extensão Chrome Manifest V3 (world: MAIN)
│   ├── manifest.json                  # Manifest V3 para flow.google.com e labs.google
│   ├── trap-main.js                   # Armadilha document_start que preserva o execute original do reCAPTCHA
│   └── flow-core.js                   # Core v0.5.1-ultrabatch (imagemLote, videoLote, jwpduf, WebLock)
└── forja/
    ├── flow_rpc_direto.py             # Motor Multi-Contas (27 workers/conta + ponte mediaId + poller jwpduf)
    ├── motor_500h_ultrabatch.py       # Esteira 500 vídeos/h (Janela deslizante 27 slots + NVENC 1-passe)
    ├── juiz_visual_gpu.py             # Juiz Visual GPU (SFace/ResNet50 + MediaPipe anti-defeito e unicidade)
    ├── qa_clipe.py                    # Tesoura Fonética 3 Passes (Faster-Whisper GPU) + Revisor 3 Camadas
    ├── compilador_realismo_zerum.py   # Compilador óptico de realismo smartphone 0.5x/24mm
    └── diretor_realismo_pastel_euojeff.py # Diretor de Realismo Pastel + JSON de Física Biomecânica Causal
```
