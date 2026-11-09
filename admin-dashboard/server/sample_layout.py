"""Layouts of the sample buildings, shared by the server and the floor plan scripts in tools/.

Coordinates are map units (0-100 on both axes), the same as bins and graph nodes. The large building
has five floors, north (y=30) and south (y=70) corridors joined by west/east stairs and a central lift.
"""

import math

LARGE_FLOORS = 5
# (x0, y0, x1, y1), 1F label, upper-floor label
LARGE_ROOMS = [
    ((0, 0, 36, 25), "로비", "{f}01 강의실"), ((36, 0, 64, 25), "학생지원센터", "{f}02 강의실"),
    ((64, 0, 100, 25), "카페", "{f}03 강의실"), ((12, 35, 29, 65), "우편실", "세미나실 A"),
    ((29, 35, 46, 65), "보안실", "세미나실 B"), ((54, 35, 71, 65), "자료실", "실험실"),
    ((71, 35, 88, 65), "회의실", "연구실"), ((0, 75, 38, 100), "휴게 공간", "휴게실"),
    ((38, 75, 62, 100), "시설 관리실", "열람실"), ((62, 75, 100, 100), "학생 라운지", "스터디 라운지"),
]
LARGE_CORRIDORS = [("N", 30, "북쪽"), ("S", 70, "남쪽")]
LARGE_CORRIDOR_X = [6, 24, 50, 76, 94]
# id, x, kind, label, distance per floor in metres (the lift includes waiting time)
LARGE_CORES = [("WS", 6, "stairs", "서쪽 계단", 12.0), ("EL", 50, "elevator", "중앙 엘리베이터", 15.0),
               ("ES", 94, "stairs", "동쪽 계단", 12.0)]
# x, y, access node, room index (six bins on every floor)
LARGE_BINS = [(24, 14, "N1", 0), (76, 14, "N3", 2), (20, 50, "N1", 3), (80, 50, "S3", 6), (24, 87, "S1", 7), (76, 87, "S3", 9)]
LARGE_FILLS = [(None, 93, 45, 82, 30, 61), (96, 52, 85, 38, 91, 70), (41, 88, 95, 25, 66, 83),
               (92, 35, 58, 87, 20, 97), (64, 90, 33, 81, 48, 55)]
LARGE_OFFICE = (50, 87, "S2")  # 1F, inside 시설 관리실
LARGE_DEPOT = (92, 88, "S4")  # 1F, inside 학생 라운지


def large_room_label(room: tuple, floor: int) -> str:
    return room[1] if floor == 1 else room[2].format(f=floor)


# The library sample: six floors, a corridor ring around a central atrium, stairs to the west and
# east, and two glass lifts on the atrium's north and south sides.
LIBRARY_FLOORS = 6
# ring corridor points: id, x, y
LIBRARY_RING = [("N0", 10, 27), ("N1", 30, 27), ("N2", 50, 27), ("N3", 70, 27), ("N4", 90, 27), ("E1", 90, 50),
                ("S4", 90, 73), ("S3", 70, 73), ("S2", 50, 73), ("S1", 30, 73), ("S0", 10, 73), ("W1", 10, 50)]
# id, x, y, kind, label, corridor point it opens onto, distance per floor in metres (the lift includes waiting time)
LIBRARY_CORES = [("ST1", 4, 50, "stairs", "서쪽 계단", "W1", 12.0), ("ST2", 96, 50, "stairs", "동쪽 계단", "E1", 12.0),
                 ("EL1", 50, 36, "elevator", "북쪽 엘리베이터", "N2", 15.0), ("EL2", 50, 64, "elevator", "남쪽 엘리베이터", "S2", 15.0)]
