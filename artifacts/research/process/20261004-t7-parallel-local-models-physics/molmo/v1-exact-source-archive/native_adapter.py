"""Fail-closed research bridge for native Molmo image grounding.

No coordinate search/repair, no labels from instructions, no fixed confidence.
A localization result remains distinct from a complete VisualDecision.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import math, numbers, re

class NativeProtocolError(ValueError):
    pass

@dataclass(frozen=True)
class NativePoint:
    image_index: int
    object_id: int
    normalized_1000: tuple[int,int]
    pixel_xy: tuple[float,float] | None = None

_TERMINAL_TOKENS=('<|im_end|>','<|endoftext|>')

def _explicit_absence(raw):
    text=raw.strip()
    for token in _TERMINAL_TOKENS:
        if text.endswith(token):text=text[:-len(token)].strip()
    return text.upper()=='ABSENT'

def parse_molmo2(raw: str, image_count: int):
    """Decode multi-image points: 1-based image ID then object-ID,x,y triples.

    Coordinates are already normalized by 1000. Values are never guessed from
    magnitude. A malformed tag or group rejects the whole native result.
    """
    tags=list(re.finditer(r'<points\b[^>]*\bcoords="([^"]*)"[^>]*>',raw))
    if not tags:
        if _explicit_absence(raw):return []
        raise NativeProtocolError('missing native multi-image points or explicit ABSENT')
    points=[]
    for tag in tags:
        groups=re.split(r'[\t:;,]',tag.group(1))
        for group in groups:
            fields=group.strip().split()
            if not fields or any(not re.fullmatch(r'\d+',x) for x in fields):
                raise NativeProtocolError('malformed native image coordinate group')
            ints=list(map(int,fields))
            if len(ints)<4 or (len(ints)-1)%3 or not 1<=ints[0]<=image_count:
                raise NativeProtocolError('invalid native image ID or triple count')
            for offset in range(1,len(ints),3):
                obj,x,y=ints[offset:offset+3]
                if not 0<=x<=1000 or not 0<=y<=1000:
                    raise NativeProtocolError('native normalized coordinate outside [0,1000]')
                points.append(NativePoint(ints[0]-1,obj,(x,y)))
    return points

def convert_molmopoint(decoded_points, image_sizes):
    """Decode official (object_id, zero-based image_index, pixel_x, pixel_y).

    Official model.extract_image_points owns patch/subpatch decoding; this
    function only validates its pixel output and converts with round-half-up.
    """
    points=[]
    for row in decoded_points:
        if len(row)!=4:raise NativeProtocolError('native decoder row must contain four fields')
        obj,image,x,y=row
        if any(isinstance(v,bool) or not isinstance(v,numbers.Integral) for v in (obj,image)):
            raise NativeProtocolError('native object and image IDs must be integers')
        if not 0<=image<len(image_sizes):raise NativeProtocolError('native image index unavailable')
        width,height=image_sizes[image]
        if width<=0 or height<=0:raise NativeProtocolError('image dimensions must be positive')
        if any(isinstance(v,bool) or not isinstance(v,numbers.Real) or not math.isfinite(v) for v in (x,y)):
            raise NativeProtocolError('native coordinate must be finite numeric pixels')
        if not 0<=x<=width or not 0<=y<=height:raise NativeProtocolError('native pixel outside source image')
        normalized=(math.floor(float(x)*1000/width+0.5),math.floor(float(y)*1000/height+0.5))
        points.append(NativePoint(int(image),int(obj),normalized,(float(x),float(y))))
    return points

def localization_result(raw_text: str, points: list[NativePoint], raw_token_ids):
    """Select only a unique RGB point; preserve failure modes and all evidence."""
    rgb=[p for p in points if p.image_index==0]
    explicit_absence=_explicit_absence(raw_text)
    contradictory_absence=bool(re.search(r'\bABSENT\b',raw_text,re.IGNORECASE)) and bool(points)
    status=('invalid' if contradictory_absence else
            'absent' if explicit_absence else
            'ambiguous' if len(rgb)>1 else
            'localized' if len(rgb)==1 else 'unavailable')
    return {'status':status,'point':list(rgb[0].normalized_1000) if status=='localized' else None,
            'raw_text':raw_text,'raw_token_ids':list(raw_token_ids),
            'native_points':[asdict(p) for p in points],
            'confidence':None,'confidence_source':None,'coordinate_system':'normalized_1000'}

def build_visual_decision(target, destination, evidence):
    """An optional gate: accept only model-emitted label, presence, confidence,
    scene description AND skills. Native localization alone cannot pass it.
    """
    required={'target_label','target_present','destination_present','reported_confidence','observed_scene','skills'}
    if not isinstance(evidence,dict) or set(evidence)!=required:
        raise NativeProtocolError('complete model evidence is missing or has extra fields')
    label,scene,conf=evidence['target_label'],evidence['observed_scene'],evidence['reported_confidence']
    if not isinstance(label,str) or not 1<=len(label)<=100 or not isinstance(scene,str) or not 1<=len(scene)<=500:
        raise NativeProtocolError('model label or scene evidence invalid')
    if isinstance(conf,bool) or not isinstance(conf,(int,float)) or not math.isfinite(conf) or not 0<=conf<=1:
        raise NativeProtocolError('model self-reported confidence unavailable or invalid')
    if type(evidence['target_present']) is not bool or type(evidence['destination_present']) is not bool:
        raise NativeProtocolError('presence evidence must be model booleans')
    for result,key in ((target,'target_present'),(destination,'destination_present')):
        if result['status']=='absent' and evidence[key] or result['status']=='localized' and not evidence[key]:
            raise NativeProtocolError('presence evidence contradicts native result')
    skills=evidence['skills']
    expected=['HOME','MOVE_ABOVE','APPROACH','GRASP','LIFT','MOVE_TO_REGION','PLACE','RELEASE','RETREAT','HOME']
    positive=target['status']=='localized' and destination['status']=='localized'
    if (positive and skills!=expected) or (not positive and skills!=[]):
        raise NativeProtocolError('model skill plan is missing or unsafe for localization status')
    return {'target_pixel':target['point'] if positive else None,
            'destination_pixel':destination['point'] if positive else None,
            'target_label':label,'reported_confidence':conf,'skills':skills,'reason':scene}

def task_metrics(calls,task_latency_s):
    """Aggregate every native/evidence call; Torch allocator peaks are distinct
    from driver/device-wide VRAM. Load time is reported separately.
    """
    return {'task_latency_s':task_latency_s,
            'model_inference_total_s':sum(c['inference_s'] for c in calls),
            'call_latency_total_s':sum(c['latency_s'] for c in calls),
            'model_call_count':len(calls),
            'input_tokens_total':sum(c['input_token_count'] for c in calls),
            'output_tokens_total':sum(c['output_token_count'] for c in calls),
            'peak_torch_allocated_bytes':max((c['max_memory_allocated_bytes'] for c in calls),default=0),
            'peak_torch_reserved_bytes':max((c['max_memory_reserved_bytes'] for c in calls),default=0)}
