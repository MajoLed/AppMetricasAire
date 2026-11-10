# AppMetricasAire

Sistema de sensórica en la nube que captura la ubicación (y la humedad) de un dispositivo, la guarda en una infraestructura FIWARE y le muestra a la persona la **calidad del aire de su zona**, tanto en una web como en una app de celular. Incluye un panel administrativo con Grafana para ver los datos crudos.

Proyecto final de Internet de las Cosas (UPB).

---

## 1. ¿Qué hace?

1. Un **sensor** envía su ubicación (latitud, longitud) y, si puede, la humedad.
2. Los datos llegan a una **API** en la nube que valida quién los manda y los reenvía a FIWARE.
3. FIWARE los guarda con historial, de modo que se pueden consultar y graficar en el tiempo.
4. Con la ubicación se busca la **estación de calidad del aire más cercana** (datos públicos de SIATA) y se le muestra el resultado a la persona.

Hay dos vistas:

- **Vista de usuario:** una página sencilla con la calidad del aire de su zona.
- **Panel administrativo:** acceso protegido en `/admin` y un tablero de Grafana con los datos que se han ido guardando.

---

## 2. Arquitectura

```
 Celular (App Inventor)  ─┐
                          ├──►  iot-api (FastAPI)  ──►  Orion  ──►  QuantumLeap  ──►  CrateDB  ──►  Grafana
 T-Beam + HDC1080  ───────┘     :8000, Bearer token      (contexto)    (historial)     (series)       :3000
                                       │
                                       └──► Frontend Flask :80  ◄── CSV de calidad del aire (SIATA)
                                            (vista de usuario + /admin)
```

Todo corre con **Docker Compose** en una instancia de **AWS** con IP pública fija.

| Servicio | Para qué sirve | ¿Público? |
|---|---|---|
| `iot-api` (FastAPI) | Único punto de entrada de los sensores. Valida el token y reenvía a Orion | Sí (:8000) |
| Orion | Guarda el estado actual de cada entidad (por ejemplo `celular:001`) | No |
| QuantumLeap | Toma los cambios de Orion y los lleva a la base de series de tiempo | No |
| CrateDB | Base de datos de series de tiempo con el historial | No |
| MongoDB | Base interna que necesita Orion | No |
| Grafana | Panel administrativo con los gráficos | Sí (:3000) |
| Frontend (Flask) | Vista de usuario y `/admin` | Sí (:80) |

---

## 3. Decisiones de diseño

**Usar FIWARE sin modificar el compose base.** Se partió del `docker-compose` entregado por el profesor y se evitó actualizar versiones de las imágenes. Así se reduce el riesgo de que algo que ya funcionaba deje de hacerlo por un cambio de compatibilidad entre Orion, QuantumLeap y Crate.

**Una sola puerta de entrada: `iot-api`.** Orion, QuantumLeap, CrateDB y Mongo no se exponen a internet, solo se hablan entre sí dentro de la red de Docker. Cualquier dato que llegue de afuera tiene que pasar por la API y traer un token. Esto reduce la superficie de ataque y evita que cualquiera pueda escribir directamente en Orion.

**Autenticación con token Bearer en la API y clave en `/admin`.** Los sensores se identifican con un token. El panel admin del frontend pide usuario y contraseña.

**Secretos fuera del código.** Las claves viven en archivos `.env` que no se suben al repositorio. Se incluyen `.env.example` con los nombres de las variables pero sin valores. El compose lee las variables, no tiene claves escritas.

**Modelo híbrido de sensor.** La arquitectura no depende de un sensor en particular. Hoy el "sensor" puede ser:
- el **celular**, con una app de MIT App Inventor que manda la ubicación, o
- un **sensor físico**: TTGO T-Beam v1.1 (ESP32 con GPS) más un HDC1080 por I2C, con firmware propio en PlatformIO.

Los dos envían lo mismo a la misma API, entonces el resto del sistema no cambia.

**Calidad del aire desde un CSV, no consultando SIATA en cada petición.** Un script (`actualizar_aire.py`) descarga el GeoJSON público de la red de aire de SIATA y lo convierte en un CSV que lee el frontend. Se eligió así para que la vista de usuario cargue rápido, no dependa de que SIATA esté disponible en ese instante y la lógica de "estación más cercana" sea simple de probar.

**Estación más cercana según la ubicación.** Con la latitud y longitud que manda el sensor se calcula la estación de SIATA con menor distancia y se muestra su valor de calidad del aire.

**Dos vistas separadas.** Una para quien usa el servicio (clara y sin tecnicismos) y otra para quien administra (datos crudos y gráficas en Grafana). Mezclarlas habría complicado las dos.

---

## 4. Cómo funciona el flujo de datos

1. El sensor hace un `POST` a `iot-api` en `/ingest` con el header `Authorization: Bearer <token>` y los datos (latitud, longitud, humedad).
2. La API valida el token y actualiza la entidad en **Orion** (por ejemplo, `celular:001` de tipo `Celular`).
3. Orion notifica el cambio a **QuantumLeap**.
4. QuantumLeap guarda el registro en **CrateDB** con su marca de tiempo (tabla `doc.etcelular`).
5. **Grafana** consulta CrateDB y muestra el historial.
6. El **frontend** lee la ubicación actual desde Orion y el CSV de calidad del aire, calcula la estación más cercana y la muestra.

Para esto se probó el camino completo: POST a `iot-api`, la entidad en Orion y el registro en CrateDB.

---

## 5. Estructura del repositorio

```
.
├── docker-compose.yml      # Infraestructura completa
├── .env.example            # Variables esperadas (sin valores)
├── crear.sh                # Script de creación de la app
├── iot-api/                # API de ingesta (FastAPI + Dockerfile)
├── proyectoapp/            # Frontend Flask, script de actualización y CSV
│   ├── app.py
│   ├── actualizar_aire.py
│   └── data/
└── ejemplo mapa interactivo/
```

---

## 6. Cómo levantarlo

1. Copia los ejemplos de variables y ponles tus valores:
   ```bash
   cp .env.example .env
   cp iot-api/.env.example iot-api/.env
   ```
2. Levanta los servicios:
   ```bash
   docker compose up -d
   ```
3. Revisa que estén arriba:
   ```bash
   docker compose ps
   ```
4. Accesos (reemplaza `<IP_PUBLICA>` por la IP de tu instancia):
   - Frontend: `http://<IP_PUBLICA>/`
   - Panel admin: `http://<IP_PUBLICA>/admin`
   - Grafana: `http://<IP_PUBLICA>:3000`
   - API: `http://<IP_PUBLICA>:8000`

Prueba rápida de la API:
```bash
curl -X POST http://<IP_PUBLICA>:8000/ingest \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"latitud": 6.25, "longitud": -75.56}'
```

---

## 7. Fuente de datos

Calidad del aire: red de monitoreo de **SIATA** (Sistema de Alerta Temprana de Medellín y el Valle de Aburrá), publicada como GeoJSON abierto.

---

## 8. Estado y trabajo futuro

- Terminar de conectar Grafana a CrateDB como fuente de datos y armar el tablero.
- Ajustar la app de App Inventor para enviar el header `Authorization` al endpoint `/ingest` y mostrar la calidad del aire en pantalla.
- Integrar el sensor físico (T-Beam con HDC1080) a la API, resolviendo la lectura del GPS.
- Guardar en CrateDB la latitud, longitud, PM2.5 estimado y hora de cada dato.
- Unificar el esquema de CrateDB (`doc` frente a `mtiot`).
