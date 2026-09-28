from foxcam.edges import nearest_edge

def test_edges_and_unknown():
    assert nearest_edge(20, 360, 1280, 720, 80) == "left"
    assert nearest_edge(640, 20, 1280, 720, 80) == "far"
    assert nearest_edge(640, 700, 1280, 720, 80) == "fence"
    assert nearest_edge(1260, 360, 1280, 720, 80) == "right"
    assert nearest_edge(640, 360, 1280, 720, 80) == "unknown"
    assert nearest_edge(80, 360, 1280, 720, 80) == "left"
