# 🔒 LEI DE ISOLAMENTO TOTAL 100% ANTI-PDQF & MOTOR REACT PYONG V2 DIRECT RESPONSE

## 1. Por Que Lotes Com Fundo/Frame Compartilhado Dão 0 Views e Zeram o Trust Score no Facebook (Meta Andromeda TMK + PDQF)
O sistema de deduplicação de vídeo da Meta (**PDQF** para frames espaciais + **TMK** para janelas temporais) flagra qualquer lote como `UNORIGINAL / DUPLICATE CREATIVE` quando:
1. **Máscara cinza apenas na cabeça (`head-mask inpaint`)**: Se apenas a região da cabeça (`25%` do quadro) muda e os outros `75%` dos pixels (cozinha, prateleiras, bancada, roupa, braços, pés ou paciente) permanecem idênticos ao frame original em todos os 50–100 vídeos (`diff L1 < 18`), todos os vídeos colidem no mesmo hash espacial `PDQF`.
2. **Cache de quadros secundários compartilhados entre vídeos (`SHARED_TABLE_DIR` / `table_slot`)**: Reutilizar 8 fotos POV de mesa nas Cenas 2, 3 e 4 ao longo de 100 vídeos faz 12 vídeos diferentes terem exatamente o mesmo hash visual dos `5s` aos `22s`.
3. **Mesmo frame inicial repetido em 3 cenas seguidas dentro do mesmo vídeo (`[f1, f1, f1, f2]`)**: Faz o vídeo saltar de volta exatamente para o frame `0.0s` nos cortes de `5s` e `12s`, gerando repetição de hash interno.
4. **Barras pretas de `3px` do `BELUGA` (`768x1376 -> 0.5581` vs `9:16 -> 0.5625`)**: Faz o checklist de qualidade do Facebook Reels reprovar o item *"Nenhuma borda detectada"*.

---

## 2. As 5 Travas Obrigatórias do Firewall Anti-PDQF (`forja/auditor_isolamento_pdqf.py`)
1. **100% do Quadro Isolado por Vídeo (`refs=[]` na Cena 1 — Proibido máscara só na cabeça)**:
   - Cada vídeo `V001..VN` gera **pessoa + roupa + cozinha/ambiente + bancada + iluminação + micro-geometria 100% únicos** (`L1 diff >= 26.0` e `dHash >= 16/64` contra todos os outros vídeos do lote).
2. **Zero Cache Compartilhado Entre Vídeos (`SHARED_TABLE_DIR` Banido)**:
   - Cada vídeo gera seus próprios quadros dentro da sua pasta isolada `Vxxx/`.
3. **Frames Iniciais Distintos por Cena (`L1 diff interno >= 14.0`)**:
   - Proibido `[f1, f1, f1, f2]`. Cada cena tem sua própria foto/variação de enquadramento e ação física para nunca saltar de volta ao mesmo frame inicial.
4. **Zero Bordas Pretas (`0px`)**:
   - `_normalizar_imagem_9x16_sem_bordas()` em `forja/flow_rpc_direto.py` + `crop=iw-16:ih-28:8:14,scale=720:1280:flags=lanczos` em todos os pipelines FFmpeg NVENC.
5. **Revisor Whisper Pós-Corte Obrigatório**:
   - Todo clipe cortado (`out_trim.mp4`) é re-auditado pelo Faster-Whisper exigindo a **última palavra real da frase** (sem truncamento por `max_len`).

---

## 3. Arquitetura React Tela Dividida Estilo Pyong V2 + Direct Response (`lotes/forjar_react_pyong_50_avatares.py`)
- **Realismo `Fusão Suprema V2` (3 parágrafos, `refs=[]` no `F1`) + `AD06` JSON (11 blocos)**:
  - Expressão durante a receita 100% calma, séria, focada e boca fechada olhando para a tela do celular (**zero olhos esbugalhados**, **zero sorriso forçado de IA**, **zero fala durante a receita**).
- **Crop 1:1 Sem Achatar (`crop=720:564` via detector YCrCb da testa)** + degradê suave de `44px` na divisória (`y=716..760`).
- **Banner Direct Response Agressivo (`0.0s–3.0s`)**:
  - Zero aspas (`“ "`) e zero rótulo de jornal (`TEMA: EXPLICAÇÃO`); usa **Blind Hook + Âncora de Vigia** com grifo exclusivo nas 2–3 palavras de dor/choque (alternando Amarelo Alerta `#FFE014` e Vermelho Sangue `#D91414`) sobre o frame mais tenso/visual da receita.
- **Receita Original 100% Inteira + Loop de Reação Sem Reverso + Final Tela Cheia (`720x1280`) com `FOLLOW FOR MORE ↓`**.
