import os
from pathlib import Path

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
