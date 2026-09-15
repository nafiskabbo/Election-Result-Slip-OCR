/**
 * Interactive Synchronized Image Viewer
 * Supports Smooth Pan, Zoom (50% - 400%), Rotate, and Bounding Box Overlays
 */
class SlipImageViewer {
  constructor(containerId, imgId, overlayId) {
    this.container = document.getElementById(containerId);
    this.img = document.getElementById(imgId);
    this.overlay = document.getElementById(overlayId);

    this.scale = 1.0;
    this.panX = 0;
    this.panY = 0;
    this.rotation = 0;
    this.isDragging = false;
    this.startX = 0;
    this.startY = 0;

    this.initEvents();
  }

  initEvents() {
    if (!this.container || !this.img) return;

    // Mouse Drag Pan
    this.container.addEventListener("mousedown", (e) => {
      this.isDragging = true;
      this.startX = e.clientX - this.panX;
      this.startY = e.clientY - this.panY;
      this.container.style.cursor = "grabbing";
    });

    window.addEventListener("mousemove", (e) => {
      if (!this.isDragging) return;
      this.panX = e.clientX - this.startX;
      this.panY = e.clientY - this.startY;
      this.applyTransform();
    });

    window.addEventListener("mouseup", () => {
      this.isDragging = false;
      if (this.container) this.container.style.cursor = "grab";
    });

    // Mouse Wheel Zoom
    this.container.addEventListener("wheel", (e) => {
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.15 : 0.85;
      this.zoom(zoomFactor, e.clientX, e.clientY);
    }, { passive: false });

    // Touch Support for Mobile Pan
    let lastTouch = null;
    this.container.addEventListener("touchstart", (e) => {
      if (e.touches.length === 1) {
        lastTouch = e.touches[0];
        this.startX = lastTouch.clientX - this.panX;
        this.startY = lastTouch.clientY - this.panY;
      }
    });

    this.container.addEventListener("touchmove", (e) => {
      if (e.touches.length === 1 && lastTouch) {
        e.preventDefault();
        const touch = e.touches[0];
        this.panX = touch.clientX - this.startX;
        this.panY = touch.clientY - this.startY;
        this.applyTransform();
      }
    }, { passive: false });

    this.container.addEventListener("touchend", () => {
      lastTouch = null;
    });
  }

  zoom(factor) {
    const newScale = this.scale * factor;
    if (newScale >= 0.4 && newScale <= 4.5) {
      this.scale = newScale;
      this.applyTransform();
    }
  }

  rotate() {
    this.rotation = (this.rotation + 90) % 360;
    this.applyTransform();
  }

  reset() {
    this.scale = 1.0;
    this.panX = 0;
    this.panY = 0;
    this.rotation = 0;
    this.applyTransform();
    this.clearHighlight();
  }

  fit() {
    if (!this.container || !this.img.naturalWidth) return;
    const cW = this.container.clientWidth;
    const cH = this.container.clientHeight;
    const iW = this.img.naturalWidth;
    const iH = this.img.naturalHeight;

    const scaleW = (cW - 40) / iW;
    const scaleH = (cH - 40) / iH;
    this.scale = Math.min(scaleW, scaleH, 1.2);
    this.panX = 0;
    this.panY = 0;
    this.applyTransform();
  }

  applyTransform() {
    const transform = `translate(${this.panX}px, ${this.panY}px) scale(${this.scale}) rotate(${this.rotation}deg)`;
    if (this.img) this.img.style.transform = transform;
    if (this.overlay) this.overlay.style.transform = transform;
  }

  loadImage(src) {
    if (!this.img) return;
    this.img.src = src;
    this.img.onload = () => {
      this.fit();
    };
  }

  highlightBBox(bbox) {
    if (!this.overlay || !bbox || !this.img.naturalWidth) {
      this.clearHighlight();
      return;
    }

    // Natural image coordinates to percentage or overlay coordinates
    const natW = this.img.naturalWidth;
    const natH = this.img.naturalHeight;

    const left = (bbox.x / natW) * 100;
    const top = (bbox.y / natH) * 100;
    const width = (bbox.width / natW) * 100;
    const height = (bbox.height / natH) * 100;

    this.overlay.innerHTML = `
      <div style="
        position: absolute;
        left: ${left}%;
        top: ${top}%;
        width: ${width}%;
        height: ${height}%;
        border: 2px solid #ef4444;
        background: rgba(239, 68, 68, 0.2);
        pointer-events: none;
        box-shadow: 0 0 8px rgba(239, 68, 68, 0.6);
        border-radius: 2px;
      "></div>
    `;
  }

  clearHighlight() {
    if (this.overlay) {
      this.overlay.innerHTML = "";
    }
  }
}
