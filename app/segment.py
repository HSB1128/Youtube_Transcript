from typing import List, Dict, Any
import re

# 한국어/영어 문장 끝 느낌을 잡기 위한 간단 패턴
_END_PUNCT_RE = re.compile(r"[.!?…]+$")

# 한국어 종결어미(완벽하진 않지만 체감 도움)
_KO_ENDING_RE = re.compile(r"(니다|어요|예요|죠|다)\s*$")

def make_natural_segments(
    segs: List[Dict[str, Any]],
    pause_gap_sec: float = 0.7,   # 세그먼트 사이 갭(침묵/호흡) 기준
    max_span_sec: float = 10.0,   # 한 덩어리 최대 시간
    max_chars: int = 240,         # 한 덩어리 최대 글자수
) -> List[Dict[str, Any]]:
    """
    입력: [{start, duration, text}, ...]
    출력: 자연스러운 단위(문장/문단)에 가까운 세그먼트 묶음 리스트

    끊는 기준(대략):
    1) 시간 갭(pause_gap_sec) 이상이면 문단 분리
    2) 누적 길이가 max_span_sec 넘으면 분리
    3) 누적 글자수가 max_chars 넘으면 분리
    4) 문장 끝(.,?!… 또는 한국어 종결어미) 느낌이면 분리 후보 강화
       - 단, 바로 다음이 이어지는 경우도 있어서 "후보"로만 쓰고,
         실제 분리는 위의 강제 조건 + 후보 조건을 조합해 발생
    """
    if not segs:
        return []

    out: List[Dict[str, Any]] = []
    cur_start = None
    cur_end = None
    cur_text_parts: List[str] = []

    def flush():
        nonlocal cur_start, cur_end, cur_text_parts
        if cur_start is None:
            return
        text = " ".join([t for t in cur_text_parts if t]).strip()
        if text:
            out.append({
                "start": float(cur_start),
                "duration": float(max(0.0, (cur_end or cur_start) - cur_start)),
                "text": text,
            })
        cur_start = None
        cur_end = None
        cur_text_parts = []

    def is_sentence_end(text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return False
        if _END_PUNCT_RE.search(t):
            return True
        if _KO_ENDING_RE.search(t):
            return True
        return False

    prev_end = None
    for s in segs:
        st = float(s.get("start", 0.0))
        dur = float(s.get("duration", 0.0))
        ed = st + max(0.0, dur)
        tx = (s.get("text") or "").strip()
        if not tx:
            continue

        # 세그먼트 사이 갭(침묵/호흡) 감지
        gap = None
        if prev_end is not None:
            gap = st - prev_end

        if cur_start is None:
            cur_start = st
            cur_end = ed
            cur_text_parts = [tx]
            prev_end = ed
            continue

        # 강제 분리 조건: 갭이 크면 바로 끊기
        if gap is not None and gap >= pause_gap_sec:
            flush()
            cur_start = st
            cur_end = ed
            cur_text_parts = [tx]
            prev_end = ed
            continue

        # 누적 후 추가했을 때 span/chars 계산
        span_if_add = ed - cur_start
        chars_if_add = len(" ".join(cur_text_parts)) + 1 + len(tx)

        # 강제 분리 조건: 너무 길어지면 끊기
        if span_if_add >= max_span_sec or chars_if_add >= max_chars:
            flush()
            cur_start = st
            cur_end = ed
            cur_text_parts = [tx]
            prev_end = ed
            continue

        # 이어붙이기
        cur_end = ed
        cur_text_parts.append(tx)
        prev_end = ed

        # 문장 끝이면 "여기서 끊어도 자연스럽다" 후보
        # 다만 너무 짧게 쪼개지는 걸 막기 위해 최소 span 3초 정도일 때만 끊기
        cur_text = " ".join(cur_text_parts).strip()
        if is_sentence_end(cur_text) and (cur_end - cur_start) >= 3.0:
            flush()

    flush()
    return out

# 하위호환: 기존 코드가 make_scene_segments를 호출할 수 있으니 남겨둠
def make_scene_segments(segs: List[Dict[str, Any]], scene_sec: float = 2.0) -> List[Dict[str, Any]]:
    # 기존 2초 로직 대신 자연 세그먼트로 대체
    # scene_sec는 더 이상 사용하지 않지만, 외부 호출 호환을 위해 인자는 유지
    return make_natural_segments(segs)
