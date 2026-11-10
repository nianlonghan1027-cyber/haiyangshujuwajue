"""Compare three point-in-channel workflows for a fixed two-scene exercise."""

import argparse

import h3
from pyproj import CRS, Transformer
from shapely.geometry import Point, box


RESOLUTION = 10
WIDTH_M = 86
LENGTH_M = 330
START_X_M = -15
EAST_SHIFT_M = 55

# Each coordinate is an (east, north) offset in meters from the channel center.
BOATS = {
    "A": (-31, 115),
    "B": (-28, -60),
    "C": (34, -154),
    "D": (-52, 70),
    "E": (59, -31),
    "F": (-98, -121),
}

LOCAL_CRS = CRS.from_proj4(
    "+proj=aeqd +lat_0=30 +lon_0=123 +datum=WGS84 +units=m"
)
TO_WGS84 = Transformer.from_crs(LOCAL_CRS, "EPSG:4326", always_xy=True)
TO_LOCAL = Transformer.from_crs("EPSG:4326", LOCAL_CRS, always_xy=True)


def to_latlng(x, y):
    """Convert local (east, north) to H3's (latitude, longitude) order."""
    lon, lat = TO_WGS84.transform(x, y)
    return lat, lon


def make_scene(east_shift):
    center_x = START_X_M + east_shift
    half_width = WIDTH_M / 2
    half_length = LENGTH_M / 2
    channel = box(
        center_x - half_width, -half_length, center_x + half_width, half_length
    )
    boats = {boat_id: Point(center_x + x, y) for boat_id, (x, y) in BOATS.items()}
    return channel, boats


def exact_hits(channel, boats, candidates):
    # covers treats points on the channel boundary as hits.
    return {boat_id for boat_id in candidates if channel.covers(boats[boat_id])}


def ids(boat_ids):
    return ", ".join(sorted(boat_ids)) or "∅"


def compare(east_shift, inspect_id):
    channel, boats = make_scene(east_shift)
    polygon = h3.LatLngPoly(
        [to_latlng(x, y) for x, y in list(channel.exterior.coords)[:-1]]
    )
    boat_cells = {
        boat_id: h3.latlng_to_cell(*to_latlng(boat.x, boat.y), RESOLUTION)
        for boat_id, boat in boats.items()
    }
    all_ids = set(boats)
    truth = exact_hits(channel, boats, all_ids)
    candidates_by_mode = {}

    print(f"\n=== 相对场景 1 向东移动 {east_shift} 米 ===")
    print(f"逐点检查           候选 [{ids(all_ids)}]  命中 [{ids(truth)}]")
    for mode, name in (("center", "中心覆盖＋精判"), ("overlap", "相交覆盖＋精判")):
        covering_cells = set(
            h3.h3shape_to_cells_experimental(polygon, RESOLUTION, contain=mode)
        )
        candidates = {
            boat_id for boat_id, cell in boat_cells.items() if cell in covering_cells
        }
        candidates_by_mode[mode] = candidates
        hits = exact_hits(channel, boats, candidates)
        print(f"{name}     候选 [{ids(candidates)}]  命中 [{ids(hits)}]")

    center = candidates_by_mode["center"]
    overlap = candidates_by_mode["overlap"]
    added = overlap - center
    recovered = added & truth
    rejected = added - truth
    print(f"中心覆盖漏点 [{ids(truth - center)}]")
    print(f"相交覆盖漏点 [{ids(truth - overlap)}]")
    print(f"相交覆盖新增候选 {len(added)} 个 [{ids(added)}]")
    print(f"  找回的漏点 {len(recovered)} 个 [{ids(recovered)}]")
    print(f"  精判剔除点 {len(rejected)} 个 [{ids(rejected)}]")

    if inspect_id:
        cell = boat_cells[inspect_id]
        lat, lon = h3.cell_to_latlng(cell)
        x, y = TO_LOCAL.transform(lon, lat)
        location = "航道内" if channel.covers(Point(x, y)) else "航道外"
        print(
            f"船位 {inspect_id} 所在格 {cell}，"
            f"格心东坐标 {x:.1f} 米、北坐标 {y:.1f} 米，位于{location}"
        )
    return truth


def main():
    parser = argparse.ArgumentParser(description="H3 航道横移对照实验")
    parser.add_argument("--inspect", choices=BOATS, metavar="ID", help="查看某个船位的格心")
    args = parser.parse_args()
    before = compare(0, args.inspect)
    after = compare(EAST_SHIFT_M, args.inspect)
    status = "一致" if before == after else "不一致"
    print(f"\n平移前后逐点检查的命中 ID {status}。")


if __name__ == "__main__":
    main()
