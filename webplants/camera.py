"""Captura da webcam em uma thread própria, com troca de câmera em tempo real.

Sempre guarda apenas o quadro mais recente, assim o stream e a detecção
nunca ficam atrasados esperando um ao outro.
"""
import platform
import threading
import time
from pathlib import Path

import cv2

SISTEMA = platform.system()


def _abrir(indice, largura=1280, altura=720, fps=30):
    if SISTEMA == "Windows":
        cap = cv2.VideoCapture(indice, cv2.CAP_DSHOW)
    elif SISTEMA == "Linux":
        cap = cv2.VideoCapture(indice, cv2.CAP_V4L2)
    else:
        cap = cv2.VideoCapture(indice)
    # MJPG permite 720p/1080p a 30 FPS na C920e (YUYV é bem mais lento)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, largura)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, altura)
    cap.set(cv2.CAP_PROP_FPS, fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def _nome_linux(indice):
    try:
        return Path(f"/sys/class/video4linux/video{indice}/name").read_text().strip()
    except OSError:
        return None


def listar_cameras(atual: int, maximo: int = 6):
    """Procura câmeras que realmente entregam imagem (índices 0..maximo-1).

    A câmera em uso não é reaberta: ela entra na lista direto.
    """
    if SISTEMA == "Linux":
        indices = sorted(int(p.name[5:]) for p in Path("/dev").glob("video[0-9]*")
                         if p.name[5:].isdigit())
        indices = [i for i in indices if i < 64]
    else:
        indices = list(range(maximo))

    cameras = []
    for i in indices:
        nome = (_nome_linux(i) if SISTEMA == "Linux" else None) or f"Câmera {i}"
        if i == atual:
            cameras.append({"indice": i, "nome": nome})
            continue
        cap = _abrir(i, 640, 480, 30)
        ok = cap.isOpened() and cap.read()[0]
        cap.release()
        if ok:
            cameras.append({"indice": i, "nome": nome})
    return cameras


class Camera:
    def __init__(self, indice=0, largura=1280, altura=720, fps=30):
        self.indice = indice
        self.largura = largura
        self.altura = altura
        self.fps = fps
        self._quadro = None
        self._trava = threading.Lock()
        self._troca = threading.Lock()
        self._acordar = threading.Event()
        self._rodando = False
        self._thread = None
        self.conectada = False

    def iniciar(self):
        self._rodando = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def parar(self):
        self._rodando = False
        self._acordar.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self):
        while self._rodando:
            indice = self.indice
            cap = _abrir(indice, self.largura, self.altura, self.fps)
            if not cap.isOpened():
                cap.release()
                self.conectada = False
                print(f"[camera] Não consegui abrir a câmera {indice}. Tentando de novo em 3 s...")
                self._acordar.wait(3)
                self._acordar.clear()
                continue

            print(f"[camera] Câmera {indice} conectada.")
            self.conectada = True
            falhas = 0
            # sai do laço se pedirem outra câmera
            while self._rodando and indice == self.indice:
                ok, quadro = cap.read()
                if not ok:
                    falhas += 1
                    if falhas > 30:
                        print("[camera] A câmera parou de responder. Reconectando...")
                        break
                    time.sleep(0.05)
                    continue
                falhas = 0
                with self._trava:
                    self._quadro = quadro
            cap.release()
            self.conectada = False

    def trocar(self, novo: int, espera: float = 8.0) -> bool:
        """Troca para outra câmera. Se ela não entregar imagem, volta para a anterior."""
        with self._troca:
            anterior = self.indice
            if novo == anterior and self.conectada:
                return True
            with self._trava:
                self._quadro = None
            self.indice = novo
            self._acordar.set()

            limite = time.time() + espera
            while time.time() < limite:
                with self._trava:
                    pronto = self._quadro is not None
                if pronto and self.indice == novo:
                    return True
                time.sleep(0.1)

            print(f"[camera] A câmera {novo} não respondeu. Voltando para a {anterior}.")
            self.indice = anterior
            self._acordar.set()
            return False

    def ler(self):
        """Retorna uma cópia do quadro mais recente (ou None)."""
        with self._trava:
            return None if self._quadro is None else self._quadro.copy()
