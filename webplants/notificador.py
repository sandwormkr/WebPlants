"""Envio de alertas pelo Telegram, com filtro anti-spam."""
import threading
import time

import cv2
import requests


class Telegram:
    def __init__(self, token: str, chat_id: str):
        self.token = (token or "").strip()
        self.chat_id = (chat_id or "").strip()
        self.configurado = bool(self.token and self.chat_id)
        if not self.configurado:
            print("[telegram] AVISO: TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID vazio no .env. "
                  "Alertas aparecerão só na página.")

    def enviar_foto(self, quadro, legenda: str):
        if not self.configurado:
            return
        threading.Thread(target=self._enviar, args=(quadro, legenda), daemon=True).start()

    def _enviar(self, quadro, legenda):
        ok, jpg = cv2.imencode(".jpg", quadro, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            return
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{self.token}/sendPhoto",
                data={"chat_id": self.chat_id, "caption": legenda},
                files={"photo": ("alerta.jpg", jpg.tobytes(), "image/jpeg")},
                timeout=20,
            )
            if r.ok:
                print("[telegram] Alerta enviado.")
            else:
                print(f"[telegram] Erro {r.status_code}: {r.text[:200]}")
        except requests.RequestException as e:
            print(f"[telegram] Falha de rede: {e}")


class FiltroAlerta:
    """Só dispara quando a mancha aparece em N análises seguidas,
    e respeita um intervalo mínimo entre alertas."""

    def __init__(self, quadros_seguidos=8, intervalo_minutos=15):
        self.necessarios = quadros_seguidos
        self.intervalo = intervalo_minutos * 60
        self.seguidos = 0
        self.ultimo_alerta = 0.0

    def registrar(self, tem_mancha: bool) -> bool:
        self.seguidos = self.seguidos + 1 if tem_mancha else 0
        agora = time.time()
        if self.seguidos >= self.necessarios and agora - self.ultimo_alerta >= self.intervalo:
            self.ultimo_alerta = agora
            self.seguidos = 0
            return True
        return False

    @property
    def em_espera(self) -> int:
        """Segundos até o próximo alerta ser permitido."""
        return max(0, int(self.intervalo - (time.time() - self.ultimo_alerta)))
