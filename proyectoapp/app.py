import csv
import math
import os
from functools import wraps

import requests
from flask import Flask, Response, jsonify, render_template_string, request

# ---------------------------------------------------------------- configuración
ORION = os.getenv("ORION_URL", "http://orion:1026")
QUANTUMLEAP = os.getenv("QL_URL", "http://quantumleap:8668")
CRATE = os.getenv("CRATE_URL", "http://crate-db:4200")
ENTIDAD = os.getenv("ENTIDAD", "persona:001")
HEADERS_FIWARE = {"Fiware-Service": "iot", "Fiware-ServicePath": "/"}
CSV_PATH = os.getenv("CSV_PATH", os.path.join(os.path.dirname(__file__), "data", "calidad_aire.csv"))
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "cambia-esta-clave")

app = Flask(__name__)


# ---------------------------------------------------------------- archivo de calidad del aire
ALIAS = {
    "estacion": ["estacion", "estación", "nombre", "station", "name"],
    "lat": ["lat", "latitud", "latitude"],
    "lon": ["lon", "lng", "longitud", "longitude"],
    "pm25": ["pm25", "pm2.5", "pm2_5", "pm_25"],
    "pm10": ["pm10", "pm_10"],
    "actualizado": ["actualizado", "fecha", "date", "timestamp"],
}


