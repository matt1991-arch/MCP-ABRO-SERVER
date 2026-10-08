"""Cálculos ABRO 4.0.1 según Manual Técnico MMAyA (FAO-56) y Manual de Usuario.

Referencias:
- Pe: Altiplano (pp-12)*0.70 | Valles (pp-15)*0.75 | Chaco/Tropico (pp-20)*0.80
- Ef_total = Ecap * Econd * Edist * Eapl
- Econd/Edist por tramo: Ef_km ^ Long_km ; total = promedio ponderado por longitud
- Eapl: promedio ponderado con tabla fija (inundación .25, surcos .40, melgas .45,
  superficial mejorado .60, aspersión .80, microaspersión .85, goteo .90)
- ETo: Penman-Monteith FAO-56 (Anexo 1 manual técnico), con nubosidad -> n = N*(1-nub)
- Vd (m3) = 10 * An(ha) * Nn(mm) / Ef_total
- Balance por campaña: mes crítico = min(oferta_m3 / demanda_bruta_m3); ha_calc = ha_prop * factor
"""
import math

MESES = ["jun", "jul", "ago", "sep", "oct", "nov", "dic", "ene", "feb", "mar", "abr", "may"]
DIAS_MES = {"jun": 30, "jul": 31, "ago": 31, "sep": 30, "oct": 31, "nov": 30,
            "dic": 31, "ene": 31, "feb": 28, "mar": 31, "abr": 30, "may": 31}

EF_APLICACION_FIJA = {
    "inundacion": 0.25,
    "surcos": 0.40,
    "melgas": 0.45,
    "superficial_mejorado": 0.60,
    "aspersion": 0.80,
    "microaspersion": 0.85,
    "goteo": 0.90,
}

# Zona ABRO: (umbral_mm, factor). id 1=Chaco/Valles mesotérmicos, 2=Valles, 3=Altiplano, 5=Trópico y Llanos, 4=FAO
ZONAS_PP = {
    1: (20, 0.80),
    2: (15, 0.75),
    3: (12, 0.70),
    4: (1, 2.0),   # zona FAO en abro.db (factor atípico, solo referencial)
    5: (20, 0.80),
}


def precipitacion_efectiva(pp_mm: float, zona_id: int = 2) -> float:
    umbral, factor = ZONAS_PP.get(int(zona_id), (15, 0.75))
    if pp_mm <= umbral:
        return 0.0
    return round((pp_mm - umbral) * factor, 2)


def precipitacion_efectiva_serie(pp_mensual: list[float], zona_id: int = 2) -> list[float]:
    return [precipitacion_efectiva(v, zona_id) for v in pp_mensual]


def eficiencia_tramos(tramos: list[dict]) -> dict:
    """tramos = [{ef_km: 0.95, longitud_km: 2.5}, ...]. Retorna eficiencia por tramo y total ponderado."""
    if not tramos:
        return {"eficiencias_tramo": [], "eficiencia_total": 1.0}
    efs, total_L = [], 0.0
    for t in tramos:
        ef_km = float(t["ef_km"])
        L = float(t["longitud_km"])
        if not (0 < ef_km <= 1) or L < 0:
            raise ValueError("ef_km debe estar en (0,1] y longitud_km >= 0")
        ef = ef_km ** L if L > 0 else 1.0
        efs.append(round(ef, 5))
        total_L += L
    if total_L == 0:
        ef_total = 1.0
    else:
        ef_total = sum(e * float(t["longitud_km"]) for e, t in zip(efs, tramos)) / total_L
    return {"eficiencias_tramo": efs, "eficiencia_total": round(ef_total, 5)}


def eficiencia_aplicacion(metodos: list[dict]) -> dict:
    """metodos = [{metodo: 'aspersion', porcentaje: 60}, ...] suma debe ser 100."""
    if not metodos:
        return {"eficiencia_aplicacion": 1.0, "detalle": []}
    total_pct = sum(float(m["porcentaje"]) for m in metodos)
    if abs(total_pct - 100.0) > 0.01:
        raise ValueError(f"Los porcentajes deben sumar 100 (actual {total_pct})")
    ef = 0.0
    detalle = []
    for m in metodos:
        key = str(m["metodo"]).lower()
        if key not in EF_APLICACION_FIJA:
            raise ValueError(f"Método desconocido: {m['metodo']}. Válidos: {sorted(EF_APLICACION_FIJA)}")
        v = EF_APLICACION_FIJA[key]
        ef += v * float(m["porcentaje"]) / 100.0
        detalle.append({"metodo": key, "eficiencia": v, "porcentaje": float(m["porcentaje"])})
    return {"eficiencia_aplicacion": round(ef, 5), "detalle": detalle}