LIBRARY_ATRIUM = (22, 37, 78, 63)
# rooms: (x0, y0, x1, y1), corridor point of the door, bin position
LIBRARY_ROOMS = [((0, 0, 22, 21), "N0", (16, 14)), ((22, 0, 50, 21), "N1", (36, 14)), ((50, 0, 78, 21), "N3", (64, 14)),
                 ((78, 0, 100, 21), "N4", (84, 14)), ((0, 79, 22, 100), "S0", (16, 86)), ((22, 79, 50, 100), "S1", (30, 86)),
                 ((50, 79, 78, 100), "S3", (70, 86)), ((78, 79, 100, 100), "S4", (84, 86))]
LIBRARY_ROOM_NAMES = {
    1: ["어린이자료실", "로비 · 안내데스크", "북카페", "유아실", "시설관리실", "다목적 강당", "무인 반납실", "하역장"],
    2: ["종합자료실 1", "종합자료실 2", "정기간행물실", "신문 열람실", "멀티미디어실", "디지털자료실", "그룹스터디룸", "휴게 라운지"],
    3: ["일반열람실 A", "일반열람실 B", "노트북열람실", "스터디카페", "세미나실 1", "세미나실 2", "사물함실", "휴게실"],
    4: ["인문과학자료실", "사회과학자료실", "자연과학자료실", "외국어자료실", "사서실", "보존서고", "고문헌실", "연구실"],
    5: ["향토자료실", "큰글자 열람실", "점자도서실", "오디오북실", "문화교실 1", "문화교실 2", "전시실", "북토크홀"],
    6: ["평생학습실 1", "평생학습실 2", "북라운지", "직원 휴게실", "행정지원실", "회의실", "전산실", "옥상정원 출입구"],
}
# offices and the drop-off point: floor, room index, kind, position, label (their rooms get no bin)
LIBRARY_POINTS = [(1, 4, "office", (14, 89), "시설관리실"), (4, 4, "office", (14, 89), "사서실"),
                  (1, 7, "depot", (89, 89), "분리수거장")]
LIBRARY_FILL_PATTERN = [62, 91, 45, 83, 27, 96, 70, 55]


def library_fill(floor: int, room: int) -> int:
    return LIBRARY_FILL_PATTERN[(room + 3 * floor) % len(LIBRARY_FILL_PATTERN)]


# The civic complex sample: an 8-floor office wing (A동) and a 5-floor culture and welfare wing (B동),
# joined by a central link with the main lift and stairs. Each wing has a corridor loop. The B동
# freight lift is out of service on 3F (운영 중단), and floors 6-8 have the A동 and the link only.
CIVIC_FLOORS = 8
# corridor points: id, x, y, label, highest floor
CIVIC_CORRIDOR = [("AN0", 8, 32, "A동 북쪽 복도 1", 8), ("AN1", 20, 32, "A동 북쪽 복도 2", 8), ("AN2", 32, 32, "A동 북쪽 복도 3", 8),
                  ("AN3", 40, 32, "A동 북쪽 복도 4", 8), ("AS0", 8, 68, "A동 남쪽 복도 1", 8), ("AS1", 20, 68, "A동 남쪽 복도 2", 8),
                  ("AS2", 32, 68, "A동 남쪽 복도 3", 8), ("AS3", 40, 68, "A동 남쪽 복도 4", 8), ("AW", 8, 50, "A동 서쪽 복도", 8),
                  ("AE", 40, 50, "A동 동쪽 복도", 8), ("CN", 50, 32, "연결동 북쪽", 8), ("CC", 50, 50, "중앙 로비", 8),
                  ("CS", 50, 68, "연결동 남쪽", 8), ("BN0", 60, 32, "B동 북쪽 복도 1", 5), ("BN1", 70, 32, "B동 북쪽 복도 2", 5),
                  ("BN2", 81, 32, "B동 북쪽 복도 3", 5), ("BN3", 92, 32, "B동 북쪽 복도 4", 5), ("BS0", 60, 68, "B동 남쪽 복도 1", 5),
                  ("BS1", 70, 68, "B동 남쪽 복도 2", 5), ("BS2", 81, 68, "B동 남쪽 복도 3", 5), ("BS3", 92, 68, "B동 남쪽 복도 4", 5),
                  ("BE", 92, 50, "B동 동쪽 복도", 5)]
