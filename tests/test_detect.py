from foxcam.detect import iou, link

def test_iou_and_linking():
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1
    assert iou((0, 0, 10, 10), (20, 20, 10, 10)) == 0
    assert abs(iou((0, 0, 10, 10), (5, 0, 10, 10)) - 1 / 3) < 1e-9
    dog = lambda x: ("dog", 0.9, x, 0, 50, 50)
    person = ("person", 0.8, 200, 200, 60, 120)
    frames = [(0, [dog(0), person]), (2, [dog(6), person]), (4, [person]), (6, [dog(20)])]
    tracks = link(frames)
    assert [(t["id"], t["class"], len(t["boxes"])) for t in tracks] == [(0, "dog", 3), (1, "person", 3)]
    assert tracks[0]["boxes"][0] == [0, 0, 0, 50, 50] and tracks[0]["boxes"][-1] == [6, 20, 0, 50, 50]
    assert len(link([(0, [dog(0)]), (2, [("cat", 0.9, 0, 0, 50, 50)])])) == 2
    gap = [(0, [dog(0)])] + [(f, []) for f in range(2, 22, 2)] + [(22, [dog(0)])]
    assert len(link(gap)) == 2 and len(link(gap, max_misses=11)) == 1
