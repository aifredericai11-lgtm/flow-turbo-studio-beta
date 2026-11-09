# 🚀 Flow Turbo Studio — Beta Tester Edition (Windows & MacBook)

Motor autônomo de alta velocidade para dissecação de vídeos virais, clonagem estrutural com variação inteligente e geração massiva em lote via **Google Flow (Beluga Image + Veo 3.1 I2V Lite — 0 créditos)** com **Revisor de 3 Juízes** e montagem acelerada por GPU (`h264_nvenc` / `h264_videotoolbox`).

---

## ✨ Principais Recursos desta Versão Beta

1. **Motor WebSocket CDP Direto (`forja/flow_rpc_direto.py` + `motor_turbo_cdp_v2.py`)**:
   - Dispara até **14 chamadas RPC simultâneas na mesma aba do Google Flow** via WebSocket assíncrono (`~0.25s` para 10 disparos concorrentes).
   - Usa o modelo `veo_3_1_i2v_lite_low_priority` (**0 créditos consumidos por vídeo**).
   - **Modo Turbo Fixo**: Gera o Quadro 1 e dispara Cena 1, Cena 2 e Cena 3 **100% em paralelo**.
   - **Suporte Nativo a MacBook (macOS Apple Silicon / Intel) e Windows**:
     - Web Lock permanente (`navigator.locks.request('flow-turbo-macbook-keepawake', ...)`) em `extensao_flow_rpc/flow-core.js` que impede o **App Nap do macOS** de congelar os XHRs `batchexecute` e o token `reCAPTCHA Enterprise` quando o Chrome está em 2º plano.
     - Download autenticado dentro do próprio navegador (`c.baixarBase64(url)` via `fetch(url, { credentials: 'include' })`) + contexto SSL tolerante no Python do macOS.
     - Exposição dupla `window.__zerumCandidateCoreV1` + `window.__FLOW` (`generateImage`, `generateVideo`, `checkStatus`, `uploadImage`).

2. **Revisor Implacável de 3 Camadas (`forja/qa_clipe.py`)**:
   - **Juiz 1 (Pré-Animação)**: Audita identidade do personagem, cor da roupa/acessórios, mãos e permanência dos objetos de cena antes de animar.
   - **Tesoura Fonética de 3 Passes (`faster-whisper`)**: Corta silêncio inicial/final, alucinação de voz no fim do clipe e congelamentos.
   - **Juiz 3 (Pós-Animação Intra-Clipe)**: Inspeciona `15%`, `55%` e `88%` da linha do tempo do `.mp4` gerado e regrava automaticamente caso algum objeto suma no meio do clipe, a roupa mude, surja texto indesejado ou haja bug de mão/flash.

3. **Edição Dinâmica & Pós-Produção GPU (`edicao/` + `studio_web.py`)**:
   - **Zero Transições de Flash**: Corte seco dinâmico com **Punch-In `1.11x`** na Cena 2.
   - **Legendas Karaokê (`Poppins Bold`)** palavra por palavra sincronizadas via Whisper.
   - **Botão Pop-Up CTA Animado (`COMMENT YES` / customizável)** no terço final do vídeo.

---

## 🛠️ Pré-Requisitos (Windows & MacBook)

1. **Python 3.10 ou 3.11+** instalado.
2. **FFmpeg** instalado no sistema (disponível no `PATH` — no Mac: `brew install ffmpeg`).
3. **Google Chrome** instalado.
4. Conta logada no **Google Flow** (`https://flow.google.com/`).

---

## ⚡ Como Iniciar em 3 Passos (Windows ou MacBook)

### Passo 1 — Instalar Dependências
- **Windows:** Dê dois cliques em **`1_INSTALAR_DEPENDENCIAS.bat`** (ou `pip install -r requirements.txt`).
- **MacBook (M1/M2/M3/M4 ou Intel):**
  ```bash
  pip3 install -r requirements.txt
  ```

### Passo 2 — Abrir o Chrome com a Extensão Flow RPC (Porta `9225`)
- **Windows:** Dê dois cliques em **`2_ABRIR_CHROME_FLOW.bat`** (ou `python abrir_chrome_flow.py`).
- **MacBook:**
  ```bash
  python3 abrir_chrome_flow.py
  ```
- O Google Chrome abrirá na porta `9225` já com a extensão `./extensao_flow_rpc` carregada, `--user-data-dir` isolado (`./chrome_flow_profile`) e flags anti-App Nap ativas.
- Faça login na sua conta Google em **`https://flow.google.com/`** e **abra ou crie qualquer projeto** (deixe a aba aberta em `https://flow.google.com/project/<ID>`).

### Passo 3 — Iniciar o Studio Web ou Usar a Camada RPC Direto
- **Windows:** Dê dois cliques em **`3_INICIAR_STUDIO_BETA.bat`**.
- **MacBook / Terminal:**
  ```bash
  python3 studio_web.py
  ```
- O painel abrirá em **`http://localhost:8788`**.
- Para usar apenas a camada de requisições ao Flow no seu próprio script Python:
  ```python
  from motor_turbo_cdp_v2 import FlowTurboCDP

  flow = FlowTurboCDP(cdp_port=9225)
  # 1. Gera imagem BELUGA (0 créditos) e baixa autenticado:
  mid = flow.gerar_start_frame("Portrait of a doctor in a bright clinic, 9:16", "./frame1.jpg")
  # 2. Dispara vídeo Veo 3.1 Lite Low Priority (0 créditos) com startFrame:
  uuids = flow.disparar_video_veo31("She speaks naturally to the camera", mid)
  ```

---

## 📂 Estrutura do Repositório

```text
├── 1_INSTALAR_DEPENDENCIAS.bat   # Instala bibliotecas Python necessárias (Windows)
├── 2_ABRIR_CHROME_FLOW.bat       # Abre Chrome na porta 9225 com a extensão (Windows)
├── abrir_chrome_flow.py          # Abre Chrome na porta 9225 em MacBook / Windows / Linux
├── 3_INICIAR_STUDIO_BETA.bat     # Inicia a interface web em http://localhost:8788
├── studio_web.py                 # Servidor Web + Pipeline Completo (Modo Turbo + GPU)
├── motor_turbo_cdp.py            # Cliente CDP direto v1 (window.__FLOW + __zerumCandidateCoreV1)
├── motor_turbo_cdp_v2.py         # Cliente CDP direto v2 com anti-Unusual Activity e auto-reload
├── extensao_flow_rpc/            # Extensão Chrome Manifest V3 (world: MAIN) p/ flow.google.com
│   ├── manifest.json             # Manifest limpo sem referências órfãs
│   ├── trap-main.js              # Hook de captura da siteKey reCAPTCHA Enterprise
│   └── flow-core.js              # Motor RPC batchexecute + WebLock Anti-App Nap + window.__FLOW
├── forja/
│   ├── flow_rpc_direto.py        # Cliente WebSocket CDP paralelo (14 slots simultâneos)
│   └── qa_clipe.py               # Revisor de 3 Camadas (Juiz 1 + Tesoura 3 Passes + Juiz 3)
└── prontos/                      # Pasta onde os vídeos finais verificados são entregues
```
