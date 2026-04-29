(function () {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const canvas = document.getElementById("matrix-wallpaper");
  const layers = Array.from(document.querySelectorAll("[data-depth]"));
  let animationFrame = 0;
  let matrixFrame = 0;
  let width = 0;
  let height = 0;
  let columns = [];

  function resizeMatrix() {
    if (!canvas) return;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = Math.floor(width * ratio);
    canvas.height = Math.floor(height * ratio);
    canvas.style.width = width + "px";
    canvas.style.height = height + "px";

    const context = canvas.getContext("2d");
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    const count = Math.ceil(width / 18);
    columns = Array.from({ length: count }, () => Math.random() * -height);
  }

  function drawMatrix() {
    if (!canvas || reduceMotion.matches) return;
    const context = canvas.getContext("2d");
    const glyphs = "01#/[]{}<>CONSENTTERMSDATA";
    context.fillStyle = "rgba(5, 5, 5, 0.13)";
    context.fillRect(0, 0, width, height);
    context.font = "14px Courier New, monospace";
    context.fillStyle = "rgba(235, 235, 230, 0.32)";

    columns.forEach((y, index) => {
      const glyph = glyphs[Math.floor(Math.random() * glyphs.length)];
      const x = index * 18;
      context.fillText(glyph, x, y);
      columns[index] = y > height + Math.random() * 1200 ? Math.random() * -160 : y + 16;
    });

    matrixFrame = window.requestAnimationFrame(drawMatrix);
  }

  function updateParallax() {
    if (reduceMotion.matches) return;
    const scrollY = window.scrollY || window.pageYOffset;
    layers.forEach((layer) => {
      const depth = Number(layer.dataset.depth || 0);
      layer.style.transform = `translate3d(0, ${scrollY * depth}px, 0)`;
    });
    animationFrame = 0;
  }

  function requestParallax() {
    if (!animationFrame) {
      animationFrame = window.requestAnimationFrame(updateParallax);
    }
  }

  function start() {
    if (reduceMotion.matches) {
      if (canvas) canvas.setAttribute("hidden", "");
      return;
    }
    if (canvas) canvas.removeAttribute("hidden");
    resizeMatrix();
    drawMatrix();
    updateParallax();
  }

  window.addEventListener("resize", resizeMatrix);
  window.addEventListener("scroll", requestParallax, { passive: true });
  reduceMotion.addEventListener("change", () => {
    window.cancelAnimationFrame(matrixFrame);
    window.cancelAnimationFrame(animationFrame);
    animationFrame = 0;
    matrixFrame = 0;
    start();
  });

  start();
})();
