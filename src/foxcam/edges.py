def nearest_edge(x: float, y: float, width: int, height: int, margin: float) -> str:
    distances = {"far": y, "fence": height - y, "left": x, "right": width - x}
    edge = min(distances, key=distances.get)
    return edge if distances[edge] <= margin else "unknown"
