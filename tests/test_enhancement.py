import os
from pathlib import Path

import cv2
import pytest
from backend.image_enhancer import ImageEnhancer

SAMPLE_DIR = Path("sample_slips")


def _sample_files():
    files = sorted(SAMPLE_DIR.glob("p_*.jpg"))
    return files or sorted(
        path for path in SAMPLE_DIR.iterdir()
        if path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )


@pytest.fixture
def enhancer():
    return ImageEnhancer()


def test_enhancement_pipeline_performance(enhancer):
    sample_files = _sample_files()[:4]
    assert sample_files, "sample_slips/ must contain photos"

    for path in sample_files:
        cv_img = enhancer.load_file_as_cv2(str(path))
        assert cv_img is not None
        assert cv_img.shape[0] > 0 and cv_img.shape[1] > 0

        res = enhancer.process_image(cv_img)
        assert res.elapsed_seconds < 5.0, f"Enhancement took {res.elapsed_seconds:.2f}s on {path.name}"
        assert res.enhanced_image is not None
        assert res.enhanced_width > 0 and res.enhanced_height > 0
        assert isinstance(res.skew_angle, float)


def test_enhancement_output_saving(enhancer, tmp_path):
    sample_files = _sample_files()
    assert sample_files, "sample_slips/ must contain photos"
    cv_img = enhancer.load_file_as_cv2(str(sample_files[0]))
    res = enhancer.process_image(cv_img)

    out_enhanced = str(tmp_path / "enh_test.jpg")
    out_thumb = str(tmp_path / "thumb_test.jpg")

    enhancer.save_results(res, out_enhanced, out_thumb)

    assert os.path.exists(out_enhanced)
    assert os.path.getsize(out_enhanced) > 0
    assert os.path.exists(out_thumb)
    assert os.path.getsize(out_thumb) > 0


def test_resultslip_stays_upright(enhancer):
    path = SAMPLE_DIR / "ResultSlip.jpg"
    if not path.exists():
        pytest.skip("ResultSlip.jpg not in sample_slips/")
    img = enhancer.load_file_as_cv2(str(path))
    upright = enhancer.upright_orientation(img)
    assert upright.shape == img.shape
    assert enhancer.header_bar_score(upright) >= enhancer.header_bar_score(
        cv2.rotate(upright, cv2.ROTATE_180)
    )
    # An upside-down capture should be flipped back.
    flipped = cv2.rotate(img, cv2.ROTATE_180)
    corrected = enhancer.upright_orientation(flipped)
    assert enhancer.header_bar_score(corrected) >= 0.12


def test_landscape_national_rotates_header_to_top(enhancer):
    path = SAMPLE_DIR / "p_1.jpg"
    if not path.exists():
        pytest.skip("p_1.jpg not in sample_slips/")
    img = enhancer.load_file_as_cv2(str(path))
    upright, degrees = enhancer._upright_with_degrees(img)
    assert upright.shape[0] > upright.shape[1]
    assert degrees in {90, 270}
    assert enhancer._header_delta(upright) > 0.5
    assert enhancer.header_bar_score(upright) > 0.5


def test_washed_header_is_not_beaten_by_background(enhancer):
    import numpy as np

    img = np.full((400, 300, 3), 240, dtype=np.uint8)
    # Faded provincial-pink bar at the top (hue ~2, sat ~60).
    img[20:50, 20:280] = (110, 113, 151)
    # Orange chair blob at the bottom that used to win a 180 flip.
    img[330:390, 20:80] = (40, 90, 200)
    upright = enhancer.upright_orientation(img)
    assert np.array_equal(upright, img)
