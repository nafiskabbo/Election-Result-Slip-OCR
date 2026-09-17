import cv2
import numpy as np
import os
import time
from PIL import Image, ImageOps
from typing import Tuple, Optional, List

try:
    import pypdfium2 as pdfium
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

class ImageEnhancementResult:
    def __init__(
        self,
        enhanced_image: np.ndarray,
        binary_image: np.ndarray,
        skew_angle: float,
        is_perspective_corrected: bool,
        elapsed_seconds: float,
        raw_width: int,
        raw_height: int,
        enhanced_width: int,
        enhanced_height: int,
        rotation_degrees: int = 0,
    ):
        self.enhanced_image = enhanced_image
        self.binary_image = binary_image
        self.skew_angle = skew_angle
        self.is_perspective_corrected = is_perspective_corrected
        self.elapsed_seconds = elapsed_seconds
        self.raw_width = raw_width
        self.raw_height = raw_height
        self.enhanced_width = enhanced_width
        self.enhanced_height = enhanced_height
        self.rotation_degrees = int(rotation_degrees)

class ImageEnhancer:
    def __init__(self, target_width: int = 1654, target_height: int = 2339):
        # Default target is A4 aspect ratio @ ~200 DPI (1654 x 2339)
        self.target_width = target_width
        self.target_height = target_height

    def load_file_as_cv2(self, file_path: str, page_index: int = 0) -> np.ndarray:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            if not PDF_SUPPORT:
                raise RuntimeError("PDF rendering is not supported because pypdfium2 is not installed.")
            pdf = pdfium.PdfDocument(file_path)
            if page_index >= len(pdf):
                raise ValueError(f"Page index {page_index} out of range for PDF with {len(pdf)} pages.")
            page = pdf[page_index]
            # Render at 200 DPI (scale ~2.77 for standard 72 DPI PDF points)
            pil_image = page.render(scale=2.77).to_pil()
            img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
            return img
        else:
            # PIL applies EXIF orientation; cv2.imread does not, so phone
            # photos otherwise arrive on their side or upside down.
            try:
                with Image.open(file_path) as pil_img:
                    pil_img = ImageOps.exif_transpose(pil_img) or pil_img
                    img = cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)
                    if img is not None and img.size:
                        return img
            except Exception:
                pass
            img = cv2.imread(file_path)
            if img is None:
                pil_img = Image.open(file_path).convert("RGB")
                img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            return img

    def count_pdf_pages(self, file_path: str) -> int:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf" and PDF_SUPPORT:
            pdf = pdfium.PdfDocument(file_path)
            return len(pdf)
        return 1

    def detect_paper_quad(self, img: np.ndarray) -> Optional[np.ndarray]:
        h, w = img.shape[:2]
        # Resize for fast contour search
        scale = 800.0 / max(h, w)
        small = cv2.resize(img, (0, 0), fx=scale, fy=scale)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

        # Smooth and edge detect
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edged = cv2.Canny(blurred, 30, 120)

        # Dilate to close small gaps
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        closed = cv2.morphologyEx(edged, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]

        img_area = small.shape[0] * small.shape[1]

        for c in contours:
            area = cv2.contourArea(c)
            # Must occupy at least 65% of frame to be the full paper sheet.
            if area < img_area * 0.65:
                continue

            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.02 * peri, True)

            if len(approx) == 4:
                # Also check bounding rect covers top and bottom (not just inner table)
                x, y, bw, bh = cv2.boundingRect(approx)
                if bh < small.shape[0] * 0.80 or bw < small.shape[1] * 0.60:
                    continue

                # Scale corners back to original image coordinates
                pts = approx.reshape(4, 2) / scale
                return self.order_points(pts)

        return None

    @staticmethod
    def order_points(pts: np.ndarray) -> np.ndarray:
        # Sort points in order: top-left, top-right, bottom-right, bottom-left
        rect = np.zeros((4, 2), dtype="float32")
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]

        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]
        return rect

    def warp_perspective(self, img: np.ndarray, rect: np.ndarray) -> np.ndarray:
        (tl, tr, br, bl) = rect
        # Compute width
        width_a = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
        width_b = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
        height_a = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
        height_b = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
        max_width = max(int(width_a), int(width_b), 400)
        max_height = max(int(height_a), int(height_b), 400)

        dst = np.array([
            [0, 0],
            [max_width - 1, 0],
            [max_width - 1, max_height - 1],
            [0, max_height - 1]
        ], dtype="float32")

        matrix = cv2.getPerspectiveTransform(rect, dst)
        warped = cv2.warpPerspective(img, matrix, (max_width, max_height), flags=cv2.INTER_LANCZOS4)
        return self.limit_size(warped, max_side=2000)

    @staticmethod
    def limit_size(img: np.ndarray, max_side: int = 1800) -> np.ndarray:
        h, w = img.shape[:2]
        longest = max(h, w)
        if longest <= max_side or longest == 0:
            return img
        scale = max_side / float(longest)
        return cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    def detect_skew_angle(self, gray: np.ndarray) -> float:
        h, w = gray.shape[:2]
        # Look at horizontal table lines or barcode lines in center 60%
        center_crop = gray[int(h * 0.15):int(h * 0.85), int(w * 0.1):int(w * 0.9)]
        edges = cv2.Canny(center_crop, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100, minLineLength=w * 0.2, maxLineGap=20)

        if lines is None:
            return 0.0

        angles = []
        for x1, y1, x2, y2 in lines.reshape(-1, 4):
            dx = float(x2 - x1)
            dy = float(y2 - y1)
            if abs(dx) > 1e-4:
                angle_deg = np.degrees(np.arctan2(dy, dx))
                # Only consider near-horizontal lines (-30 to +30 degrees)
                if abs(angle_deg) < 30:
                    angles.append(angle_deg)

        if not angles:
            return 0.0

        median_angle = float(np.median(angles))
        return median_angle

    def deskew_image(self, img: np.ndarray, angle: float) -> np.ndarray:
        if abs(angle) < 0.2:
            return img
        h, w = img.shape[:2]
        center = (w // 2, h // 2)
        rot_mat = cv2.getRotationMatrix2D(center, angle, 1.0)
        deskewed = cv2.warpAffine(
            img,
            rot_mat,
            (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE
        )
        return deskewed

    def enhance_contrast_and_denoise(self, img: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        # Convert to LAB color space for illumination normalization
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)

        # Estimate background illumination using large morphological kernel
        kernel_size = 41
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
        background = cv2.morphologyEx(l_channel, cv2.MORPH_DILATE, kernel)
        background = cv2.GaussianBlur(background, (21, 21), 0)

        # Subtract background gradient and normalize
        diff = cv2.subtract(background, l_channel)
        diff = cv2.bitwise_not(diff)
        norm_l = cv2.normalize(diff, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX)

        # Apply CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced_l = clahe.apply(norm_l)

        # Merge back to BGR
        enhanced_lab = cv2.merge([enhanced_l, a_channel, b_channel])
        enhanced_bgr = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)

        # Denoise with fast bilateral filter to preserve text edges
        denoised = cv2.bilateralFilter(enhanced_bgr, d=5, sigmaColor=35, sigmaSpace=35)

        # Generate binarized image for OCR assistance
        gray = cv2.cvtColor(denoised, cv2.COLOR_BGR2GRAY)
        binary = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            25,
            11
        )

        return denoised, binary

    def header_bar_score(self, img: np.ndarray) -> float:
        """How much of the top strip is a solid IEC colour bar, not scattered logos."""
        h, w = img.shape[:2]
        strip = img[: max(8, int(h * 0.12)), :]
        hsv = cv2.cvtColor(strip, cv2.COLOR_BGR2HSV)
        # Phone photos wash the Provincial pink/red bar; keep orange/blue strict
        # so warm table paper is not mistaken for a header.
        ranges = [
            (np.array([0, 50, 80]), np.array([8, 255, 255])),
            (np.array([170, 50, 80]), np.array([180, 255, 255])),
            (np.array([145, 70, 80]), np.array([175, 255, 255])),
            (np.array([8, 130, 90]), np.array([22, 255, 255])),
            (np.array([95, 80, 70]), np.array([130, 255, 255])),
        ]
        best = 0.0
        for lo, hi in ranges:
            mask = cv2.inRange(hsv, lo, hi)
            if mask.size == 0:
                continue
            frac = (mask > 0).mean(axis=1)
            if len(frac):
                smooth = np.convolve(frac, np.ones(3) / 3.0, mode="same")
                best = max(best, float(np.max(smooth)))
        return best

    def _rotation_to_portrait(self, img: np.ndarray) -> Tuple[np.ndarray, int]:
        """Quarter-turns only. Landscape phone pixels become portrait."""
        h, w = img.shape[:2]
        if w <= h:
            return img, 0
        cw = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        ccw = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        if self._header_delta(cw) >= self._header_delta(ccw):
            return cw, 90
        return ccw, 270

    def upright_orientation(self, img: np.ndarray) -> np.ndarray:
        """Rotate phone photos so the coloured header bar sits at the top."""
        oriented, _ = self._upright_with_degrees(img)
        return oriented

    def _header_delta(self, img: np.ndarray) -> float:
        """Positive when the IEC colour bar is at the top rather than the bottom."""
        top = self.header_bar_score(img)
        bottom = self.header_bar_score(cv2.rotate(img, cv2.ROTATE_180))
        return top - bottom

    def _upright_with_degrees(self, img: np.ndarray) -> Tuple[np.ndarray, int]:
        portrait, deg = self._rotation_to_portrait(img)
        delta = self._header_delta(portrait)
        bottom = self.header_bar_score(cv2.rotate(portrait, cv2.ROTATE_180))
        # Only commit to a 180 flip when the header is clearly at the bottom.
        if delta <= -0.08 and bottom >= 0.12:
            return cv2.rotate(portrait, cv2.ROTATE_180), (deg + 180) % 360
        return portrait, deg

    def process_image(
        self,
        img: np.ndarray,
        debug_dir: Optional[str] = None,
    ) -> ImageEnhancementResult:
        t0 = time.time()
        if debug_dir:
            os.makedirs(debug_dir, exist_ok=True)
            cv2.imwrite(os.path.join(debug_dir, "01_loaded.jpg"), img)

        img, rotation_degrees = self._upright_with_degrees(img)
        raw_h, raw_w = img.shape[:2]
        if debug_dir:
            cv2.imwrite(os.path.join(debug_dir, "02_upright.jpg"), img)

        # Step 1: Detect Paper Boundary & Perspective Transform
        quad = self.detect_paper_quad(img)
        is_perspective_corrected = False
        if quad is not None:
            processed = self.warp_perspective(img, quad)
            is_perspective_corrected = True
        else:
            processed = img.copy()
        if debug_dir:
            cv2.imwrite(os.path.join(debug_dir, "03_perspective.jpg"), processed)

        processed = self.limit_size(processed, max_side=1800)

        # Step 2: Deskew
        gray_temp = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
        skew_angle = self.detect_skew_angle(gray_temp)
        if abs(skew_angle) >= 0.2:
            processed = self.deskew_image(processed, skew_angle)
        if debug_dir:
            cv2.imwrite(os.path.join(debug_dir, "04_deskewed.jpg"), processed)

        # Step 3: Illumination correction, local contrast enhancement, and denoising
        enhanced, binary = self.enhance_contrast_and_denoise(processed)
        if debug_dir:
            cv2.imwrite(os.path.join(debug_dir, "05_enhanced.jpg"), enhanced)
            cv2.imwrite(os.path.join(debug_dir, "06_binary.jpg"), binary)

        t1 = time.time()
        enh_h, enh_w = enhanced.shape[:2]

        return ImageEnhancementResult(
            enhanced_image=enhanced,
            binary_image=binary,
            skew_angle=round(skew_angle, 2),
            is_perspective_corrected=is_perspective_corrected,
            elapsed_seconds=round(t1 - t0, 3),
            raw_width=raw_w,
            raw_height=raw_h,
            enhanced_width=enh_w,
            enhanced_height=enh_h,
            rotation_degrees=rotation_degrees,
        )

    def save_results(
        self,
        enh_res: ImageEnhancementResult,
        enhanced_out_path: str,
        thumb_out_path: Optional[str] = None
    ):
        os.makedirs(os.path.dirname(enhanced_out_path), exist_ok=True)
        cv2.imwrite(enhanced_out_path, enh_res.enhanced_image, [cv2.IMWRITE_JPEG_QUALITY, 92])

        if thumb_out_path:
            os.makedirs(os.path.dirname(thumb_out_path), exist_ok=True)
            h, w = enh_res.enhanced_image.shape[:2]
            thumb_w = 400
            thumb_h = int(h * (thumb_w / float(w)))
            thumb = cv2.resize(enh_res.enhanced_image, (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)
            cv2.imwrite(thumb_out_path, thumb, [cv2.IMWRITE_JPEG_QUALITY, 85])
