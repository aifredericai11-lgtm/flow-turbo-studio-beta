# 🚀 Flow Turbo Studio — Beta Tester Edition

Motor autônomo de alta velocidade para dissecação de vídeos virais, clonagem estrutural com variação inteligente e geração massiva em lote via **Google Flow (Beluga Image + Veo 3.1 I2V Lite — 0 créditos)** com **Revisor de 3 Juízes** e montagem acelerada por GPU (`h264_nvenc`).

---

## ✨ Principais Recursos desta Versão Beta

1. **Motor WebSocket CDP Direto (`forja/flow_rpc_direto.py`)**:
   - Dispara até **14 chamadas RPC simultâneas na mesma aba do Google Flow** via WebSocket assíncrono (`~0.25s` para 10 disparos concorrentes).
   - Usa o modelo `veo_3_1_i2v_lite_low_priority` (**0 créditos consumidos por vídeo**).
   - **Modo Turbo Fixo**: Gera o Quadro 1 e dispara Cena 1, Cena 2 e Cena 3 **100% em paralelo**.

2. **Revisor Implacável de 3 Camadas (`forja/qa_clipe.py`)**:
   - **Juiz 1 (Pré-Animação)**: Audita identidade do personagem, cor da roupa/acessórios, mãos e permanência dos objetos de cena antes de animar.
   - **Tesoura Fonética de 3 Passes (`faster-whisper`)**: Corta silêncio inicial/final, alucinação de voz no fim do clipe e congelamentos.
   - **Juiz 3 (Pós-Animação Intra-Clipe)**: Inspeciona `15%`, `55%` e `88%` da linha do tempo do `.mp4` gerado e regrava automaticamente caso algum objeto suma no meio do clipe, a roupa mude, surja texto indesejado ou haja bug de mão/flash.

3. **Edição Dinâmica & Pós-Produção GPU (`edicao/` + `studio_web.py`)**:
   - **Zero Transições de Flash**: Corte seco dinâmico com **Punch-In `1.11x`** na Cena 2.
   - **Legendas Karaokê (`Poppins Bold`)** palavra por palavra sincronizadas via Whisper.
   - **Botão Pop-Up CTA Animado (`COMMENT YES` / customizável)** no terço final do vídeo.

---

## 🛠️ Pré-Requisitos no Windows

1. **Python 3.10 ou 3.11** instalado (marcando a opção *"Add Python to PATH"*).
2. **FFmpeg** instalado no sistema (disponível no `PATH` — teste com `ffmpeg -version` no terminal).
3. **Google Chrome** instalado.
4. Conta logada no **Google Labs Flow** (`https://labs.google/fx/tools/flow`).

---

## ⚡ Como Iniciar em 3 Passos (1 Clique)

### Passo 1 — Instalar Dependências
Dê dois cliques em **`1_INSTALAR_DEPENDENCIAS.bat`** (necessário apenas na primeira vez).

### Passo 2 — Abrir o Chrome com a Extensão Flow RPC
Dê dois cliques em **`2_ABRIR_CHROME_FLOW.bat`**.
- O Google Chrome abrirá na porta `9225` já com a extensão `./extensao_flow_rpc` carregada automaticamente.
- Faça login na sua conta Google no [Google Flow](https://labs.google/fx/tools/flow) e **abra ou crie qualquer projeto** (deixe a aba do projeto aberta).

### Passo 3 — Iniciar o Studio Web
Dê dois cliques em **`3_INICIAR_STUDIO_BETA.bat`**.
- O painel abrirá automaticamente em **`http://localhost:8788`**.
- Suba um vídeo viral de referência na aba **Diretor IA** ou escolha a quantidade de variações, cores de roupa/cenário e clique em **Disparar Lote**.
- Todos os vídeos aprovados pelos 3 Juízes são salvos prontos em **`./prontos/`**.

---

## 📂 Estrutura do Repositório

```text
├── 1_INSTALAR_DEPENDENCIAS.bat   # Instala bibliotecas Python necessárias
├── 2_ABRIR_CHROME_FLOW.bat       # Abre Chrome na porta 9225 com a extensão carregada
├── 3_INICIAR_STUDIO_BETA.bat     # Inicia a interface web em http://localhost:8788
├── studio_web.py                 # Servidor Web + Pipeline Completo (Modo Turbo + NVENC)
├── extensao_flow_rpc/            # Extensão Chrome que expõe __izarFlowCore no Google Flow
├── forja/
│   ├── flow_rpc_direto.py        # Cliente WebSocket CDP paralelo (14 slots simultâneos)
│   ├── qa_clipe.py               # Revisor de 3 Camadas (Juiz 1 + Tesoura 3 Passes + Juiz 3)
│   └── extrator_zerum15.py       # Extrator automático de vídeos virais de referência
├── edicao/
│   ├── subtitles.py              # Gerador de legendas .ASS Karaokê + Pop-Up CTA
│   └── render_gpu.py             # Montagem final acelerada por GPU (h264_nvenc)
├── fonts/                        # Fontes Poppins Bold/Black, Montserrat e Anton
└── prontos/                      # Pasta onde os vídeos finais verificados são entregues
```
