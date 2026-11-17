# 게임 페이지의 문장을 음성 파일(mp3)로 미리 만들어요.
#   한국어: SunHi (여성)   영어 문장과 글자 이름: Jenny
# 실행: python -I make_voice.py  (인터넷이 필요해요. 한 번 만들면 다시 만들 필요 없어요)
# 결과: voice/ko/*.mp3, voice/en/*.mp3, voice/manifest.js
# 문장이 바뀌면 다시 실행하면 새로 생긴 문장만 만들어요.

import asyncio
import hashlib
import json
import pathlib
import re
import sys

import edge_tts

HERE = pathlib.Path(__file__).resolve().parent
PAGE = HERE.parent / "index.html"
OLD_PAGE = HERE.parent / "수업용 영타게임.html"  # 콤보 효과음을 꺼낼 때만 써요
ESCAPE_PAGE = HERE.parent / "keyboard_escape_game.html"  # 키보드 탈출 게임 (말하는 문장을 따로 모아요)

KO_VOICE = "ko-KR-SunHiNeural"
EN_VOICE = "en-US-JennyNeural"
CONCURRENCY = 8

sys.stdout.reconfigure(encoding="utf-8")


def collect(html):
    script = html[html.index("<script>"):]
    # 영어 문장 목록
    sent_block = re.search(r"var SENT = \[(.*?)\];", script, re.S).group(1)
    sents = re.findall(r'"([^"]*)"', sent_block)
    # 영어 글자 이름과 기호 이름
    en_names = []
    for name in ("LET_EN", "NAMES_EN"):
        block = re.search(r"var %s = \{(.*?)\};" % name, script, re.S).group(1)
        # "키": "영어 이름" 에서 이름(값)만 가져와요
        en_names += re.findall(r':\s*"([^"]*)"', block)
    # 한국어 문장: 따옴표 안에 한글이 들어 있는 모든 문자열
    ko_lits = [s for s in re.findall(r'"([^"\n]*)"', script) if re.search(r"[가-힣]", s)]
    # 점수와 콤보 번호는 조각으로 말해요: "150점", "5번째"
    numbers = ["%d점" % n for n in range(0, 3001, 10)] + ["%d번째" % n for n in range(1, 101)]
    # 코드에서 조합해서 말하는 낱말과 짧은 문장 (띄어쓰기, 대문자, 기호 이름 등)
    extra = ["띄어쓰기", "대문자", "대문자,", "스페이스", "점", "쉼표", "느낌표", "물음표",
             "작은따옴표", "정답은", "열 글자!", "지웠어요.", "맨 앞이에요.", "맨 끝이에요.",
             "아직 친 글자가 없어요.", "문장을 다 친 뒤에 엔터를 누르세요.", "시간 보너스",
             "현재", "이에요.", "지금 점수는", "지금", "콤보에요!", "콤보!", "다음 문장이에요.",
             "엔터를 누르면 다음 문장이에요.", "지금까지 친 글자예요.", "단축키 안내예요.",
             "입니다.", "문장을 다 쳤어요.", "다음은", "먼저 문장을 쳐 보세요.", "1번", "2번", "3번", "4번", "일번", "이번", "삼번", "사번",
             "점수판 주소가 아직 없어요.", "이름을 입력해 주세요.", "점수를 저장하고 있어요.",
             "저장하지 못했어요. 인터넷과 점수판 주소를 확인해 주세요.", "점수판을 불러오지 못했어요.",
             "아직 저장된 점수가 없어요.", "님,", "을 저장했어요.", "점을 저장했어요.",
             "더 빨라질 수 없어요.", "더 느려질 수 없어요.", "먼저 문장을 쳐 보세요.",
             "상위 1명을 읽어 드릴게요.", "상위 2명을 읽어 드릴게요.", "상위 3명을 읽어 드릴게요.",
             "상위 4명을 읽어 드릴게요.", "상위 5명을 읽어 드릴게요.", "상위 6명을 읽어 드릴게요.",
             "상위 7명을 읽어 드릴게요.", "상위 8명을 읽어 드릴게요.", "상위 9명을 읽어 드릴게요.",
             "상위 10명을 읽어 드릴게요.",
             "1등", "2등", "3등", "4등", "5등", "6등", "7등", "8등", "9등", "10등", "시간 보너스는 없어요.", "지금은 콤보가 없어요.",
             "틀린 글자가 있어서 콤보가 끊겼어요.", "영어 시작하기", "한글 시작하기",
             "엔터를 누르면 시작합니다.", "한글 시작은 아직 준비 중이에요. 영어 시작하기를 골라 주세요."]
    # 한글 문장을 띄어쓰기로 나눈 단어들 (딩동댕 뒤에 단어를 읽으려고)
    words = []
    ks = re.search(r"var KSENT = \[(.*?)\];", script, re.S)
    if ks:
        for sent in re.findall(r'"([^"]*)"', ks.group(1)):
            for w in sent.split(" "):
                if w:
                    words.append(w)
                    if w.endswith("."):
                        words.append(w[:-1])
    # 점수판 상위 50명을 읽을 때 쓰는 문장과 등수
    board = ["상위 %d명을 읽어 드릴게요." % n for n in range(1, 51)] + ["%d등" % n for n in range(1, 51)]
    ko_all = sorted(set(ko_lits + numbers + extra + words + board + ["정답은"]))
    # 고칠 것 메뉴 안내: "이번이 맞았어요", "이번은 틀렸어요", "삼 버전을 열었어요" 같은 한 덩어리 문장
    menu_names = ["일번", "이번", "삼번", "사번"]
    knum = ["일", "이", "삼", "사", "오", "육", "칠", "팔"]
    menu = [n + "이 맞았어요." for n in menu_names] + [n + "은 틀렸어요." for n in menu_names]
    menu += [k + " 버전을 열었어요." for k in knum] + [k + " 버전으로 돌아왔어요." for k in knum]
    ko_all = sorted(set(ko_all + menu))
    combo = ["콤보! %d번째 콤보에요!" % n for n in range(1, 101)]
    ko_all = sorted(set(ko_all + combo))
    # 마침표로 끝나는 문장은 마침표 앞까지도 따로 만들어요 (끝에 "쩜!"을 붙여 읽으려고)
    # 아이템 퀴즈의 영어 단어 (QUIZ 목록의 en: "...")
    quiz_en = re.findall(r'\ben: "([^"]+)"', script)
    en_all = sorted(set(sents + en_names + quiz_en + [s[:-1] for s in sents if s.endswith(".")]))
    ko_all = sorted(set(ko_all + [s[:-1] for s in ko_all if s.endswith(".")]))
    return ko_all, en_all


