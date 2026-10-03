"""Latest caller-supplied location, persisted locally using atomic replacement."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import threading
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

LOCATION_PATH = Path(__file__).resolve().parent / 'data' / 'last_location.json'
_lock = threading.Lock()

class LocationRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')
    latitude: float = Field(ge=-90,le=90,allow_inf_nan=False)
    longitude: float = Field(ge=-180,le=180,allow_inf_nan=False)
    updated_at: str
    source: Literal['/api/audio','/api/intent']


def save(latitude, longitude, source):
    with _lock:
        record = LocationRecord(latitude=latitude,longitude=longitude,
                                updated_at=datetime.now(timezone.utc).isoformat(),source=source)
        LOCATION_PATH.parent.mkdir(parents=True,exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=LOCATION_PATH.parent,
                                             prefix='.location-',suffix='.tmp',delete=False) as file:
                temporary = Path(file.name)
                json.dump(record.model_dump(),file,ensure_ascii=False,allow_nan=False)
                file.flush()
                os.fsync(file.fileno())
            temporary.replace(LOCATION_PATH)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return record


def read():
    with _lock:
        try:
            raw = LOCATION_PATH.read_text(encoding='utf-8')
        except FileNotFoundError:
            return None
        return LocationRecord.model_validate_json(raw)