def eficiencia_total(ecap: float, econd: float, edist: float, eapl: float) -> float:
    for v, n in [(ecap, "ecap"), (econd, "econd"), (edist, "edist"), (eapl, "eapl")]:
        if not (0 < v <= 1):
            raise ValueError(f"{n} debe estar en (0,1]")
    return round(ecap * econd * edist * eapl, 5)


# ---------------- ETo Penman-Monteith FAO-56 (mensual) ----------------

def _j_dia(mes_idx_eto: int) -> int:
    """mes_idx_eto: 0=jun..11=may (orden ABRO). J = día medio del mes."""
    M = {0: 6, 1: 7, 2: 8, 3: 9, 4: 10, 5: 11, 6: 12, 7: 1, 8: 2, 9: 3, 10: 4, 11: 5}[mes_idx_eto]
    return int(30.4 * M - 15)


def eto_penman_monteith_mes(lat_deg: float, alt_msnm: float, mes_idx_eto: int,
                            tmax: float, tmin: float, hr_media: float,
                            nubosidad: float, viento_ms: float,
                            tmedia_prev: float | None = None,
                            tmedia_next: float | None = None) -> dict:
    """Un mes. mes_idx_eto 0=jun..11=may. nubosidad 0..1. Retorna ETo mm/día y términos intermedios."""
    phi = math.radians(lat_deg)
    T = (tmax + tmin) / 2.0
    # Presión atmosférica y gamma
    P = 101.3 * ((293 - 0.0065 * alt_msnm) / 293) ** 5.26
    gamma = 0.000665 * P  # kPa/°C (Cp*P/(eps*lambda), lambda=2.45)
    # Delta
    delta = 4098 * (0.6108 * math.exp(17.27 * T / (T + 237.3))) / ((T + 237.3) ** 2)
    # Ra
    J = _j_dia(mes_idx_eto)
    dr = 1 + 0.033 * math.cos(2 * math.pi / 365 * J)
    decl = 0.409 * math.sin(2 * math.pi / 365 * J - 1.39)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(phi) * math.tan(decl))))
    Ra = 24 * 60 / math.pi * 0.0820 * dr * (ws * math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(decl) * math.sin(ws))
    N = 24 / math.pi * ws
    n = N * (1 - nubosidad)
    Rs = (0.25 + 0.50 * (n / N if N > 0 else 0)) * Ra
    Rso = (0.75 + 2e-5 * alt_msnm) * Ra
    Rns = (1 - 0.23) * Rs
    # Presiones de vapor
    def eo(t): return 0.6108 * math.exp(17.27 * t / (t + 237.3))
    es = (eo(tmax) + eo(tmin)) / 2.0
    ea = (hr_media / 100.0) * eo(T)
    # Rnl
    sigma = 4.903e-9
    tmaxk, tmink = tmax + 273.16, tmin + 273.16
    rel = min(1.0, Rs / Rso if Rso > 0 else 0)
    Rnl = sigma * ((tmaxk ** 4 + tmink ** 4) / 2) * (0.34 - 0.14 * math.sqrt(max(ea, 0))) * (1.35 * rel - 0.35)
    Rn = Rns - Rnl
    # G mensual
    if tmedia_prev is not None and tmedia_next is not None:
        G = 0.07 * (tmedia_next - tmedia_prev)
    else:
        G = 0.0
    u2 = viento_ms  # se asume medición a 2 m
    ETo = (0.408 * delta * (Rn - G) + gamma * 900 / (T + 273) * u2 * (es - ea)) / (delta + gamma * (1 + 0.34 * u2))
    return {
        "ETo_mm_dia": round(max(ETo, 0.0), 2),
        "Delta": round(delta, 4), "gamma": round(gamma, 4),
        "Ra": round(Ra, 2), "N_horas": round(N, 2), "n_horas": round(n, 2),
        "Rs": round(Rs, 2), "Rns": round(Rns, 2), "Rnl": round(Rnl, 2),
        "Rn": round(Rn, 2), "G": round(G, 3),
        "es": round(es, 3), "ea": round(ea, 3), "deficit": round(es - ea, 3),
    }


