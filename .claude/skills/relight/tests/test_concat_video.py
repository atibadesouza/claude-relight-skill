import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import concat_video as cv


def test_concat_list_order_and_format():
    txt = cv.build_concat_list(["a.mp4", "b.mp4"])
    assert txt.strip().splitlines() == ["file 'a.mp4'", "file 'b.mp4'"]


def test_concat_list_normalizes_backslashes():
    txt = cv.build_concat_list([r"C:\work\seg_000.mp4"])
    assert txt.strip() == "file 'C:/work/seg_000.mp4'"
