import os
import time
import pytest
from backend.image_enhancer import ImageEnhancer

@pytest.fixture
def enhancer():
    return ImageEnhancer()

def test_enhancement_pipeline_performance(enhancer):
    sample_files = ["image1.jpg", "image2.jpg", "image3.jpg", "image4.jpg"]
    
    for filename in sample_files:
        path = os.path.join("sample_slips", filename)
        assert os.path.exists(path), f"Sample file {path} must exist"
        
        cv_img = enhancer.load_file_as_cv2(path)
        assert cv_img is not None
        assert cv_img.shape[0] > 0 and cv_img.shape[1] > 0
        
        t0 = time.time()
        res = enhancer.process_image(cv_img)
        elapsed = time.time() - t0
        
        # Acceptance Criterion 1: Must be under 5 seconds per file
        assert elapsed < 5.0, f"Enhancement took {elapsed:.2f}s, expected < 5.0s"
        assert res.enhanced_image is not None
        assert res.enhanced_width > 0 and res.enhanced_height > 0
        assert isinstance(res.skew_angle, float)

def test_enhancement_output_saving(enhancer, tmp_path):
    path = os.path.join("sample_slips", "image1.jpg")
    cv_img = enhancer.load_file_as_cv2(path)
    res = enhancer.process_image(cv_img)
    
    out_enhanced = str(tmp_path / "enh_test.jpg")
    out_thumb = str(tmp_path / "thumb_test.jpg")
    
    enhancer.save_results(res, out_enhanced, out_thumb)
    
    assert os.path.exists(out_enhanced)
    assert os.path.getsize(out_enhanced) > 0
    assert os.path.exists(out_thumb)
    assert os.path.getsize(out_thumb) > 0