# 키보드 탈출 게임은 말하기 전에 영어 약어를 한글 발음으로 바꿔요 (게임의 PRON 과 같은 표)
PRON = {"ESC": "이에스씨", "TAB": "탭", "CAP": "캡스락", "SHI": "시프트", "SHIFT": "시프트", "CTR": "컨트롤", "CTRL": "컨트롤",
        "ALT": "알트", "WIN": "윈도우", "ENT": "엔터", "ENTER": "엔터", "BAC": "백스페이스", "SPACE": "스페이스바",
        "INS": "인서트", "DEL": "딜리트", "HOM": "홈", "END": "엔드", "PGU": "페이지 업", "PGD": "페이지 다운",
        "PRT": "프린트 스크린", "SCR": "스크롤 락", "PAU": "포즈", "NUM": "넘 락", "FN": "에프엔", "APP": "메뉴 키",
        "KEYBOARD": "키보드", "COMPUTER": "컴퓨터", "TYPEWRITER": "타이프라이터", "MONITOR": "모니터"}


def pron_py(text):
    t = re.sub(r"\b[A-Z]{2,}\b", lambda m: PRON.get(m.group(0), m.group(0)), text, flags=re.ASCII)
    t = re.sub(r"[·…]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def skip_early_sessions(html):
    # 1~4회는 이미 끝난 회차라서 음성을 만들지 않아요 (문제 데이터와 미션 데이터의 1~4회 부분을 뺌)
    for start, end in ((r"\{ n: 1,", r"\{ n: 5,"), (r'\n\s*"1": \[', r'\n\s*"5": \['), (r'\n\s*"1": \{', r'\n\s*"5": \{')):
        a = re.search(start, html)
        b = re.search(end, html[a.end():]) if a else None
        if a and b:
            html = html[:a.start()] + html[a.end() + b.start():]
    return html


def collect_escape(html):
    # 게임이 말하는 한글 문장: 큰따옴표와 작은따옴표 안의 한글 문자열 전부
    found = [x for x in re.findall(r'"([^"\n]*)"', html) if re.search(r"[가-힣]", x)]
    found += [x for x in re.findall(r"'([^'\n]*)'", html) if re.search(r"[가-힣]", x)]
    # 버튼 글자처럼 HTML 태그 사이에 있는 한글도 읽어요
    found += [x.strip() for x in re.findall(r">([^<>\n]*[가-힣][^<>\n]*)<", html)]
    return sorted(set(found))


def clue_strings(html):
    # 1~4회 줄거리 중 5회 이후가 "지난 이야기"로 읽는 문장은 남겨요
    return [x for x in re.findall(r'"clue": "([^"]*)"', html) if re.search(r"[가-힣]", x)]


def lesson_extras(html):
    # 수업용 영타게임이 이어 붙여 읽는 문장: 힌트, 상자 결과, 칭호, 화면 버튼 글자
    out = set()
    for en in re.findall(r'en: "([^"]+)"', html):
        out.add("글자는 %d글자예요." % len(en))
        out.add("첫 글자는 %s예요." % en[0])
    for mean in re.findall(r'mean: "([^"]+)"', html):
        out.add("뜻은 %s이에요." % mean)
    for n in range(10, 101, 10):
        out.add("상자에서 %d점이 나왔어요!" % n)
        out.add("상자에서 %d점을 잃었어요." % n)
    for t in ["타자 새싹", "타자 초보", "타자 연습생", "타자 고수", "타자 달인"]:
        out.add("지금 칭호는 %s이에요." % t)
    for t in re.findall(r'>([^<>\n]*[가-힣][^<>\n]*)<', html):
        out.add(t.strip())
    return out


def make_sfx():
    # 콤보 효과음은 예전 파일 안에 base64 로 들어 있어요. mp3 로 꺼내 둬요.
    import base64
    (HERE / "sfx").mkdir(exist_ok=True)
    out = HERE / "sfx" / "combo.mp3"
    if out.exists() and out.stat().st_size > 0:
        return
    text = OLD_PAGE.read_text(encoding="utf-8")
    b64 = re.search(r'var COMBO_B64 = "([^"]+)"', text).group(1)
    out.write_bytes(base64.b64decode(b64))
    print("콤보 효과음 저장:", out.name, out.stat().st_size, "바이트")


def name_for(key, folder):
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return "voice/%s/%s.mp3" % (folder, digest)


async def make_one(sem, text, voice, path):
    if path.exists() and path.stat().st_size > 0:
        return "skip"
    async with sem:
        for attempt in range(3):
            try:
                await edge_tts.Communicate(text, voice).save(str(path))
                # 앞뒤 빈 소리를 잘라서 바로 나오게
                import subprocess, os
                ff = os.path.join(os.environ['LOCALAPPDATA'], 'JY', 'bin', 'ffmpeg.exe')
                flt = ('silenceremove=start_periods=1:start_silence=0.03:start_threshold=-45dB,'
                       'areverse,silenceremove=start_periods=1:start_silence=0.03:start_threshold=-45dB,areverse')
                tmp = path.with_suffix('.trim.mp3')
                subprocess.run([ff, '-y', '-loglevel', 'error', '-i', str(path), '-af', flt, '-c:a', 'libmp3lame', '-q:a', '4', str(tmp)])
                if tmp.exists() and tmp.stat().st_size > 0: tmp.replace(path)
                return "ok"
            except Exception as e:  # 네트워크 일시 오류는 다시 시도해요
                last = e
                await asyncio.sleep(2)
        print("실패:", text, last)
        return "fail"


async def main():
    html = PAGE.read_text(encoding="utf-8")
    ko_all, en_all = collect(html)
    # 키보드 탈출 게임의 문장 (영어타자 페이지와 같은 음성 파일 목록에 넣어요)
    esc_html = ESCAPE_PAGE.read_text(encoding="utf-8") if ESCAPE_PAGE.exists() else ""
    esc_ko = sorted(set(collect_escape(skip_early_sessions(esc_html)) + clue_strings(esc_html)))
    # 옛 5회차 파일의 영어 문장도 같은 음성(Jenny)으로 만들어요
    if OLD_PAGE.exists():
        old_ko, old_en = collect(OLD_PAGE.read_text(encoding="utf-8"))
        old_ko = sorted(set(old_ko) | lesson_extras(OLD_PAGE.read_text(encoding="utf-8")))
        en_all = sorted(set(en_all + old_en))
        ko_all = sorted(set(ko_all + old_ko))
    (HERE / "ko").mkdir(exist_ok=True)
    (HERE / "en").mkdir(exist_ok=True)
    make_sfx()

    manifest = {}
    jobs = []
    sem = asyncio.Semaphore(CONCURRENCY)

    for text in ko_all:
        rel = name_for(text, "ko")
        manifest[text] = rel
        jobs.append(make_one(sem, text, KO_VOICE, HERE.parent / rel))
    # 게임은 문장을 쉼표와 마침표 단위 조각으로 나눠서 읽어요. 조각마다 음성을 만들어요.
    # 게임은 한 자리 수를 한글로 읽어요 (2 -> 이)
    sino_digits = ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]
    def ko_digits(t):
        return re.sub(r"(?<!\d)[1-9](?!\d)", lambda m: sino_digits[int(m.group())], t)
    esc_pieces = set(ko_digits(x) for x in esc_ko)
    for text in esc_ko:
        for piece in re.split(r"[.!?,]\s*", text):
            piece = ko_digits(piece.strip())
            if piece and re.search(r"[가-힣]", piece):
                esc_pieces.add(piece)
    esc_pieces |= {sino_digits[n] + "회" for n in range(1, 10)}
    # 키 이름 (ESC, CAP 같은 영어 약자는 게임이 한글 발음으로 바꿔 읽어요)
    esc_pieces |= set(re.findall(r'"([A-Z]{2,4})"', esc_html))
    # 나만의 캐릭터 만들기가 이어 붙여 읽는 문장
    ords = ["첫 번째", "두 번째", "세 번째", "네 번째", "다섯 번째", "여섯 번째", "일곱 번째", "여덟 번째", "아홉 번째", "열 번째", "열한 번째", "열두 번째"]
    esc_pieces |= {o + " 질문이에요" for o in ords} | {"A", "B"}
    chars = ["산악 탐험가", "숲속 길잡이", "구조대원", "자연 탐사 대원", "우주 조종사", "우주 관측가", "로봇 대회 선수", "로봇 연구팀", "정원사", "식물학자", "동물 보호사", "생태 조사원", "발명가", "과학자", "프로그래머", "데이터 분석가"]
    for n in range(1, 5):
        for num in (str(n), sino_digits[n]):   # 게임은 한 자리 숫자를 한글(일)로 바꿔 읽어요
            esc_pieces.add(num + "번째 친구는 어떤 걸 선택할까요")
            esc_pieces |= {num + "번째 친구는 " + c + "예요" for c in chars}
    # 7회 마법 배틀: 게임이 이어 붙여 읽는 문장 (숫자는 게임처럼 한글로 바꿔요)
    bE = ["물", "불", "전기"]
    bKeys = ["불불", "물물", "전기전기", "불물", "불전기", "물전기"]
    bName = {"불불": "불꽃 화살", "물물": "물대포", "전기전기": "벼락치기", "불물": "힘의 기운", "불전기": "단단한 방패", "물전기": "치유의 물결"}
    bAb = {
        "불불": "보스에게 불 피해 2 (보스 속성이 전기면 2배 피해)",
        "물물": "보스에게 물 피해 2 (보스 속성이 불이면 2배 피해)",
        "전기전기": "보스에게 전기 피해 2 (보스 속성이 물이면 2배 피해)",
        "불물": "내 공격력 +1 (계속 유지)",
        "불전기": "내 방어력 +1 (보스 공격 피해 -1) (계속 유지)",
        "물전기": "내 체력 +4 회복",
    }
    bPair = {"불불": ["불", "불"], "물물": ["물", "물"], "전기전기": ["전기", "전기"], "불물": ["불", "물"], "불전기": ["불", "전기"], "물전기": ["물", "전기"]}
    bOrd = ["일", "이", "삼", "사", "육"]
    bF = ["일번째 친구", "이번째 친구", "삼번째 친구", "사번째 친구"]
    bp = set()
    bp |= {"보스가 나타났어요", "보스 속성은 불이에요", "마법 만들기나 마법 쓰기를 고르세요", "보스가 공격했어요", "보스의 속성이 바뀌었어요",
           "다음 턴에 보스가 공격해요", "보스를 무찔렀어요", "모두 축하해요", "내 체력이 모두 떨어졌어요", "다시 도전해 봐요",
           "보스의 공격 피해가 1 줄었어요", "상성이 맞아서 2배", "공격력이 1 올랐어요", "최대 체력 10이에요",
           "원소를 두 개 고르세요", "두 번째 원소를 고르세요", "고르던 원소를 취소했어요", "원소를 고르세요", "취소했어요",
           "이미 만든 마법이에요", "다른 조합을 골라 보세요", "마법을 모두 만들었어요", "이제 마법을 쓰세요", "만든 마법이 없어요",
           "먼저 마법을 만드세요", "쓸 마법 번호를 고르세요", "아직 만들지 않은 마법이에요", "마법 만들기로 먼저 만드세요",
           "이제 계속 쓸 수 있어요", "마법 조합법이에요", "만든 마법은", "1번 물", "2번 불", "3번 전기예요", "1번 불", "2번 물", "지금 줄이는 양은"}
    for n in range(1, 61):
        bp.add(ko_digits(str(n)) + "턴이 끝났어요")
    for hp in range(0, 11):
        bp.add("내 체력 " + ko_digits(str(hp)))
    for bo in range(0, 21):
        bp.add("보스 체력 " + ko_digits(str(bo)))
    for e in bE:
        bp.add("보스 속성은 " + e + "이에요")
        bp.add("지금은 " + e + " 속성이에요")
        bp.add(e + "을 골랐어요")
        bp.add(e)
    for f in bF:
        bp.add(f + " 차례예요")
        bp.add("다음은 " + f + " 차례예요")
    for d in range(0, 5):
        bp.add("내 체력이 " + ko_digits(str(d)) + " 줄었어요")
    for d in range(1, 5):
        bp.add("내 체력이 " + ko_digits(str(d)) + " 회복됐어요")
    for n in range(1, 11):
        bp.add("지금 공격력 보너스는 " + ko_digits(str(n)) + "이에요")
        bp.add("지금 줄이는 양은 " + ko_digits(str(n)) + "이에요")
    for n in range(1, 7):
        bp.add(ko_digits(str(n)) + "번 마법은 아직 없어요")
    for n in range(1, 7):
        bp.add(ko_digits(str(n) + "번"))   # 조합법에서 '일번' 따로 읽는 조각
    # 칸과 목록 버튼의 이름 (2번 물대포 아직 없음 / 2번 물대포 쓰기)
    for n, k in enumerate(bKeys, start=1):
        for tail in (" 아직 없음", " 쓰기"):
            bp.add(ko_digits(str(n) + "번 " + bName[k] + tail))
    for d in range(2, 31):
        bp.add("보스에게 " + ko_digits(str(d)) + "의 피해를 줬어요")
    for k in bKeys:
        sp = bName[k]
        bp.add(sp + "을 썼어요")
        bp.add("만든 마법은 " + sp)
        bp.add(ko_digits(bAb[k]))
        bp.add(bAb[k])
        for f in bF:
            bp.add(f + "가 " + sp + "을 썼어요")
        bp.add(ko_digits(bAb[k]))
        bp.add(sp + "을 합치면")
        for i, e in enumerate(bPair[k]):
            pass
        bp.add(bPair[k][0] + "을 합쳐서 " + sp + "을 만들었어요")
        bp.add(bPair[k][1] + "을 합쳐서 " + sp + "을 만들었어요")
        bp.add(ko_digits("1번") + ", " + bPair[k][0])
    for k in bKeys:
        a0, b0 = bPair[k][0], bPair[k][1]
        bp.add(b0 + "을 합치면 " + bName[k] + "이에요")
        bp.add(b0 + "을 합쳐서 " + bName[k] + "을 만들었어요")
    for x in bE:
        for y in bE:
            k2 = "".join(sorted([x, y], key=lambda t: bE.index(t)))
            k2 = {"불불": "불불", "물물": "물물", "전기전기": "전기전기"}.get(x + y, None) or None
    for x in bE:
        for y in bE:
            if x == y:
                key = x + y
            else:
                key = "".join(sorted([x, y], key=lambda t: ["불", "물", "전기"].index(t)))
            if key in bName:
                bp.add(y + "을 합쳐서 " + bName[key] + "을 만들었어요")
    # 한 번에 읽는 조합법 (번호, 조합, 스킬, 능력)
    for i, k in enumerate(bKeys):
        bp.add(ko_digits(str(i + 1) + "번") + ", " + bPair[k][0] + ", " + bPair[k][1] + "을 합치면")
    esc_pieces |= bp
    esc_pieces |= {ko_digits(x) for x in bp}
    # 함께하는 친구 이름 (박준우, 박소린, 서정민, 이수현): 이름이 들어가는 문장
    def eun(n):
        c = ord(n[-1])
        return "은" if (0xAC00 <= c <= 0xD7A3 and (c - 0xAC00) % 28 != 0) else "는"
    for name in ["박준우", "박소린", "서정민", "이수현"]:
        esc_pieces.add(name + " 친구")
        esc_pieces.add(name + " 친구는 어떤 걸 선택할까요")
        esc_pieces |= {name + eun(name) + " " + c + "예요" for c in chars}
    for name in ["용기", "지혜", "자연", "기계", "혼자", "함께", "탐구", "실천"]:
        esc_pieces |= {name + " " + str(pt) + "점" for pt in (0, 2, 4, 6)}
    # 자물쇠 화면이 이어 붙여 읽는 문장 (NATIVE, SINO 표와 같은 낱말)
    native = ["", "하나", "둘", "셋", "넷", "다섯", "여섯", "일곱", "여덟", "아홉", "열"]
    sino = ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구", "십"]
    esc_pieces |= {"자물쇠가 %s 개 있어요" % native[n] for n in range(1, 11)}
    esc_pieces |= {"자물쇠 %s번" % sino[n] for n in range(1, 11)}
    esc_pieces |= set(sino[1:]) | {"일번", "이번", "삼번", "사번", "보기는", "틀린 보기예요", "열리는 보기예요"}
    esc_pieces |= {w + "을 골랐어요" for w in ["일번", "이번", "삼번", "사번"]} | {"정답은 " + w + "이에요" for w in ["일번", "이번", "삼번", "사번"]}
    for text in sorted(esc_pieces):
        if text in manifest:
            continue  # 영어타자 페이지와 같은 문장은 이미 있어요
        rel = name_for(text, "ko")
        manifest[text] = rel
        jobs.append(make_one(sem, pron_py(text), KO_VOICE, HERE.parent / rel))
    for text in en_all:
        rel = name_for("EN|" + text, "en")
        manifest["EN|" + text] = rel
        jobs.append(make_one(sem, text, EN_VOICE, HERE.parent / rel))

    results = await asyncio.gather(*jobs)  # noqa
    print("한국어 %d개, 영어 %d개" % (len(ko_all), len(en_all)))
    print("새로 만듦: %d, 이미 있음: %d, 실패: %d" % (
        results.count("ok"), results.count("skip"), results.count("fail")))

    # 페이지가 읽는 목록 (file:// 로 열어도 읽히도록 js 파일로 저장)
    body = json.dumps(manifest, ensure_ascii=False, indent=1)
    (HERE / "manifest.js").write_text("window.VOICE_MAP = " + body + ";\n", encoding="utf-8")
    print("manifest.js 저장:", len(manifest), "항목")


if __name__ == "__main__":
    asyncio.run(main())
