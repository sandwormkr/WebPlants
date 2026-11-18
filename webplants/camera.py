"""Captura da webcam em uma thread própria.

Sempre guarda apenas o quadro mais recente, assim o stream e a detecção
nunca ficam atrasados esperando um ao outro.
"""
import platform
import threading
import time

import cv2


class Camera:
    def __init__(self, indice=0, largura=1280, altura=720, fps=30):
        self.indice = indice
        self.largura = largura
        self.altura = altura
        self.fps = fps
        self._quadro = None
        self._trava = threading.Lock()
        self._rodando = False
        self._thread = None
        self.conectada = False

    def _abrir(self):
        sistema = platform.system()
        if sistema == "Windows":
            cap = cv2.VideoCapture(self.indice, cv2.CAP_DSHOW)
        elif sistema == "Linux":
            cap = cv2.VideoCapture(self.indice, cv2.CAP_V4L2)
        else:
            cap = cv2.VideoCapture(self.indice)

        # MJPG permite 720p/1080p a 30 FPS na C920e (YUYV é bem mais lento)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.largura)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.altura)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def iniciar(self):
        self._rodando = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def parar(self):
        self._rodando = False
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self):
        while self._rodando:
            cap = self._abrir()
            if not cap.isOpened():
                self.conectada = False
                print(f"[camera] Não consegui abrir a câmera {self.indice}. Tentando de novo em 3 s...")
                time.sleep(3)
                continue

            print("[camera] Câmera conectada.")
            self.conectada = True
            falhas = 0
            while self._rodando:
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

    def ler(self):
        """Retorna uma cópia do quadro mais recente (ou None)."""
        with self._trava:
            return None if self._quadro is None else self._quadro.copy()
