"""Detecção de plantas e manchas pretas (OpenCV, sem treino).

- Planta: separação da cor verde.
- Mancha preta: região escura colada na folha e majoritariamente cercada por ela.
  O "escuro" é RELATIVO ao brilho da folha, então funciona com pouca ou muita luz.
  Isso evita marcar a terra escura entre as plantas.
"""
import time
from dataclasses import dataclass, field

import cv2
import numpy as np


@dataclass
class Resultado:
    plantas: list = field(default_factory=list)   # [(x1, y1, x2, y2), ...] na resolução original
    manchas: list = field(default_factory=list)
    mascara: np.ndarray | None = None              # imagem de calibração
    limiar: int = 0                                # brilho máximo considerado "preto" agora
    brilho_folha: int = 0                          # brilho mediano das folhas
    tempo_ms: float = 0.0


def _escalar(caixa, fator):
    x, y, w, h = caixa
    return (int(x * fator), int(y * fator), int((x + w) * fator), int((y + h) * fator))


def _elipse(n):
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (n, n))


class DetectorPlantas:
    def __init__(self, cfg: dict):
        self.cfg = cfg

    def analisar(self, quadro: np.ndarray) -> Resultado:
        inicio = time.perf_counter()
        c = self.cfg
        h0, w0 = quadro.shape[:2]
        largura = c.get("largura_analise", 640)
        fator = w0 / largura if w0 > largura else 1.0
        img = cv2.resize(quadro, (int(w0 / fator), int(h0 / fator))) if fator != 1.0 else quadro
        img = cv2.GaussianBlur(img, (3, 3), 0)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        brilho = hsv[:, :, 2]
        area_img = img.shape[0] * img.shape[1]
        resultado = Resultado()

        # 1) Folha = pixels verdes (sem fechar buracos, pois as manchas SÃO buracos na folha)
        folha = cv2.inRange(
            hsv,
            (c["verde_h_min"], c["verde_s_min"], c["verde_v_min"]),
            (c["verde_h_max"], 255, 255),
        )
        folha = cv2.morphologyEx(folha, cv2.MORPH_OPEN, _elipse(3))

        # 2) Planta = folhas unidas -> contornos externos
        unida = cv2.morphologyEx(folha, cv2.MORPH_CLOSE, _elipse(15))
        contornos, _ = cv2.findContours(unida, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contornos = [k for k in contornos if cv2.contourArea(k) >= c["planta_area_min"] * area_img]
        preenchida = np.zeros_like(folha)
        for k in contornos:
            cv2.drawContours(preenchida, [k], -1, 255, thickness=-1)
            resultado.plantas.append(_escalar(cv2.boundingRect(k), fator))

        # 3) "Preto" relativo ao brilho da folha (a webcam ajusta a exposição sozinha)
        pixels_folha = brilho[(folha > 0) & (preenchida > 0)]
        v_folha = int(np.median(pixels_folha)) if pixels_folha.size else 255
        limiar = int(min(c["mancha_v_max"], c["mancha_fator_relativo"] * v_folha))
        resultado.limiar, resultado.brilho_folha = limiar, v_folha

        # 4) Candidatas: escuras, não-folha, dentro da planta ou em "mordidas" da borda
        #    (fechamento grande preenche entalhes da borda sem pegar a terra em volta)
        fechada = cv2.morphologyEx(folha, cv2.MORPH_CLOSE, _elipse(c.get("mancha_borda_px", 25)))
        cont_f, _ = cv2.findContours(fechada, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        regiao = np.zeros_like(folha)
        for k in cont_f:
            if cv2.contourArea(k) >= c["planta_area_min"] * area_img:
                cv2.drawContours(regiao, [k], -1, 255, thickness=-1)
        escuro = cv2.inRange(brilho, 0, limiar)
        candidatas = cv2.bitwise_and(escuro, regiao)
        candidatas = cv2.bitwise_and(candidatas, cv2.bitwise_not(folha))
        # fecha pequenos reflexos (fita isolante e folhas molhadas brilham)
        candidatas = cv2.morphologyEx(candidatas, cv2.MORPH_CLOSE, _elipse(7))
        candidatas = cv2.morphologyEx(candidatas, cv2.MORPH_OPEN, _elipse(3))

        # Cada região escura é analisada separadamente (componentes conectados;
        # contornos externos fariam a terra em volta da planta "engolir" as manchas)
        area_plantas = max(cv2.countNonZero(preenchida), 1)
        n, rotulos, stats, _ = cv2.connectedComponentsWithStats(candidatas, connectivity=8)
        dbg = np.zeros_like(img)
        dbg[folha > 0] = (0, 150, 0)
        COR_BORDA, COR_TAMANHO, COR_MANCHA = (0, 210, 255), (200, 80, 255), (0, 0, 255)
        m = 6
        anel_k = _elipse(2 * m + 1)
        H, W = img.shape[:2]
        for i in range(1, n):
            x, y, w, h, area = stats[i]
            xa, ya = max(x - m, 0), max(y - m, 0)
            xb, yb = min(x + w + m, W), min(y + h + m, H)
            local = (rotulos[ya:yb, xa:xb] == i).astype(np.uint8) * 255
            alvo = dbg[ya:yb, xa:xb]
            if area < c["mancha_area_min"] or area > c["mancha_area_max"] * area_plantas:
                alvo[local > 0] = COR_TAMANHO
                continue
            # 5) A borda ao redor da mancha precisa ser majoritariamente folha
            anel = cv2.subtract(cv2.dilate(local, anel_k), local)
            total = cv2.countNonZero(anel)
            em_folha = cv2.countNonZero(cv2.bitwise_and(anel, folha[ya:yb, xa:xb]))
            if total and em_folha / total >= c["mancha_cercada_min"]:
                alvo[local > 0] = COR_MANCHA
                resultado.manchas.append(_escalar((x, y, w, h), fator))
            else:
                alvo[local > 0] = COR_BORDA

        # Calibração: verde = folha | amarelo = pouca folha em volta | rosa = tamanho | vermelho = mancha
        cv2.putText(dbg, f"folha V~{v_folha}  preto V<={limiar}", (8, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        resultado.mascara = dbg
        resultado.tempo_ms = (time.perf_counter() - inicio) * 1000
        return resultado


def desenhar(quadro, resultado: Resultado):
    for x1, y1, x2, y2 in resultado.plantas:
        cv2.rectangle(quadro, (x1, y1), (x2, y2), (60, 200, 60), 2)
        cv2.putText(quadro, "planta", (x1 + 4, max(y1 - 6, 14)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (60, 200, 60), 2)
    for x1, y1, x2, y2 in resultado.manchas:
        cv2.rectangle(quadro, (x1 - 3, y1 - 3), (x2 + 3, y2 + 3), (0, 0, 255), 2)
        cv2.putText(quadro, "mancha", (x1, max(y1 - 8, 14)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
    return quadro
