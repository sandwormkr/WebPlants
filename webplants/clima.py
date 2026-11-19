"""Temperatura e umidade relativa via Open-Meteo (gratuito, sem chave de API).

Atualiza em segundo plano a cada N minutos e guarda o último valor,
assim a página nunca espera pela internet.
"""
import threading
import time

import requests

URL = "https://api.open-meteo.com/v1/forecast"

# Códigos WMO usados pelo Open-Meteo -> (descrição, ícone de dia, ícone de noite)
CONDICOES = {
    0: ("Céu limpo", "☀️", "🌙"),
    1: ("Predomínio de sol", "🌤️", "🌙"),
    2: ("Parcialmente nublado", "⛅", "☁️"),
    3: ("Nublado", "☁️", "☁️"),
    45: ("Neblina", "🌫️", "🌫️"),
    48: ("Neblina com geada", "🌫️", "🌫️"),
    51: ("Garoa fraca", "🌦️", "🌧️"),
    53: ("Garoa", "🌦️", "🌧️"),
    55: ("Garoa forte", "🌧️", "🌧️"),
    56: ("Garoa congelante", "🌧️", "🌧️"),
    57: ("Garoa congelante", "🌧️", "🌧️"),
    61: ("Chuva fraca", "🌦️", "🌧️"),
    63: ("Chuva", "🌧️", "🌧️"),
    65: ("Chuva forte", "🌧️", "🌧️"),
    66: ("Chuva congelante", "🌧️", "🌧️"),
    67: ("Chuva congelante", "🌧️", "🌧️"),
    71: ("Neve fraca", "🌨️", "🌨️"),
    73: ("Neve", "🌨️", "🌨️"),
    75: ("Neve forte", "❄️", "❄️"),
    77: ("Grãos de neve", "🌨️", "🌨️"),
    80: ("Pancadas de chuva", "🌦️", "🌧️"),
    81: ("Pancadas de chuva", "🌧️", "🌧️"),
    82: ("Pancadas fortes", "⛈️", "⛈️"),
    85: ("Pancadas de neve", "🌨️", "🌨️"),
    86: ("Pancadas de neve", "🌨️", "🌨️"),
    95: ("Trovoada", "⛈️", "⛈️"),
    96: ("Trovoada com granizo", "⛈️", "⛈️"),
    99: ("Trovoada com granizo", "⛈️", "⛈️"),
}


class Clima:
    def __init__(self, cfg: dict):
        self.cidade = cfg.get("cidade", "Guaíra, PR")
        self.lat = cfg.get("latitude", -24.08)
        self.lon = cfg.get("longitude", -54.2558)
        self.intervalo = max(5, cfg.get("atualizar_minutos", 10)) * 60
        self._dados = None
        self._erro = None
        self._trava = threading.Lock()
        self._rodando = False

    def iniciar(self):
        self._rodando = True
        threading.Thread(target=self._loop, daemon=True).start()

    def parar(self):
        self._rodando = False

    def _loop(self):
        while self._rodando:
            self.atualizar()
            # se falhou, tenta de novo mais cedo
            espera = self.intervalo if self._erro is None else 60
            for _ in range(int(espera)):
                if not self._rodando:
                    return
                time.sleep(1)

    def atualizar(self):
        try:
            r = requests.get(URL, timeout=10, params={
                "latitude": self.lat,
                "longitude": self.lon,
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,"
                           "weather_code,wind_speed_10m,is_day",
                "daily": "temperature_2m_max,temperature_2m_min",
                "forecast_days": 1,
                "timezone": "America/Sao_Paulo",
            })
            r.raise_for_status()
            j = r.json()
            atual, dia = j["current"], j.get("daily", {})
            codigo = int(atual.get("weather_code", 0))
            desc, icone_dia, icone_noite = CONDICOES.get(codigo, ("—", "🌡️", "🌡️"))
            dados = {
                "cidade": self.cidade,
                "temperatura": round(atual["temperature_2m"], 1),
                "umidade": round(atual["relative_humidity_2m"]),
                "sensacao": round(atual.get("apparent_temperature", atual["temperature_2m"]), 1),
                "vento": round(atual.get("wind_speed_10m", 0)),
                "descricao": desc,
                "icone": icone_dia if atual.get("is_day", 1) else icone_noite,
                "maxima": round(dia.get("temperature_2m_max", [None])[0] or 0),
                "minima": round(dia.get("temperature_2m_min", [None])[0] or 0),
                "horario": atual.get("time", "")[-5:],  # "2026-11-19T14:00" -> "14:00"
            }
            with self._trava:
                self._dados, self._erro = dados, None
        except Exception as e:  # noqa: BLE001
            with self._trava:
                self._erro = str(e)
            print(f"[clima] Não consegui atualizar: {e}")

    def obter(self) -> dict:
        with self._trava:
            if self._dados is None:
                return {"ok": False, "cidade": self.cidade, "erro": self._erro or "carregando"}
            return {"ok": True, "desatualizado": self._erro is not None, **self._dados}

    def resumo(self) -> str:
        """Linha curta para o alerta do Telegram."""
        d = self.obter()
        if not d["ok"]:
            return ""
        return f"🌡️ {d['temperatura']:.0f}°C · 💧 {d['umidade']}% em {d['cidade']}"