# corridor links; a link is on every floor that has both of its ends
CIVIC_LINKS = [("AN0", "AN1"), ("AN1", "AN2"), ("AN2", "AN3"), ("AS0", "AS1"), ("AS1", "AS2"), ("AS2", "AS3"),
               ("AN0", "AW"), ("AW", "AS0"), ("AN3", "AE"), ("AE", "AS3"), ("AN3", "CN"), ("AS3", "CS"), ("CN", "CC"),
               ("CC", "CS"), ("CN", "BN0"), ("CS", "BS0"), ("BN0", "BN1"), ("BN1", "BN2"), ("BN2", "BN3"),
               ("BS0", "BS1"), ("BS1", "BS2"), ("BS2", "BS3"), ("BN3", "BE"), ("BE", "BS3")]
# code, x, y, kind, label, corridor point, distance per floor in metres, highest floor, floors out of service
CIVIC_CORES = [("ST1", 3, 50, "stairs", "A동 서쪽 계단", "AW", 12.0, 8, ()),
               ("EL1", 46, 42, "elevator", "중앙 엘리베이터", "CC", 15.0, 8, ()),
               ("ST2", 54, 58, "stairs", "중앙 계단", "CC", 12.0, 8, ()),
               ("EL2", 88, 44, "elevator", "B동 화물 엘리베이터", "BE", 15.0, 5, (3,)),
               ("ST3", 97, 50, "stairs", "B동 동쪽 계단", "BE", 12.0, 5, ())]
# rooms: (x0, y0, x1, y1), corridor point of the door, highest floor, bins on every floor (else 1F only)
CIVIC_ROOMS = [((1, 8, 15, 27), "AN0", 8, True), ((15, 8, 29, 27), "AN1", 8, True), ((29, 8, 44, 27), "AN2", 8, True),
               ((12, 37, 24, 63), "AN1", 8, False), ((24, 37, 36, 63), "AN2", 8, False),
               ((1, 73, 15, 92), "AS0", 8, True), ((15, 73, 29, 92), "AS1", 8, True), ((29, 73, 44, 92), "AS2", 8, True),
               ((56, 8, 70, 27), "BN0", 5, True), ((70, 8, 84, 27), "BN2", 5, True), ((84, 8, 99, 27), "BN3", 5, True),
               ((63, 37, 74, 63), "BN1", 5, False), ((74, 37, 85, 63), "BN2", 5, False),
               ((56, 73, 70, 92), "BS0", 5, True), ((70, 73, 84, 92), "BS2", 5, True), ((84, 73, 99, 92), "BS3", 5, True)]
CIVIC_ROOM_NAMES = {
    1: ["민원실 A", "민원실 B", "열린카페", "종합상황실", "민원 대기실", "주차장 수거함", "시민 상담실", "보안실",
        "시민 홀", "갤러리", "작은 도서관", "다목적실", "물품 보관실", "수유실", "우체국", "하역장"],
    2: ["기획예산과", "감사실", "법무팀", "정책회의실", "기록관", "세무과", "징수과", "서류창고",
        "평생학습실 1", "평생학습실 2", "컴퓨터교실", "강의실", "교재실", "청소년 공부방", "동아리방", "휴게실"],
    3: ["도시계획과", "건축과", "교통과", "상황 회의실", "도면 보관실", "주택과", "공원녹지과", "직원 휴게실",
        "건강증진센터", "보건 상담실", "예방접종실", "검진 대기실", "의무 기록실", "체력단련실", "샤워실", "자원봉사센터"],
    4: ["복지정책과", "노인복지과", "아동보육과", "상담센터", "자료실", "일자리과", "청년정책과", "탕비실",
        "대강당 로비", "대강당", "분장실", "음향실", "무대 창고", "세미나실 1", "세미나실 2", "휴게 라운지"],
    5: ["환경정책과", "자원순환과", "기후대응과", "대회의실", "소회의실", "경제정책과", "투자유치과", "휴게실",
        "시민 식당", "주방", "식재료 창고", "직원 식당", "배식대", "카페테리아", "옥상정원 출입구", "기계실"],
    6: ["인사과", "행정지원과", "정보통신과", "서버실", "총무과", "회계과", "계약과", "직원 휴게실"],
    7: ["부시장실", "비서실", "접견실", "정책보좌관실", "홍보담당관실", "대변인실", "브리핑룸", "탕비실"],
    8: ["시장실", "비서실", "접견실", "시정회의실", "귀빈 대기실", "직원 라운지", "하늘정원 입구", "공조실"],
}
# offices and drop-off points: floor, room index, kind, position, label (their rooms get no bin)
CIVIC_POINTS = [(1, 3, "office", (18, 52), "종합상황실"), (6, 4, "office", (30, 52), "총무과"),
                (1, 15, "depot", (91, 85), "하역장 분리수거장"), (1, 5, "depot", (8, 85), "주차장 분리수거함")]
