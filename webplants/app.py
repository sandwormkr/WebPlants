"""WebPlants - servidor principal.

Rode com:  python app.py
Depois abra http://localhost:8000
"""
import os
import re
import secrets
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import cv2
import uvicorn
import yaml
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from camera import Camera
from detector import DetectorPlantas, Resultado, desenhar
from notificador import FiltroAlerta, Telegram

BASE = Path(__file__).resolve().parent
PASTA_ALERTAS = BASE / "alertas"
PASTA_ALERTAS.mkdir(exist_ok=True)

load_dotenv(BASE / ".env")
CFG = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))

USUARIO = os.getenv("PAGINA_USUARIO", "horta")
SENHA = os.getenv("PAGINA_SENHA", "")
if not SENHA or SENHA == "troque-esta-senha":
    print("[app] AVISO: defina PAGINA_SENHA no arquivo .env antes de publicar a página!")


# ------------------------------------------------------------------ estado
class Estado:
    def __init__(self):
        self.trava = threading.Lock()
        self.resultado = Resultado()
        self.alertas = []  # [{"arquivo", "quando", "manchas"}]
        self.rodando = True


camera = Camera(**CFG["camera"])
detector = DetectorPlantas(CFG["deteccao"])
telegram = Telegram(os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID"))
filtro = FiltroAlerta(CFG["alerta"]["quadros_seguidos"], CFG["alerta"]["intervalo_minutos"])
estado = Estado()

PADRAO_ARQUIVO = re.compile(r"^alerta_(\d{8}_\d{6})_(\d+)\.jpg$")


def carregar_alertas_antigos():
    for arq in sorted(PASTA_ALERTAS.glob("alerta_*.jpg"), reverse=True)[: CFG["alerta"]["manter_ultimos"]]:
        m = PADRAO_ARQUIVO.match(arq.name)
        if m:
            quando = datetime.strptime(m.group(1), "%Y%m%d_%H%M%S")
            estado.alertas.append({"arquivo": arq.name,
                                   "quando": quando.strftime("%d/%m/%Y %H:%M:%S"),
                                   "manchas": int(m.group(2))})


def quadro_publico(quadro, resultado):
    """Quadro com as caixas desenhadas."""
    return desenhar(quadro, resultado)


# ------------------------------------------------------------------ análise
def loop_deteccao():
    periodo = 1.0 / CFG["deteccao"]["fps"]
    while estado.rodando:
        inicio = time.time()
        quadro = camera.ler()
        if quadro is None:
            time.sleep(0.2)
            continue

        resultado = detector.analisar(quadro)
        with estado.trava:
            estado.resultado = resultado

        if filtro.registrar(len(resultado.manchas) > 0):
            disparar_alerta(quadro, resultado)

        time.sleep(max(0.0, periodo - (time.time() - inicio)))


def disparar_alerta(quadro, resultado):
    agora = datetime.now()
    n = len(resultado.manchas)
    imagem = quadro_publico(quadro.copy(), resultado)
    nome = f"alerta_{agora:%Y%m%d_%H%M%S}_{n}.jpg"
    cv2.imwrite(str(PASTA_ALERTAS / nome), imagem)

    with estado.trava:
        estado.alertas.insert(0, {"arquivo": nome, "quando": agora.strftime("%d/%m/%Y %H:%M:%S"),
                                  "manchas": n})
        del estado.alertas[CFG["alerta"]["manter_ultimos"]:]

    legenda = (f"🌱 WebPlants: {n} mancha(s) preta(s) detectada(s)\n"
               f"🕒 {agora:%d/%m/%Y %H:%M:%S}\n"
               f"Veja a transmissão ao vivo para avaliar a folha.")
    print(f"[alerta] {n} mancha(s) - {nome}")
    telegram.enviar_foto(imagem, legenda)


# ------------------------------------------------------------------ web
@asynccontextmanager
async def ciclo_de_vida(_app):
    carregar_alertas_antigos()
    camera.iniciar()
    threading.Thread(target=loop_deteccao, daemon=True).start()
    yield
    estado.rodando = False
    camera.parar()


seguranca = HTTPBasic(realm="WebPlants")


def autenticar(cred: HTTPBasicCredentials = Depends(seguranca)):
    usuario_ok = secrets.compare_digest(cred.username.encode(), USUARIO.encode())
    senha_ok = secrets.compare_digest(cred.password.encode(), SENHA.encode())
    if not (usuario_ok and senha_ok and SENHA):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login inválido",
                            headers={"WWW-Authenticate": 'Basic realm="WebPlants"'})


app = FastAPI(title="WebPlants", lifespan=ciclo_de_vida, dependencies=[Depends(autenticar)],
              docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/", response_class=HTMLResponse)
def pagina():
    return (BASE / "templates" / "index.html").read_text(encoding="utf-8")


def gerar_mjpeg(modo: str):
    periodo = 1.0 / CFG["stream"]["fps"]
    qualidade = [cv2.IMWRITE_JPEG_QUALITY, CFG["stream"]["qualidade_jpeg"]]
    while estado.rodando:
        inicio = time.time()
        with estado.trava:
            resultado = estado.resultado
        if modo == "mascara":
            quadro = resultado.mascara
        else:
            quadro = camera.ler()
            if quadro is not None:
                quadro = quadro_publico(quadro, resultado)
        if quadro is not None:
            ok, jpg = cv2.imencode(".jpg", quadro, qualidade)
            if ok:
                yield (b"--quadro\r\nContent-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n")
        time.sleep(max(0.0, periodo - (time.time() - inicio)))


@app.get("/stream")
def stream(modo: str = "video"):
    return StreamingResponse(gerar_mjpeg(modo),
                             media_type="multipart/x-mixed-replace; boundary=quadro",
                             headers={"Cache-Control": "no-store"})


@app.get("/api/status")
def api_status():
    with estado.trava:
        r = estado.resultado
        alertas = list(estado.alertas)
    return {
        "camera": camera.conectada,
        "plantas": len(r.plantas),
        "manchas": len(r.manchas),
        "analise_ms": round(r.tempo_ms, 1),
        "brilho_folha": r.brilho_folha,
        "limiar": r.limiar,
        "seguidos": filtro.seguidos,
        "necessarios": filtro.necessarios,
        "proximo_alerta_em": filtro.em_espera if filtro.ultimo_alerta else 0,
        "telegram": telegram.configurado,
        "alertas": alertas,
    }


@app.get("/alertas/{nome}")
def foto_alerta(nome: str):
    if not PADRAO_ARQUIVO.match(nome):
        raise HTTPException(404)
    caminho = PASTA_ALERTAS / nome
    if not caminho.exists():
        raise HTTPException(404)
    return FileResponse(caminho, media_type="image/jpeg")


if __name__ == "__main__":
    print(f"WebPlants em http://localhost:{CFG['servidor']['porta']}  (usuário: {USUARIO})")
    uvicorn.run(app, host=CFG["servidor"]["host"], port=CFG["servidor"]["porta"], log_level="warning")
