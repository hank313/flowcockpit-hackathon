"""Local audio -> faster-whisper -> Ollama -> validated JSON."""
import argparse
import json
import logging
import os
import re
import sqlite3
from pathlib import Path
import sys
import tempfile
import threading
from typing import Literal

import httpx
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
import places
from bc_intent import BCIntent, CandidateContext, extract as extract_bc
from search_scope import resolve_scope, without_scope
from opencc import OpenCC

ROOT = Path(__file__).resolve().parent
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
MAX_BYTES = 25 * 1024 * 1024
MAX_SECONDS = 300
DEFAULT_INSTRUCTION = "請用繁體中文摘要這段語音，並回應說話者的問題或請求。沒有問題時，簡短確認內容。"
logger = logging.getLogger(__name__)
lock = threading.Lock()
whisper = None
traditional = OpenCC('s2t')


class PipelineError(Exception):
    def __init__(self, code, message, status=422):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


class ModelReply(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    summary: str = Field(min_length=1, description="A concise summary of the transcript")
    reply: str = Field(min_length=1, description="An answer to the speaker's question or request")


def analyze_text(transcript, instruction=DEFAULT_INSTRUCTION):
    schema = ModelReply.model_json_schema()
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "format": schema,
        "options": {"temperature": 0, "num_predict": 700, "num_ctx": 8192},
        "messages": [
            {"role": "system", "content": (
                "你是語音助理。依照使用者指定任務處理語音逐字稿。"
                "只回傳符合 JSON schema 的物件，summary 為摘要，reply 為回答。"
                "不要聲稱已執行外部操作，不要編造逐字稿未提供的事實。\n"
                + json.dumps(schema, ensure_ascii=False)
            )},
            {"role": "user", "content": json.dumps(
                {"task": instruction, "transcript": transcript}, ensure_ascii=False
            )},
        ],
    }
    return call_model(payload, ModelReply)


def call_model(payload, result_type):
    try:
        response = httpx.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=180,
                              trust_env=False)
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise PipelineError("ollama_timeout", "Ollama 回覆逾時，請稍後重試。", 504) from exc
    except httpx.HTTPStatusError as exc:
        raise PipelineError("ollama_error", f"Ollama 回傳 HTTP {exc.response.status_code}；請確認模型 {OLLAMA_MODEL} 已安裝。", 502) from exc
    except httpx.RequestError as exc:
        raise PipelineError("ollama_unavailable", f"無法連線 {OLLAMA_URL}，請啟動 ollama serve。", 503) from exc
    try:
        data = response.json()
        if data.get("done_reason") == "length":
            raise ValueError("Output truncated")
        return result_type.model_validate_json(data["message"]["content"])
    except (ValueError, KeyError, TypeError, ValidationError) as exc:
        raise PipelineError("invalid_model_json", "模型未產生完整且符合欄位規範的 JSON，請重試。", 502) from exc


class SearchIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: Literal['search', 'chat']
    category: Literal['rest','park','cafe','food','toilet','convenience','fuel','medical','attraction','lodging','parking','water','all']
    place_name: str = Field(description="Specific place name explicitly in the input, otherwise empty string")
    outside_taiwan: bool


