#!/usr/bin/env python3
import csv, json, os, sys
from urllib.request import urlopen, Request

URL = "https://siata.gov.co/DatosRedAire/txtRedAire/RedAireAMVA.geojson"
SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "calidad_aire.csv")


def valido(v):
    return isinstance(v, (int, float)) and v >= 0


req = Request(URL, headers={"User-Agent": "proyecto-iot-upb/1.0 (uso academico)"})
with urlopen(req, timeout=20) as r:
    data = json.load(r)

filas = []
for f in data.get("features", []):
    p = f.get("properties", {})
    lon, lat = f["geometry"]["coordinates"][:2]
    pm25 = p.get("PM2.5_24H-prom")
    if not valido(pm25):
        continue
    pm10 = p.get("PM10_24H-prom")
    filas.append([
        p.get("Estacion", "").strip(), lat, lon, pm25,
        pm10 if valido(pm10) else "", p.get("FechaFin", ""),
    ])

if not filas:
    sys.exit("Sin estaciones con PM2.5: no se sobrescribe el CSV")

tmp = SALIDA + ".tmp"
with open(tmp, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["estacion", "lat", "lon", "pm25", "pm10", "actualizado"])
    w.writerows(filas)
os.replace(tmp, SALIDA)
print(f"{len(filas)} estaciones escritas en {SALIDA}")
