document.addEventListener('DOMContentLoaded', () => {
  const hero = document.querySelector('[data-featured]');
  if (hero) {
    const slides = [...hero.querySelectorAll('.hero-slide')];
    const dots = [...hero.querySelectorAll('.hero-dot')];
    const previous = hero.querySelector('[data-hero-prev]');
    const next = hero.querySelector('[data-hero-next]');
    let current = 0;
    let timer;
    let touchStartX = 0;
    let touchStartY = 0;

    const show = (index) => {
      slides[current]?.classList.remove('is-active');
      dots[current]?.classList.remove('is-active');
      current = (index + slides.length) % slides.length;
      slides[current]?.classList.add('is-active');
      dots[current]?.classList.add('is-active');
    };
    const restartTimer = () => {
      window.clearInterval(timer);
      if (slides.length > 1) timer = window.setInterval(() => show(current + 1), 5500);
    };
    const move = (index) => { show(index); restartTimer(); };
    dots.forEach((dot, index) => dot.addEventListener('click', () => move(index)));
    previous?.addEventListener('click', () => move(current - 1));
    next?.addEventListener('click', () => move(current + 1));
    hero.addEventListener('touchstart', (event) => {
      touchStartX = event.changedTouches[0].clientX;
      touchStartY = event.changedTouches[0].clientY;
    }, { passive: true });
    hero.addEventListener('touchend', (event) => {
      const deltaX = event.changedTouches[0].clientX - touchStartX;
      const deltaY = event.changedTouches[0].clientY - touchStartY;
      if (Math.abs(deltaX) > 45 && Math.abs(deltaX) > Math.abs(deltaY)) move(current + (deltaX < 0 ? 1 : -1));
    }, { passive: true });
    restartTimer();
  }

  const metadataButton = document.querySelector('#generate-metadata');
  if (metadataButton) {
    metadataButton.addEventListener('click', async () => {
      const title = document.querySelector('[name="title"]')?.value.trim();
      const status = document.querySelector('#metadata-status');
      if (!title) { status.textContent = 'Enter a title first.'; return; }
      metadataButton.disabled = true;
      status.textContent = 'Checking local references...';
      try {
        const response = await fetch(`${window.metadataEndpoint}?title=${encodeURIComponent(title)}`);
        const result = await response.json();
        if (!result.found) { status.textContent = result.message; return; }
        Object.entries(result.metadata).forEach(([field, value]) => {
          const input = document.querySelector(`[name="${field}"]`);
          if (input && !input.value.trim()) input.value = value;
        });
        status.textContent = 'Empty fields were filled. Your existing entries were kept.';
      } catch (error) {
        status.textContent = 'Metadata is unavailable. You can continue manually.';
      } finally { metadataButton.disabled = false; }
    });
  }
});
