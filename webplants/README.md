# 🌱 WebPlants

Transmissão ao vivo da horta do colégio com detecção de **manchas pretas** nas folhas
e alerta pelo **Telegram**.

- 🟩 Caixa verde: cada planta (detectada pela cor verde)
- 🟥 Caixa vermelha: mancha preta **dentro** da folha (a terra escura é ignorada)
- 📲 Alerta com foto no Telegram, com filtro anti-spam
- 🌍 Página acessível de qualquer lugar pelo Tailscale Funnel, com senha

---

## 1. Instalar

Requisitos: **Python 3.11 ou 3.12** ([python.org](https://www.python.org/downloads/);
no Windows, marque *"Add python.exe to PATH"*) e a webcam Logitech C920e ligada na USB.

**Windows 11 (notebook do colégio):** dê dois cliques em `iniciar.bat`.
Na primeira vez ele cria o ambiente, instala tudo (alguns minutos) e abre o `.env`
no Bloco de Notas para você preencher.

**Linux (Arch):**
```bash
./iniciar.sh
```
> Se a câmera não abrir no Arch, adicione seu usuário ao grupo `video`:
> `sudo usermod -aG video $USER` (depois saia e entre na sessão).

A instalação ocupa cerca de **200 MB** (só OpenCV, NumPy e o servidor web).

## 2. Configurar o Telegram

1. No Telegram, abra o **@BotFather**, mande `/newbot` e siga os passos.
   Ele te dá um **token**. Cole no `.env` em `TELEGRAM_TOKEN=`.
2. Abra o seu bot (link que o BotFather mostra) com a conta **@sandwormkr** e mande `/start`.
3. Rode:
   ```bash
   # Windows
   .venv\Scripts\python.exe pegar_chat_id.py
   # Linux
   .venv/bin/python pegar_chat_id.py
   ```
   Ele mostra o `chat_id` e envia uma mensagem de teste. Cole o número em `TELEGRAM_CHAT_ID=`.
4. Troque também `PAGINA_SENHA` no `.env`.

> ⚠️ Nunca compartilhe o `.env`: o token dá controle total do bot.

## 3. Rodar

Rode `iniciar.bat` (ou `./iniciar.sh`) e abra **http://localhost:8000**.
O navegador pede usuário e senha (os do `.env`).

## 4. Acessar de qualquer lugar (Tailscale Funnel)

Com o Tailscale instalado e logado no notebook:

```bash
tailscale funnel --bg 8000
```

O comando mostra um endereço como `https://notebook.tail1234.ts.net`. Esse link
funciona em **qualquer navegador**, sem Tailscale. Para desligar:

```bash
tailscale funnel --bg 8000 off
```

> Na primeira vez, o Tailscale pode pedir para habilitar o Funnel no painel de
> administração (ele mostra o link). É preciso ativar HTTPS e o atributo `funnel`
> na política da tailnet.

## 5. Calibrar na horta

Na página, clique em **Calibração**. Você verá:

| Cor | Significado |
|---|---|
| Verde | o que foi reconhecido como folha |
| Amarelo | região escura descartada: pouca folha em volta |
| Rosa | região escura descartada: pequena ou grande demais |
| Vermelho | mancha aceita |

No topo aparece `folha V~150  preto V<=82`: o brilho médio da folha e o brilho máximo
que conta como "preto" naquele momento. O limite acompanha a luz automaticamente.

Ajuste no `config.yaml` e reinicie:

| Problema | O que mudar |
|---|---|
| Folhas não ficam verdes na calibração | diminua `verde_s_min` / `verde_v_min`, ou aumente a faixa `verde_h_min`–`verde_h_max` |
| Mancha não aparece em nenhuma cor | aumente `mancha_fator_relativo` (ex.: 0.7) |
| Mancha aparece em amarelo | diminua `mancha_cercada_min` (ex.: 0.3) |
| Mancha aparece em rosa | ajuste `mancha_area_min` / `mancha_area_max` |
| Sombra virando mancha | diminua `mancha_fator_relativo` (ex.: 0.45) ou aumente `mancha_cercada_min` |
| Alertas demais | aumente `quadros_seguidos` ou `intervalo_minutos` |

**Dicas de posição:** câmera de cima ou levemente inclinada, a **30–60 cm** das plantas,
sem sol batendo direto na lente. A C920e não enxerga no escuro.

## Estrutura

```
webplants/
├── app.py              servidor (página, /stream MJPEG, /api/status, login)
├── camera.py           captura da C920e (DirectShow no Windows, V4L2 no Linux)
├── detector.py         plantas + manchas (OpenCV)
├── notificador.py      Telegram + filtro anti-spam
├── config.yaml         todos os ajustes
├── .env.example        modelo do .env (token, chat_id, senha)
├── pegar_chat_id.py    descobre o chat_id e testa o bot
├── iniciar.bat / .sh   instalação e início com um clique
├── templates/index.html
└── alertas/            fotos dos alertas (criada automaticamente)
```

## Próximos passos (Fase 2)

Detectar manchas com IA: tirar fotos reais da horta, rotular as manchas
(ex.: no Roboflow ou Label Studio), treinar um YOLO11 próprio e exportá-lo para
ONNX, que o próprio OpenCV consegue rodar sem instalar o PyTorch.