class TextRequest(CandidateContext):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=6000)
    instruction: str = Field(default=DEFAULT_INSTRUCTION, min_length=1, max_length=2000)
    radius_km: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    limit: int = Field(default=5, ge=1, le=20)

    @model_validator(mode='after')
    def coordinates_together(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError('latitude 和 longitude 必須一起提供')
        if not self.text.strip():
            raise ValueError('text 不可全為空白')
        return self


class PlaceReply(BaseModel):
    places: list[dict]
    reply: str
    bc_to_d: BCIntent


def interpret_query(text):
    schema = SearchIntent.model_json_schema()
    return call_model({
        'model': OLLAMA_MODEL, 'stream': False, 'format': schema,
        'options': {'temperature':0, 'num_predict':250, 'num_ctx':4096},
        'messages': [
            {'role':'system','content': (
                'Extract search intent; never invent places. search means finding a physical place; otherwise chat. '
                'Categories: rest=休息/坐下/座椅, park=公園, cafe=咖啡, food=吃飯/餐廳, toilet=廁所, '
                'convenience=便利商店, fuel=加油, medical=醫院/藥局, attraction=景點, lodging=住宿, '
                'parking=停車, water=飲用水, all=specific place name or other category. '
                'place_name: copy a specific business or landmark name from the input, or empty string. '
                'Do not put generic category words or township names in place_name. '
                'outside_taiwan=true ONLY if the user explicitly requests a location outside Taiwan (including Penghu, Kinmen and Lienchiang). '
                'All Taiwan counties and cities are supported. '
                'Examples: 找一個休息地點 -> search/rest/empty/false; 找廁所 -> search/toilet/empty/false; '
                '你好 -> chat/all/empty/false. JSON schema: ' + json.dumps(schema,ensure_ascii=False))},
            {'role':'user','content':text},
        ],
    }, SearchIntent)


def respond(text, instruction=DEFAULT_INSTRUCTION, latitude=None, longitude=None, limit=5, radius_km=None, context=None):
    try:
        resolve_scope(traditional.convert(text),traditional.convert(instruction),latitude,longitude,radius_km)
    except ValueError as exc:
        raise PipelineError('invalid_search_scope',str(exc)) from exc
    parsed = interpret_query(without_scope(traditional.convert(text)))
    bc, clarification = extract_bc(text,parsed.action,parsed.category,context)
    if clarification:
        result = {'places':[], 'reply':clarification}
    elif bc.reference:
        result = {'places':[], 'reply':'已抽取指定候選的操作與條件，交由 D 模組處理；此服務未修改任務狀態。'}
    elif bc.conditions.model_dump(exclude_none=True):
        # BC emits constraints. D owns state and constraint evaluation; never claim
        # that straight-line OSM distances are driving distances.
        result = {'places':[], 'reply':'已抽取搜尋條件，交由 D 模組篩選地點。室內、座位與實際行駛距離尚未由此服務驗證。'}
    else:
        result = respond_places(text,instruction,latitude,longitude,limit,radius_km,parsed)
    result['bc_to_d'] = bc.model_dump(exclude_none=True)
    return result


def respond_places(text, instruction=DEFAULT_INSTRUCTION, latitude=None, longitude=None, limit=5, radius_km=None, parsed=None):
    text = traditional.convert(text)
    try:
        latitude,longitude,radius_km = resolve_scope(text,traditional.convert(instruction),latitude,longitude,radius_km)
    except ValueError as exc:
        raise PipelineError('invalid_search_scope',str(exc)) from exc
    text = without_scope(text)
    intent = parsed or interpret_query(text)
    normalized = text.replace('台','臺')
    if intent.action == 'chat':
        return {'places':[], 'reply':analyze_text(text,instruction).reply}
    try:
        counties, district, clarification = places.resolve_regions(normalized)
    except (OSError, sqlite3.Error) as exc:
        raise PipelineError('places_unavailable','本機臺灣地點資料庫尚未建立或無法讀取。',503) from exc
    if clarification:
        return {'places':[], 'reply':clarification}
    if intent.outside_taiwan and not counties:
        return {'places':[], 'reply':'目前安裝臺灣的離線地點資料，無法查詢國外地點。'}
    # Small models sometimes copy the whole request as place_name. Remove search
    # grammar/category words, while keeping unknown proper names (no false fallback).
    keyword = traditional.convert(intent.place_name.strip())
    if keyword and keyword not in text:
        keyword = ''
    keyword = keyword.replace('台','臺')
    if keyword and (keyword.replace('台','臺') in district or keyword.replace('台','臺') in {*counties, *(c[:-1] for c in counties), '臺灣'}):
        keyword = ''
    if keyword:
        keyword = re.sub(r'^(請問|請|幫我|替我|我想要|我想|我要|我|想要|想|找出|尋找|找|推薦|給我|一個|一間|一家|一處|附近|最近|有沒有|哪裡有|可以|能)+', '', keyword)
        generic = {
            'rest': ('可以坐下','坐一下','坐下','休息地點','休息區','休息','座椅','長椅','座位'),
            'park': ('公園',), 'cafe': ('咖啡店','咖啡廳','咖啡館','咖啡'),
            'food': ('餐廳','餐館','餐飲','吃飯'), 'toilet': ('公共廁所','廁所','洗手間'),
            'convenience': ('便利商店','超商'), 'fuel': ('加油站','加油'),
            'medical': ('醫院','診所','藥局'), 'attraction': ('景點',),
            'lodging': ('住宿','旅館','飯店'), 'parking': ('停車場','停車'),
            'water': ('飲水機','飲用水','飲水'), 'all': (),
        }
        for word in (*generic[intent.category],district,district[:-1],*counties,*(c[:-1] for c in counties),'臺灣','台灣','的地點','地點','地方'):
            if word: keyword = keyword.replace(word,'')
        keyword = keyword.strip(' 的？?。，,.!！')
    try:
        exact_name = places.explicit_name(text)
        if exact_name:
            keyword = exact_name
            intent.category = 'all'
        if intent.category == 'all' and not keyword:
            return {'places':[], 'reply':'請指定地點名稱或類別，例如「找休息地點」、「虎尾的咖啡店」或「找廁所」。'}
        return places.answer(intent.category,keyword,district,latitude,longitude,limit,radius_km,counties)
    except (OSError, sqlite3.Error) as exc:
        raise PipelineError('places_unavailable','本機地點資料庫尚未建立或無法讀取。',503) from exc


def process_audio(path, language="auto", instruction=DEFAULT_INSTRUCTION,
                  latitude=None, longitude=None, limit=5, radius_km=None, context=None):
    global whisper
    if not instruction.strip() or len(instruction) > 2000:
        raise PipelineError("invalid_instruction", "任務指令需為 1–2000 字。")
    path = Path(path)
    if not path.is_file():
        raise PipelineError("file_not_found", "找不到音訊檔案。")
    if path.stat().st_size == 0:
        raise PipelineError("empty_file", "音訊檔案是空的。")
    if path.stat().st_size > MAX_BYTES:
        raise PipelineError("file_too_large", "檔案上限為 25 MiB。", 413)
    from faster_whisper import WhisperModel
    from faster_whisper.tokenizer import _LANGUAGE_CODES
    if language != "auto" and language not in _LANGUAGE_CODES:
        raise PipelineError("invalid_language", "請使用 auto、zh、en、ja 等支援的語言代碼。")
    if not lock.acquire(blocking=False):
        raise PipelineError("busy", "目前正在處理另一段音訊，請稍後重試。", 429)
    try:
        # Decode in bounded chunks so a highly compressed long file cannot use unlimited RAM.
        import av
        import numpy as np
        chunks = []
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
        with av.open(str(path)) as container:
            stream = next((s for s in container.streams if s.type == "audio"), None)
            if stream is None:
                raise PipelineError("invalid_audio", "檔案沒有音軌。")
            duration = 0.0
            for frame in container.decode(stream):
                duration += frame.samples / frame.sample_rate
                if duration > MAX_SECONDS:
                    raise PipelineError("audio_too_long", "此版本每段音訊上限為 5 分鐘。", 413)
                frame.pts = None
                chunks.extend(output.to_ndarray().flatten() for output in resampler.resample(frame))
            chunks.extend(output.to_ndarray().flatten() for output in resampler.resample(None))
        audio = np.concatenate(chunks).astype(np.float32) / 32768.0 if chunks else np.array([], dtype=np.float32)
        if not len(audio):
            raise PipelineError("empty_audio", "音訊沒有可解碼的內容。")
        if whisper is None:
            try:
                from huggingface_hub.errors import LocalEntryNotFoundError
                settings = dict(device='cpu', compute_type='int8',
                                cpu_threads=min(os.cpu_count() or 4, 8),
                                download_root=str(ROOT / 'models'))
                try:
                    whisper = WhisperModel(WHISPER_MODEL,local_files_only=True,**settings)
                except LocalEntryNotFoundError:
                    whisper = WhisperModel(WHISPER_MODEL,**settings)
            except Exception as exc:
                raise PipelineError("asr_load_failed", "無法載入 Whisper；首次使用需要網路下載模型，請查看伺服器日誌。", 503) from exc
        segments, info = whisper.transcribe(
            audio, language=None if language == "auto" else language,
            vad_filter=True, beam_size=5, condition_on_previous_text=False,
        )
        transcript = " ".join(s.text.strip() for s in segments).strip()
        if not transcript:
            raise PipelineError("no_speech", "未辨識到語音，請提供有清楚人聲的音訊。")
        if len(transcript) > 6000:
            raise PipelineError("transcript_too_long", "辨識文字超過 6000 字，請分段提交音訊。", 413)
        return respond(transcript,instruction,latitude,longitude,limit,radius_km,context)
    except PipelineError:
        raise
    except (av.error.FFmpegError, ValueError, EOFError) as exc:
        raise PipelineError("invalid_audio", "無法解碼音訊，請使用有效的 WAV、MP3、M4A、FLAC 或 WebM 檔。") from exc
    finally:
        lock.release()


def error_json(exc):
    return {"ok": False, "error": {"code": exc.code, "message": exc.message}}


app = FastAPI(title="臺灣離線地點搜尋", description="音訊或文字 → 本機 llama3.2:1b → 臺灣 SQLite。回應包含 places（地點）、reply（回覆）與 bc_to_d（意圖條件）。地圖資料 © OpenStreetMap contributors，ODbL 1.0；資料日期見 /api/places/info。")


@app.exception_handler(PipelineError)
async def pipeline_error_handler(request, exc):
    return JSONResponse(error_json(exc), status_code=exc.status)


@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse("/docs")


@app.post('/api/intent', response_model=BCIntent, response_model_exclude_none=True)
def intent_endpoint(request: TextRequest):
    """只回傳 BC → D 合約，不查詢地圖或修改 D 的任務狀態。"""
    parsed = interpret_query(traditional.convert(request.text))
    result, clarification = extract_bc(request.text,parsed.action,parsed.category,request)
    if clarification:
        raise PipelineError('clarification_needed',clarification)
    return result


@app.post('/api/text', response_model=PlaceReply, response_model_exclude_none=True)
def text_endpoint(request: TextRequest):
    """輸入「找一個休息地點」。座標選填；未提供時不宣稱最近。"""
    return respond(request.text,request.instruction,request.latitude,request.longitude,request.limit,request.radius_km,request)


@app.get('/api/places/info')
def places_info():
    """查看地點數量、資料日期、來源及授權。此介面不連線外部地圖服務。"""
    try:
        return places.metadata()
    except (OSError, sqlite3.Error) as exc:
        raise PipelineError('places_unavailable','本機地點資料庫無法讀取。',503) from exc


@app.post("/api/audio", response_model=PlaceReply, response_model_exclude_none=True)
def audio_endpoint(file: UploadFile = File(...), language: str = Form("auto"),
                   instruction: str = Form(DEFAULT_INSTRUCTION),
                   latitude: float | None = Form(None, ge=-90,le=90),
                   longitude: float | None = Form(None, ge=-180,le=180),
                   radius_km: float | None = Form(None,gt=0,allow_inf_nan=False,description='搜尋半徑（公里），例如 5；也可寫在 instruction 中'),
                   limit: int = Form(5,ge=1,le=20),
                   context_json: str = Form('{}',max_length=10000,description='上位機的 JSON：reference_type、candidate_ids；或完整 reference；可設定 short_drive_distance_m')):
    """展開後按 Try it out → 選擇檔案 → Execute。首次執行會下載 Whisper。"""
    try:
        try:
            context = CandidateContext.model_validate_json(context_json)
        except ValidationError as exc:
            raise PipelineError('invalid_context','context_json 格式錯誤，請檢查 reference.type 與候選清單。') from exc
        if (latitude is None) != (longitude is None):
            raise PipelineError('invalid_coordinates','latitude 和 longitude 必須一起提供。')
        with tempfile.TemporaryDirectory(prefix="ollama-audio-") as directory:
            path = Path(directory) / "upload.audio"
            size = 0
            with path.open("wb") as output:
                while chunk := file.file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise PipelineError("file_too_large", "檔案上限為 25 MiB。", 413)
                    output.write(chunk)
            return process_audio(path, language, instruction,latitude,longitude,limit,radius_km,context)
    except PipelineError:
        raise
    except Exception as exc:
        logger.exception("Audio processing failed")
        raise PipelineError("processing_failed", "處理失敗，請查看伺服器日誌。", 500) from exc
    finally:
        file.file.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", nargs="?", help="音訊檔案路徑")
    parser.add_argument("--language", default="auto", help="auto / zh / en / ja …")
    parser.add_argument("--instruction", default=DEFAULT_INSTRUCTION)
    parser.add_argument("--serve", action="store_true", help="啟動本機 API 與上傳測試頁")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument('--text', help='不錄音，直接輸入地點搜尋需求')
    parser.add_argument('--latitude',type=float)
    parser.add_argument('--longitude',type=float)
    parser.add_argument('--radius-km',type=float)
    parser.add_argument('--limit',type=int,default=5)
    parser.add_argument('--context-json',default='{}',help='上位機提供的 reference/candidate_ids JSON')
    args = parser.parse_args()
    if args.serve:
        import uvicorn
        uvicorn.run(app, host="127.0.0.1", port=args.port)
        return
    if not args.audio and not args.text:
        parser.error("請指定音訊檔案、--text 或 --serve")
    try:
        context = CandidateContext.model_validate_json(args.context_json)
        request = TextRequest(**context.model_dump(),text=args.text or 'audio',instruction=args.instruction,latitude=args.latitude,longitude=args.longitude,limit=args.limit,radius_km=args.radius_km)
    except ValidationError as exc:
        parser.error(str(exc))
    try:
        result = (respond(args.text,args.instruction,request.latitude,request.longitude,request.limit,request.radius_km,request) if args.text
                  else process_audio(args.audio,args.language,args.instruction,request.latitude,request.longitude,request.limit,request.radius_km,request))
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except PipelineError as exc:
        print(json.dumps(error_json(exc), ensure_ascii=False, indent=2))
        sys.exit(1)
    except Exception:
        logger.exception("Audio processing failed")
        print(json.dumps(error_json(PipelineError("processing_failed", "處理失敗，請查看 stderr。")), ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
