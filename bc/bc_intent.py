"""BC -> D contract. Conditions are sparse; references require caller-owned context."""
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from opencc import OpenCC

traditional = OpenCC('s2t')

class Conditions(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    indoor: bool | None = None
    has_seating: bool | None = None
    max_drive_distance_m: int | None = Field(default=None,ge=0,le=100000)

class Reference(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    type: str = Field(min_length=1,max_length=64,pattern=r'^[A-Za-z][A-Za-z0-9_-]*$')
    target_candidate_id: str = Field(min_length=1,max_length=128,pattern=r'^\S+$')

class BCIntent(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    intent: Literal['search_rest_stop','search_place','chat','clarify']
    conditions: Conditions
    reference: Reference | None = None
    raw_text: str
    latitude: float | None = Field(default=None,ge=-90,le=90,allow_inf_nan=False)
    longitude: float | None = Field(default=None,ge=-180,le=180,allow_inf_nan=False)
    type: str | None = Field(default=None,min_length=1,max_length=64,pattern=r'^[A-Za-z][A-Za-z0-9_-]*$')

class CandidateContext(BaseModel):
    model_config = ConfigDict(extra='forbid')
    candidate_ids: list[str] = Field(default_factory=list,max_length=20)
    short_drive_distance_m: int = Field(default=300,ge=1,le=100000,strict=True)

    reference_type: str | None = Field(default=None,min_length=1,max_length=64,pattern=r'^[A-Za-z][A-Za-z0-9_-]*$')
    reference: Reference | None = None

    @model_validator(mode='after')
    def validate_ids(self):
        if any(not x.strip() or len(x)>128 for x in self.candidate_ids) or len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ValueError('candidate_ids 必須是互不重複、非空白且不超過 128 字的 ID。')
        if self.reference and self.reference_type and self.reference.type != self.reference_type:
            raise ValueError('reference.type 與 reference_type 不一致。')
        return self

DIGITS = dict(zip('零一二三四五六七八九',range(10)))
DIGITS['兩'] = 2

def integer(text):
    if text.isdigit(): return int(text)
    total = current = 0
    for c in text:
        if c in DIGITS: current = DIGITS[c]
        elif c in {'十','百','千'}:
            total += (current or 1)*{'十':10,'百':100,'千':1000}[c]
            current = 0
        else: raise ValueError('不支援的中文數字')
    return total+current


def extract_conditions(text, short_drive_distance_m=300):
    text=traditional.convert(text)
    result={}
    neutral = re.sub(r'(?:不一定要|不需要|不要求|不限制|不限|無所謂)(?:有)?(?:室內|室外|戶外|座位|座椅)', '',text)
    neutral=re.sub(r'(?:不要|不想要|排除|別找)(?:室外|戶外)','室內',neutral)
    for key, positive,negative in [
        ('indoor',r'室內|屋內',r'(?:不要|不想要|非|排除|別找)(?:的)?(?:室內|屋內)|室外|戶外'),
        ('has_seating',r'有(?:個|地方)?(?:座位|座椅|椅子)|能坐|可以坐|坐下|坐一下',r'(?:不要有|沒有|無|不要|排除)(?:座位|座椅|椅子)'),
    ]:
        negatives=list(re.finditer(negative,neutral))
        remaining=re.sub(negative,'',neutral)
        yes=bool(re.search(positive,remaining))
        if yes and negatives: raise ValueError('條件同時包含肯定與否定，請說明要室內／室外或是否需要座位。')
        if yes: result[key]=True
        elif negatives: result[key]=False
    # Only driving clauses define driving distance; radius/coordinate instructions stay separate.
    driving=re.findall(r'(?:駕車|開車|行駛|車程)[^，。；;!?！？\n]{0,45}',text)
    distances=[]
    for clause in driving:
        for value,unit in re.findall(r'(\d+(?:\.\d+)?|[零一二兩三四五六七八九十百千]+)\s*(公里|千米|公尺|米|km|m)',clause,re.I):
            amount=float(value) if re.fullmatch(r'\d+(?:\.\d+)?',value) else integer(value)
            metres=amount*(1000 if unit.lower() in {'公里','千米','km'} else 1)
            if isinstance(metres,float) and not metres.is_integer():
                raise ValueError('行駛距離請以整數公尺表示。')
            distances.append(int(metres))
    if len(set(distances))>1: raise ValueError('找到多個行駛距離，請指定一個上限。')
    if distances: result['max_drive_distance_m']=distances[0]
    elif re.search(r'不用開太遠|不要開太遠|不想開太遠|少開一點|開近一點',text):
        result['max_drive_distance_m']=short_drive_distance_m
    return Conditions.model_validate(result)


def extract(raw_text, action, category, context=None):
    text=traditional.convert(raw_text)
    context=context or CandidateContext()
    clarification=None
    try: conditions=extract_conditions(text,context.short_drive_distance_m)
    except ValueError as exc:
        conditions=Conditions()
        clarification=str(exc)
    reference=context.reference
    ordinal=re.search(r'第\s*([0-9零一二兩三四五六七八九十百]+)\s*(?:個|筆|項|家|間)',text)
    explicit=re.search(r'(?<![A-Za-z0-9_])(loc_[A-Za-z0-9_-]+)(?![A-Za-z0-9_])',text)
    modifying=bool(re.search(r'修改|改成|改為|留下|保留|選擇|選|換成|第二|第[一三四五六七八九十0-9]',text))
    if reference is None and (ordinal or explicit):
        target=None
        if explicit: target=explicit.group(1)
        elif ordinal:
            index=integer(ordinal.group(1))-1
            if 0<=index<len(context.candidate_ids): target=context.candidate_ids[index]
        if target and target in context.candidate_ids and context.reference_type:
            reference=Reference(type=context.reference_type,target_candidate_id=target)
        elif target and target in context.candidate_ids:
            clarification='請由上位機提供 reference_type；程式不會自行判斷操作 type。'
        else:
            clarification='無法對應指定候選，請由 D 傳入上一輪依顯示順序排列的 candidate_ids。'
    elif reference is None and re.search(r'那個|這個|上一個|剛才那個',text) and modifying:
        clarification='請指定第幾個候選，並提供上一輪 candidate_ids。'
    rest=category=='rest' or bool(re.search(r'休息|座位|座椅|坐下|坐一下',text)) or reference is not None
    intent='search_rest_stop' if rest else ('search_place' if action=='search' else 'chat')
    if clarification: intent='clarify'
    return BCIntent(intent=intent,conditions=conditions,reference=reference,raw_text=raw_text),clarification
