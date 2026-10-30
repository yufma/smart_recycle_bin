"""Layout of the large sample building, shared by the server and tools/make_large_floorplans.py.

Five floors, north (y=30) and south (y=70) corridors joined by west/east stairs and a central lift.
Coordinates are map units (0-100 on both axes), the same as bins and graph nodes.
"""

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


def large_room_label(room: tuple, floor: int) -> str:
    return room[1] if floor == 1 else room[2].format(f=floor)
