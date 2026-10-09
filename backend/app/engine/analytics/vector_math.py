from typing import Tuple, Optional

def line_side(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """
    Calculate the cross-product to determine which side of the line (P1 -> P2)
    the point P(px, py) is on.
    > 0 : Left side
    < 0 : Right side
    = 0 : On the line
    """
    return (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)

def do_segments_intersect(
    p1: Tuple[float, float], p2: Tuple[float, float],
    q1: Tuple[float, float], q2: Tuple[float, float]
) -> bool:
    """
    Check if segment p1->p2 intersects segment q1->q2.
    """
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = q1
    x4, y4 = q2

    d1 = (x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1)
    d2 = (x2 - x1) * (y4 - y1) - (y2 - y1) * (x4 - x1)
    d3 = (x4 - x3) * (y1 - y3) - (y4 - y3) * (x1 - x3)
    d4 = (x4 - x3) * (y2 - y3) - (y4 - y3) * (x2 - x3)

    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
       ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True

    return False

def check_line_crossing(
    prev_pos: Tuple[float, float],
    curr_pos: Tuple[float, float],
    line_start: Tuple[float, float],
    line_end: Tuple[float, float],
    direction_arrow: str = "BIDIRECTIONAL"
) -> Optional[str]:
    """
    Determine if an object trajectory crosses the line and in which direction.
    Coordinates are assumed to be in the same space (e.g. pixels or normalized 0.0-1.0).

    Returns:
        "IN", "OUT", or None if no crossing.
    """
    x1, y1 = line_start
    x2, y2 = line_end

    side_prev = line_side(prev_pos[0], prev_pos[1], x1, y1, x2, y2)
    side_curr = line_side(curr_pos[0], curr_pos[1], x1, y1, x2, y2)

    # Check if trajectory intersects line segment
    if not do_segments_intersect(prev_pos, curr_pos, line_start, line_end):
        # Also check simple side change if segments are very close
        if (side_prev > 0 and side_curr < 0) or (side_prev < 0 and side_curr > 0):
            # Verify proximity to line segment bounding box
            min_lx, max_lx = min(x1, x2) - 0.05, max(x1, x2) + 0.05
            min_ly, max_ly = min(y1, y2) - 0.05, max(y1, y2) + 0.05
            cx, cy = curr_pos
            if not (min_lx <= cx <= max_lx and min_ly <= cy <= max_ly):
                return None
        else:
            return None

    # Determine direction
    # Going from Left (side > 0) to Right (side < 0) -> "IN"
    # Going from Right (side < 0) to Left (side > 0) -> "OUT"
    if side_prev > 0 and side_curr <= 0:
        detected_dir = "IN"
    elif side_prev < 0 and side_curr >= 0:
        detected_dir = "OUT"
    else:
        return None

    if direction_arrow == "IN_ONLY" and detected_dir != "IN":
        return None
    if direction_arrow == "OUT_ONLY" and detected_dir != "OUT":
        return None

    return detected_dir