CIVIC_FILL_PATTERN = [58, 92, 37, 81, 66, 95, 24, 73, 49]


def civic_bin_at(room: tuple) -> tuple:
    """Where a room's bin stands: by its door, inside the wall that faces the corridor."""
    (x0, y0, x1, y1), door, _, _ = room
    door_x = next(x for point, x, *_ in CIVIC_CORRIDOR if point == door)
    x = min(max(door_x, x0 + 4), x1 - 4)
    return x, (y1 - 6 if y1 <= 30 else y0 + 6)



# The curved sample: a convention centre shaped like a running track (two half circles joined by
# straight sides) around a central hall. The map stretches its 0-100 units to 900 x 460 pixels, so
# this geometry is set in plan pixels to keep the curves round on screen, and its corridor links
# carry distances measured on it (ROUND_M_PER_PX metres per pixel).
ROUND_FLOORS = 4
ROUND_CENTRES = ((240, 230), (660, 230))  # plan pixels: centres of the west and east half circles
ROUND_M_PER_PX = 0.18
ROUND_RADII = {"wall": 222, "outer_rooms": 160, "outer_corridor": 140, "middle_out": 118, "middle_in": 88,
               "inner_corridor": 72, "hall": 55}
# positions along the track: 0-1 north side (west to east), 1-2 east curve, 2-3 south side, 3-4 west curve
# straight sides need only the points where passages and doors meet them; the curves get a point
# every 30 degrees (outer) or 45 degrees (inner)
ROUND_OUTER_U = [0, 0.5, 0.75] + [1 + k / 6 for k in range(6)] + [2, 2.5, 2.75] + [3 + k / 6 for k in range(6)]
ROUND_INNER_U = [0, 0.25, 0.5] + [1 + k / 4 for k in range(4)] + [2, 2.25, 2.5] + [3 + k / 4 for k in range(4)]
ROUND_RADIALS = [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5]  # passages between the outer (OR) and inner (IR) corridor
# code, position, radius, kind, label (the door is the nearest outer corridor point)
ROUND_CORES = [("ST1", 3.5, 191, "stairs", "서쪽 계단"), ("ST2", 1.5, 191, "stairs", "동쪽 계단"),
               ("EL1", 0.75, 103, "elevator", "북쪽 엘리베이터"), ("EL2", 2.75, 103, "elevator", "남쪽 엘리베이터")]
# rooms: band, from and to position; outer rooms open onto the outer corridor, middle rooms onto the inner one
ROUND_ROOMS = [("outer", 0, 1 / 3), ("outer", 1 / 3, 2 / 3), ("outer", 2 / 3, 1), ("outer", 1, 1.4), ("outer", 1.6, 2),
               ("outer", 2, 7 / 3), ("outer", 7 / 3, 8 / 3), ("outer", 8 / 3, 3), ("outer", 3, 3.4), ("outer", 3.6, 4),
               ("middle", 0, 0.5), ("middle", 1, 1.5), ("middle", 1.5, 2), ("middle", 2, 2.5), ("middle", 3, 3.5), ("middle", 3.5, 4)]
