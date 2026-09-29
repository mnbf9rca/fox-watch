from foxcam.media import _moved


def test_walk_then_pause():
    boxes = [[0, 100, 100, 20, 20], [2, 140, 100, 20, 20], [4, 140, 100, 20, 20]]
    assert _moved(boxes, 40)
    assert not _moved(boxes, 41)


def test_out_and_back():
    boxes = [[0, 100, 100, 20, 20], [2, 150, 100, 20, 20], [4, 100, 100, 20, 20]]
    assert _moved(boxes, 40)


def test_parked_car_jitter():
    boxes = [[frame, 100 + frame % 5, 100 + frame % 3, 100, 60] for frame in range(100)]
    assert not _moved(boxes, 40)
    assert _moved(boxes, 0)


def test_centroid_bounds_diagonal():
    # Changing box sizes moves the centroid by (24, 32), exactly 40 pixels.
    assert _moved([[0, 100, 100, 20, 20], [2, 100, 100, 68, 84]], 40)
    assert not _moved([[0, 100, 100, 20, 20]], 40)
    assert not _moved([], 40)