def _num(v):
    try:
        return float(str(v).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None


def cargar_estaciones():
    """Lee el CSV en cada consulta, así los cambios al archivo se ven sin reiniciar."""
    estaciones = []
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        lector = csv.DictReader(f)
        cols = {(c or "").strip().lower(): c for c in (lector.fieldnames or [])}

        def col(clave):
            for a in ALIAS[clave]:
                if a in cols:
                    return cols[a]
            return None

        mapa = {k: col(k) for k in ALIAS}
        for fila in lector:
            lat, lon = _num(fila.get(mapa["lat"])), _num(fila.get(mapa["lon"]))
            if lat is None or lon is None:
                continue
            estaciones.append({
                "nombre": (fila.get(mapa["estacion"]) or "Estación sin nombre").strip(),
                "lat": lat,
                "lon": lon,
                "pm25": _num(fila.get(mapa["pm25"])),
                "pm10": _num(fila.get(mapa["pm10"])) if mapa["pm10"] else None,
                "actualizado": (fila.get(mapa["actualizado"]) or "").strip() if mapa["actualizado"] else "",
            })
    return estaciones


def distancia_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# Umbrales referenciales de PM2.5 (µg/m³), ajustables a la norma que usen en el curso.
CATEGORIAS = [
    (12.0, "buena", "Aire bueno", "Es un buen momento para salir y hacer ejercicio al aire libre."),
    (37.0, "moderada", "Aire moderado", "La mayoría puede salir con normalidad. Si eres sensible a la contaminación, evita esfuerzos largos afuera."),
    (55.0, "sensibles", "Dañino para grupos sensibles", "Niños, adultos mayores y personas con asma o problemas del corazón deberían reducir el tiempo al aire libre."),
    (150.0, "danina", "Aire dañino", "Evita el ejercicio intenso afuera. Si puedes, permanece en espacios cerrados."),
    (250.0, "muy_danina", "Aire muy dañino", "Quédate en interiores y usa tapabocas si debes salir."),
    (float("inf"), "peligrosa", "Aire peligroso", "Evita salir. Emergencia ambiental."),
]


def categoria(pm25):
    if pm25 is None:
        return {"clave": "sin", "nombre": "Sin dato", "mensaje": "La estación más cercana no reporta PM2.5 por ahora."}
    for tope, clave, nombre, mensaje in CATEGORIAS:
        if pm25 <= tope:
            return {"clave": clave, "nombre": nombre, "mensaje": mensaje}


# ---------------------------------------------------------------- datos del sensor (celular → Orion)
class SinDatos(Exception):
    pass


def leer_ubicacion():
    r = requests.get(f"{ORION}/v2/entities/{ENTIDAD}", headers=HEADERS_FIWARE, timeout=4)
    if r.status_code == 404:
        raise SinDatos()
    r.raise_for_status()
    e = r.json()
    return float(e["latitud"]["value"]), float(e["longitud"]["value"])


def estacion_cercana(lat, lon):
    est = cargar_estaciones()
    if not est:
        return None
    mejor = min(est, key=lambda s: distancia_km(lat, lon, s["lat"], s["lon"]))
    return {**mejor, "distancia_km": round(distancia_km(lat, lon, mejor["lat"], mejor["lon"]), 2)}


@app.get("/api/estado")
def api_estado():
    try:
        lat, lon = leer_ubicacion()
    except SinDatos:
        return jsonify(ok=False, motivo="sin_datos")
    except (requests.RequestException, KeyError, ValueError):
        return jsonify(ok=False, motivo="servidor")
    try:
        est = estacion_cercana(lat, lon)
    except (OSError, ValueError):
        return jsonify(ok=False, motivo="archivo")
    if est is None:
        return jsonify(ok=False, motivo="archivo")
    return jsonify(ok=True, lat=lat, lon=lon, estacion=est, categoria=categoria(est["pm25"]))


# ---------------------------------------------------------------- panel de administración
def requiere_login(f):
    @wraps(f)
    def envoltura(*a, **kw):
        auth = request.authorization
        if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
            return Response("Acceso restringido", 401, {"WWW-Authenticate": 'Basic realm="Panel de administración"'})
        return f(*a, **kw)
    return envoltura


def probar(url, extraer):
    try:
        r = requests.get(url, timeout=3)
        r.raise_for_status()
        return {"ok": True, "detalle": extraer(r)}
    except Exception:
        return {"ok": False, "detalle": "sin respuesta"}


@app.get("/api/admin")
@requiere_login
def api_admin():
    servicios = [
        {"nombre": "Orion (recibe los datos)", **probar(f"{ORION}/version", lambda r: r.json().get("orion", {}).get("version", "activo"))},
        {"nombre": "QuantumLeap (guarda el historial)", **probar(f"{QUANTUMLEAP}/version", lambda r: r.json().get("version", "activo"))},
        {"nombre": "Crate (base de datos)", **probar(f"{CRATE}/", lambda r: r.json().get("version", {}).get("number", "activo"))},
    ]
    try:
        lat, lon = leer_ubicacion()
        ultima = {"lat": lat, "lon": lon}
    except SinDatos:
        ultima = None
    except Exception:
        ultima = {"error": True}
    try:
        estaciones = cargar_estaciones()
    except Exception:
        estaciones = []
    return jsonify(servicios=servicios, ultima=ultima, estaciones=estaciones, entidad=ENTIDAD)


# ---------------------------------------------------------------- páginas
PAGINA_USUARIO = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aire a tu alrededor</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,800&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:#e9edf0; --ink:#1c2a33; --haze:.15; --ridge-far:#b9c6cf; --ridge-near:#8fa2af;
    --font:"Bricolage Grotesque", system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  body[data-cat="buena"]      { --bg:#d9f0e2; --ink:#0f3a24; --haze:.10; --ridge-far:#a6d3b8; --ridge-near:#6fb38d; }
  body[data-cat="moderada"]   { --bg:#faedbd; --ink:#3b2f05; --haze:.30; --ridge-far:#e6d28b; --ridge-near:#c9b055; }
  body[data-cat="sensibles"]  { --bg:#fad5ac; --ink:#4a2504; --haze:.45; --ridge-far:#e9b57e; --ridge-near:#c98a4b; }
  body[data-cat="danina"]     { --bg:#f5b3a8; --ink:#4d0f0c; --haze:.60; --ridge-far:#dd8d80; --ridge-near:#b9655a; }
  body[data-cat="muy_danina"] { --bg:#dcb0d3; --ink:#3d1035; --haze:.72; --ridge-far:#bc88b1; --ridge-near:#96648b; }
  body[data-cat="peligrosa"]  { --bg:#c9a3b0; --ink:#2f0b1a; --haze:.85; --ridge-far:#a87888; --ridge-near:#82525f; }
  * { box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    margin: 0; background: var(--bg); color: var(--ink); font-family: var(--font);
    transition: background-color .9s ease, color .9s ease;
    min-height: 100vh; display: flex; flex-direction: column; position: relative; overflow-x: hidden;
  }
  main { position: relative; z-index: 2; padding: clamp(24px, 6vw, 72px) clamp(16px, 6vw, 72px) 0; max-width: 980px; }
  h1 { margin: 0; font-weight: 600; font-size: clamp(1.4rem, 3.4vw, 2.1rem); letter-spacing: -.01em; line-height: 1.15; max-width: 22ch; }
  .cifra { display: flex; align-items: baseline; gap: .6rem; margin-top: clamp(12px, 3vh, 36px); flex-wrap: wrap; }
  #valor { font-weight: 800; font-size: clamp(6rem, 24vw, 15rem); line-height: .85; letter-spacing: -.045em; font-variation-settings: "opsz" 96; }
  #unidad { font-size: clamp(1rem, 2vw, 1.3rem); font-weight: 400; max-width: 14ch; line-height: 1.25; opacity: .85; }
  #veredicto { margin: clamp(16px, 3vh, 32px) 0 0; font-size: clamp(1.6rem, 4.4vw, 2.8rem); font-weight: 600; letter-spacing: -.02em; line-height: 1.1; }
  #mensaje { margin: .7rem 0 0; font-size: clamp(1.05rem, 2vw, 1.25rem); line-height: 1.45; max-width: 46ch; }
  #aviso { margin: .9rem 0 0; font-size: 1rem; max-width: 46ch; font-weight: 600; }
  #aviso:empty { display: none; }
  dl { margin: clamp(20px, 4vh, 40px) 0 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, max-content)); gap: .6rem 2.4rem; font-size: .98rem; }
  dt { opacity: .7; font-size: .88rem; }
  dd { margin: 0; font-weight: 600; }
  .valle { position: absolute; left: 0; right: 0; bottom: 0; z-index: 1; height: 38vh; min-height: 220px; pointer-events: none; }
  .valle svg { position: absolute; inset: 0; width: 100%; height: 100%; }
  .valle .far { fill: var(--ridge-far); transition: fill .9s ease; }
  .valle .near { fill: var(--ridge-near); transition: fill .9s ease; }
  .bruma { position: absolute; inset: 0; background: linear-gradient(to top, transparent 0%, var(--bg) 100%); opacity: var(--haze); transition: opacity .9s ease; }
  footer { position: relative; z-index: 2; margin-top: auto; padding: 16px clamp(16px, 6vw, 72px) 18px; font-size: .85rem; }
  footer a { color: inherit; opacity: .75; }
  footer a:hover { opacity: 1; }
  a:focus-visible { outline: 3px solid currentColor; outline-offset: 3px; }
  @media (prefers-reduced-motion: reduce) { body, .valle .far, .valle .near, .bruma { transition: none; } }
</style>
</head>
<body data-cat="sin">
<main>
  <h1 id="lugar">Buscando tu ubicación…</h1>
  <div class="cifra"><span id="valor" aria-live="polite">–</span><span id="unidad">µg/m³ de PM2.5</span></div>
  <p id="veredicto"></p>
  <p id="mensaje"></p>
  <p id="aviso"></p>
  <dl id="meta"></dl>
</main>
<div class="valle" aria-hidden="true">
  <svg viewBox="0 0 1200 400" preserveAspectRatio="none">
    <path class="far" d="M0 190 L90 150 L170 185 L260 120 L350 170 L450 105 L540 160 L640 125 L740 175 L850 110 L950 165 L1060 130 L1200 180 L1200 400 L0 400 Z"/>
    <path class="near" d="M0 270 L120 225 L210 255 L330 200 L440 250 L560 215 L690 265 L800 220 L930 262 L1050 228 L1200 268 L1200 400 L0 400 Z"/>
  </svg>
  <div class="bruma"></div>
</div>
<footer><a href="/admin">Administración</a></footer>
<script>
const $ = id => document.getElementById(id);
function fila(dt, dd) {
  const wrap = document.createElement('div');
  const a = document.createElement('dt'); a.textContent = dt;
  const b = document.createElement('dd'); b.textContent = dd;
  wrap.append(a, b); return wrap;
}
function vacio(titulo, detalle) {
  document.body.dataset.cat = 'sin';
  $('lugar').textContent = titulo; $('valor').textContent = '–';
  $('veredicto').textContent = ''; $('mensaje').textContent = detalle;
  $('aviso').textContent = ''; $('meta').replaceChildren();
}
async function actualizar() {
  try {
    const r = await fetch('/api/estado'); const d = await r.json();
    if (!d.ok) {
      if (d.motivo === 'sin_datos') vacio('Aún no recibimos tu ubicación', 'Abre la app MiUbicación en tu celular y pulsa «Obtener ubicación».');
      else if (d.motivo === 'archivo') vacio('No pudimos leer los datos de calidad del aire', 'Revisa el archivo data/calidad_aire.csv.');
      else vacio('No hay conexión con el servidor', 'Reintentaremos en unos segundos.');
      return;
    }
    const e = d.estacion, c = d.categoria;
    document.body.dataset.cat = c.clave;
    $('lugar').textContent = 'Estás cerca de ' + e.nombre;
    $('valor').textContent = e.pm25 === null ? '–' : Math.round(e.pm25);
    $('veredicto').textContent = c.nombre;
    $('mensaje').textContent = c.mensaje;
    $('aviso').textContent = e.distancia_km > 15 ? 'La estación más cercana está a ' + e.distancia_km.toString().replace('.', ',') + ' km, así que este dato puede no representar tu zona.' : '';
    const meta = [fila('Distancia a la estación', e.distancia_km.toString().replace('.', ',') + ' km')];
    if (e.pm10 !== null) meta.push(fila('PM10', Math.round(e.pm10) + ' µg/m³'));
    if (e.actualizado) meta.push(fila('Dato de la estación', e.actualizado));
    meta.push(fila('Tu ubicación', d.lat.toFixed(4) + ', ' + d.lon.toFixed(4)));
    $('meta').replaceChildren(...meta);
  } catch (err) { vacio('No hay conexión con el servidor', 'Reintentaremos en unos segundos.'); }
}
actualizar(); setInterval(actualizar, 5000);
</script>
</body>
</html>
"""

PAGINA_ADMIN = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Administración</title>
<style>
  :root { --bg:#f6f7f9; --ink:#1d232a; --muted:#66707b; --line:#dde1e6; --ok:#1f8a4c; --bad:#c23b2e; --accent:#1c4e80; }
  @media (prefers-color-scheme: dark) { :root { --bg:#14181d; --ink:#e7eaee; --muted:#98a2ad; --line:#2a3139; --ok:#4cc17c; --bad:#ef7a6e; --accent:#7db4ec; } }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--ink); font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
  main { max-width: 860px; margin: 0 auto; padding: 32px 16px 56px; }
  header { display: flex; justify-content: space-between; align-items: baseline; gap: 16px; flex-wrap: wrap; }
  h1 { font-size: 1.5rem; margin: 0; }
  h2 { font-size: 1.05rem; margin: 36px 0 8px; }
  a { color: var(--accent); }
  a:focus-visible, button:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }
  .accesos { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 12px; }
  .boton { display: inline-block; padding: 10px 16px; border-radius: 6px; background: var(--accent); color: #fff; text-decoration: none; font-weight: 600; }
  .boton.sec { background: transparent; color: var(--accent); border: 1px solid var(--accent); }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); }
  th { font-weight: 600; color: var(--muted); font-size: .9rem; }
  td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
  .punto { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; background: var(--muted); }
  .punto.ok { background: var(--ok); } .punto.bad { background: var(--bad); }
  .muted { color: var(--muted); }
</style>
</head>
<body>
<main>
  <header>
    <h1>Panel de administración</h1>
    <a href="/">Ver vista de usuario</a>
  </header>
  <div class="accesos">
    <a class="boton" id="grafana" href="#" target="_blank" rel="noopener">Abrir Grafana</a>
    <a class="boton sec" id="crate" href="#" target="_blank" rel="noopener">Consola de Crate</a>
  </div>
  <h2>Servicios</h2>
  <table><tbody id="servicios"></tbody></table>
  <h2>Última ubicación recibida</h2>
  <p id="ultima" class="muted">Cargando…</p>
  <h2>Estaciones de calidad del aire cargadas</h2>
  <table>
    <thead><tr><th>Estación</th><th class="num">PM2.5</th><th class="num">PM10</th><th>Actualizado</th></tr></thead>
    <tbody id="estaciones"></tbody>
  </table>
</main>
<script>
document.getElementById('grafana').href = location.protocol + '//' + location.hostname + ':3000';
document.getElementById('crate').href = location.protocol + '//' + location.hostname + ':4200';
function td(txt, cls) { const c = document.createElement('td'); c.textContent = txt; if (cls) c.className = cls; return c; }
async function cargar() {
  try {
    const d = await (await fetch('/api/admin')).json();
    const sv = document.getElementById('servicios'); sv.replaceChildren();
    for (const s of d.servicios) {
      const tr = document.createElement('tr'); const c = document.createElement('td');
      const p = document.createElement('span'); p.className = 'punto ' + (s.ok ? 'ok' : 'bad');
      c.append(p, s.nombre); tr.append(c, td(s.ok ? 'Activo, versión ' + s.detalle : 'Sin respuesta', s.ok ? '' : 'muted')); sv.append(tr);
    }
    const u = document.getElementById('ultima');
    if (d.ultima === null) u.textContent = 'Aún no llega ninguna ubicación a ' + d.entidad + '.';
    else if (d.ultima.error) u.textContent = 'No se pudo consultar Orion.';
    else u.textContent = d.entidad + ': ' + d.ultima.lat.toFixed(5) + ', ' + d.ultima.lon.toFixed(5);
    const es = document.getElementById('estaciones'); es.replaceChildren();
    for (const e of d.estaciones) {
      const tr = document.createElement('tr');
      tr.append(td(e.nombre), td(e.pm25 === null ? '–' : e.pm25, 'num'), td(e.pm10 === null ? '–' : e.pm10, 'num'), td(e.actualizado || '–'));
      es.append(tr);
    }
  } catch (e) { document.getElementById('ultima').textContent = 'No se pudo cargar el estado.'; }
}
cargar(); setInterval(cargar, 5000);
</script>
</body>
</html>
"""


@app.get("/")
def vista_usuario():
    return render_template_string(PAGINA_USUARIO)


@app.get("/admin")
@requiere_login
def vista_admin():
    return render_template_string(PAGINA_ADMIN)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "80")))
