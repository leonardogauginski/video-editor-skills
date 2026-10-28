# Vídeo cozy para YouTube: como ajustar

Arquivos:
- `edl.json`: a lista de cortes. Cada trecho tem o arquivo de origem (pelo horário no nome, ex. `16.32.28`), o início e o fim em segundos e o motivo da escolha. As cenas aparecem na ordem do vídeo, com um dissolve suave entre uma cena e outra.
- `render.py`: o script que monta o vídeo com o ffmpeg (corte, orientação, estabilização, cor, som e exportação).

## Rodar de novo
1. Instale ffmpeg e Python 3 com numpy (`pip install numpy`).
2. Coloque os vídeos originais do WhatsApp em uma pasta.
3. Rode: `python3 render.py --src "caminho/da/pasta" --out cozy_youtube_final.mp4`

## Ajustes comuns
- **Encurtar ou alongar um trecho:** mude `in` e `out` no `edl.json`.
- **Tirar um trecho:** apague a linha dele. **Trocar a ordem:** mova a linha.
- **Som de um trecho mais alto ou mais baixo:** adicione `"gain_db": 3` (ou `-3`).
- **Vídeo deitado ou de lado:** `"orient": "raw"` ignora a rotação gravada pelo WhatsApp (vários arquivos vieram com a rotação errada). `"orient": "vertical"` usa o tratamento de vídeo vertical, com a imagem no centro e o fundo desfocado.
- **Tremido:** `"stab": true` estabiliza o trecho.
- **Recorte leve:** `"crop": [x, y, largura]` em fração do quadro, mantendo o 16:9.
- **Cor:** no topo do `render.py`, `COZY_GRADE` define o visual quente comum a todos os trechos. `WB_STRENGTH` e `EXPO_STRENGTH` controlam o quanto cada clipe é aproximado dos outros.

## Exportação
H.264 High em 1920×1080 a 30 fps, tags de cor Rec.709, áudio AAC 320 kb/s a 48 kHz, loudness por volta de -16 LUFS e `faststart` ligado.