def eto_serie_anual(lat_deg: float, alt_msnm: float, datos: list[dict]) -> list[dict]:
    """datos: 12 dicts en orden jun..may con {tmax,tmin,hr,nubosidad,viento}. Retorna lista con ETo diaria y mensual."""
    if len(datos) != 12:
        raise ValueError("Se requieren 12 meses en orden jun..may")
    out = []
    for i, d in enumerate(datos):
        t_prev = (datos[i - 1]["tmax"] + datos[i - 1]["tmin"]) / 2 if i > 0 else (datos[i]["tmax"] + datos[i]["tmin"]) / 2
        t_next = (datos[(i + 1) % 12]["tmax"] + datos[(i + 1) % 12]["tmin"]) / 2 if i < 11 else (datos[i]["tmax"] + datos[i]["tmin"]) / 2
        r = eto_penman_monteith_mes(lat_deg, alt_msnm, i, d["tmax"], d["tmin"],
                                   d["hr"], d["nubosidad"], d["viento"],
                                   t_prev, t_next)
        dias = DIAS_MES[MESES[i]]
        r["mes"] = MESES[i]
        r["ETo_mm_mes"] = round(r["ETo_mm_dia"] * dias, 1)
        out.append(r)
    return out


# ---------------- Dotación y balance ----------------

def dotacion_volumen(Nn_mm: float, ha: float, ef_total: float) -> float:
    """Vd (m3) = 10 * An(ha) * Nn(mm) / Ef_total. Nn = necesidad neta mensual."""
    if ef_total <= 0 or ef_total > 1:
        raise ValueError("ef_total debe estar en (0,1]")
    return round(10 * ha * max(Nn_mm, 0.0) / ef_total, 1)


def modulo_riego_lps_ha(vol_m3_mes: float, dias_mes: int) -> float:
    """Caudal continuo 24h en l/s/ha para un volumen mensual de 1 ha."""
    if dias_mes <= 0:
        raise ValueError("dias_mes inválido")
    return round(vol_m3_mes / (dias_mes * 86400) * 1000, 3)


def balance_campana(oferta_m3: list[float], demanda_neta_mm: list[float],
                    ha_propuesta: float, ef_total: float) -> dict:
    """Balance oferta vs demanda para una campaña (12 meses jun..may).

    demanda_bruta_m3 = 10*ha*Nn/Ef. factor_mes = oferta/demanda.
    Mes crítico = menor factor. ha_calc = ha_prop * factor_min (si oferta<demanda)
    o mayor (si sobra agua). Retorna tabla mensual y resumen.
    """
    if not (len(oferta_m3) == 12 and len(demanda_neta_mm) == 12):
        raise ValueError("oferta_m3 y demanda_neta_mm deben tener 12 valores (jun..may)")
    dem_bruta = [dotacion_volumen(nn, ha_propuesta, ef_total) for nn in demanda_neta_mm]
    factores, usados, sobrantes = [], [], []
    for of, dem in zip(oferta_m3, dem_bruta):
        if dem <= 0:
            factores.append(None); usados.append(0.0); sobrantes.append(round(of, 1))
        else:
            f = of / dem
            factores.append(round(f, 4))
            usados.append(round(min(of, dem), 1))
            sobrantes.append(round(max(of - dem, 0.0), 1))
    valid = [(i, f) for i, f in enumerate(factores) if f is not None]
    if not valid:
        factor_min, mes_crit = 1.0, None
    else:
        mes_crit, factor_min = min(valid, key=lambda x: x[1])
    ha_calc = round(ha_propuesta * factor_min, 2) if valid else ha_propuesta
    # Módulo de riego del mes crítico (sobre demanda bruta por ha)
    if mes_crit is not None and ha_propuesta > 0:
        vol_ha = dem_bruta[mes_crit] / ha_propuesta if ha_propuesta else 0
        mod = modulo_riego_lps_ha(vol_ha, DIAS_MES[MESES[mes_crit]])
    else:
        mod = 0.0
    return {
        "ha_propuesta": ha_propuesta,
        "ha_calculada": ha_calc,
        "factor_mes_critico": round(factor_min, 4),
        "mes_critico": MESES[mes_crit] if mes_crit is not None else None,
        "demanda_bruta_m3": [round(v, 1) for v in dem_bruta],
        "factores": factores,
        "vol_usado_m3": usados,
        "vol_sobrante_m3": sobrantes,
        "vol_oferta_total": round(sum(oferta_m3), 1),
        "vol_usado_total": round(sum(usados), 1),
        "vol_sobrante_total": round(sum(sobrantes), 1),
        "modulo_riego_lps_ha": mod,
    }