ROUND_ROOM_NAMES = {
    1: ["전시홀 A", "전시홀 B", "전시홀 C", "물품보관소", "하역장", "카페", "주출입구 로비", "운영사무실", "기념품점", "매표소",
        "등록 데스크", "의무실", "방송실", "안내 센터", "수유실", "유실물 센터"],
    2: ["컨퍼런스룸 1", "컨퍼런스룸 2", "컨퍼런스룸 3", "컨퍼런스룸 4", "세미나실 1", "세미나실 2", "2층 라운지", "휴게 라운지",
        "세미나실 3", "세미나실 4", "준비실", "장비 창고", "연사 대기실", "통역 부스", "회의 지원실", "창고"],
    3: ["그랜드볼룸 A", "그랜드볼룸 B", "그랜드볼룸 C", "연회 준비실", "연회 주방", "리셉션홀", "3층 라운지", "VIP 라운지",
        "프레스룸", "비즈니스 센터", "출연자 대기실", "기술지원실", "음향실", "연회 창고", "의상실", "조명실"],
    4: ["레스토랑", "스카이라운지", "전망 데크", "주방", "식자재 창고", "사무국", "회의실", "직원 휴게실", "전산실", "기계실",
        "회의 준비실", "청소용품실", "직원 탈의실", "문서고", "비품 창고", "공조실"],
}
# offices and the drop-off point: floor, room index, kind, position, radius, label (their rooms get no bin)
ROUND_POINTS = [(1, 7, "office", 2.85, 186, "운영사무실"), (3, 11, "office", 1.27, 104, "기술지원실"),
                (1, 4, "depot", 1.82, 186, "분리수거장")]
ROUND_FILL_PATTERN = [64, 93, 41, 86, 57, 97, 29, 78]


def round_px(u: float, radius: float) -> tuple:
    """Plan pixel position at a place along the track, at a distance from its centre line."""
    u %= 4
    (wx, cy), (ex, _) = ROUND_CENTRES
    if u < 1:
        return wx + (ex - wx) * u, cy - radius
    if u < 2:
        a = math.radians(90 - 180 * (u - 1))
        return ex + radius * math.cos(a), cy - radius * math.sin(a)
    if u < 3:
        return ex - (ex - wx) * (u - 2), cy + radius
    a = math.radians(270 - 180 * (u - 3))
    return wx + radius * math.cos(a), cy - radius * math.sin(a)


def round_at(u: float, radius: float) -> tuple:
    """Map position (units) of a place along the track."""
    x, y = round_px(u, radius)
    return round(x / 9, 2), round(y / 4.6, 2)


def round_nearest(places: list, u: float) -> int:
    return min(range(len(places)), key=lambda i: abs(places[i] - u))


def round_door(room: tuple) -> str:
    band, u0, u1 = room
    ring, places = ("OR", ROUND_OUTER_U) if band == "outer" else ("IR", ROUND_INNER_U)
    return f"{ring}{round_nearest(places, (u0 + u1) / 2)}"


def round_bin_u(room: tuple) -> float:
    # a bin stands just inside its door, so the walk from the corridor to it is short and straight
    band, u0, u1 = room
    places = ROUND_OUTER_U if band == "outer" else ROUND_INNER_U
    return min(max(places[round_nearest(places, (u0 + u1) / 2)], u0 + 0.07), u1 - 0.07)


def round_bin_px(room: tuple) -> tuple:
    return round_px(round_bin_u(room), 172 if room[0] == "outer" else 100)


def round_bin_at(room: tuple) -> tuple:
    x, y = round_bin_px(room)
    return round(x / 9, 2), round(y / 4.6, 2)
