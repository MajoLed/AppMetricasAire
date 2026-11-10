import os
import secrets

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="IoT Security Gateway")

API_KEY = os.environ["IOT_API_KEY"]
ORION_URL = os.getenv("ORION_URL", "http://orion:1026")


class SensorData(BaseModel):
    sensor_id: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-zA-Z0-9_:-]+$"
    )
    latitud: float = Field(ge=-90, le=90)
    longitud: float = Field(ge=-180, le=180)
    humedad: float | None = Field(default=None, ge=0, le=100)


@app.post("/ingest")
async def ingest(
    data: SensorData,
    authorization: str | None = Header(default=None)
):
    expected = f"Bearer {API_KEY}"

    if not authorization or not secrets.compare_digest(
        authorization, expected
    ):
        raise HTTPException(status_code=401, detail="No autorizado")

    payload = {
        "latitud":  {"type": "Number", "value": data.latitud},
        "longitud": {"type": "Number", "value": data.longitud},
    }
    if data.humedad is not None:
        payload["humedad"] = {"type": "Number", "value": data.humedad}

    headers = {
        "Content-Type": "application/json",
        "Fiware-Service": "iot",
        "Fiware-ServicePath": "/"
    }

    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.patch(
                f"{ORION_URL}/v2/entities/{data.sensor_id}/attrs",
                json=payload,
                headers=headers
            )
        except httpx.RequestError:
            raise HTTPException(
                status_code=502,
                detail="Error de conexión con Orion"
            )

    if response.status_code == 204:
        return {"status": "ok", "sensor_id": data.sensor_id}

    if response.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail="La entidad del sensor no existe en Orion"
        )

    raise HTTPException(
        status_code=502,
        detail="Orion no pudo procesar la actualización"
    )
