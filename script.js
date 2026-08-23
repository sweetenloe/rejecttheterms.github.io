(function () {
  const consentHero = document.querySelector('#consentHero');
  const confirmation = document.querySelector('#dataConfirmation');
  const publication = document.querySelector('#publication');
  const choiceBar = document.querySelector('#choiceBar');
  const rejectBtn = document.querySelector('#rejectBtn');
  const acceptBtn = document.querySelector('#acceptBtn');
  const termsScroll = document.querySelector('#termsScroll');
  const scrollDownBtn = document.querySelector('#scrollDownBtn');
  let swapped = false;
  let accepted = false;

  function showPublication() {
    if (!publication) return;
    if (consentHero) consentHero.hidden = true;
    if (confirmation) confirmation.hidden = true;
    publication.hidden = false;
    document.body.classList.add('has-entered');
    try { sessionStorage.setItem('reject-the-terms-entered', 'true'); } catch (error) {}
    window.scrollTo(0, 0);
  }

  if (publication) {
    try {
      if (sessionStorage.getItem('reject-the-terms-entered') === 'true') showPublication();
    } catch (error) {}
  }

  if (scrollDownBtn && termsScroll) {
    scrollDownBtn.addEventListener('click', () => termsScroll.scrollTo({ top: termsScroll.scrollHeight, behavior: 'smooth' }));
  }

  function swapButtons() {
    if (accepted || !choiceBar) return;
    swapped = !swapped;
    choiceBar.classList.toggle('is-swapped', swapped);
    choiceBar.insertBefore(swapped ? acceptBtn : rejectBtn, swapped ? rejectBtn : acceptBtn);
  }

  function blockReject(event) {
    event.preventDefault();
    event.stopPropagation();
    swapButtons();
  }

  if (rejectBtn) {
    rejectBtn.addEventListener('pointerenter', swapButtons);
    rejectBtn.addEventListener('pointerdown', blockReject);
    rejectBtn.addEventListener('click', blockReject);
    rejectBtn.addEventListener('focus', swapButtons);
    rejectBtn.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') blockReject(event);
    });
  }

  if (acceptBtn) {
    acceptBtn.addEventListener('click', () => {
      if (accepted) return;
      accepted = true;
      consentHero.hidden = true;
      confirmation.hidden = false;
      confirmation.focus({ preventScroll: true });
      window.scrollTo(0, 0);
    });
  }

  if (confirmation) {
    confirmation.addEventListener('click', showPublication);
    confirmation.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        showPublication();
      }
    });
  }
})();

(function () {
  const hero = document.querySelector('.article-hero');
  if (!hero || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  let framePending = false;

  function updateArticleHero() {
    const progress = Math.min(Math.max(window.scrollY / Math.max(hero.offsetHeight, 1), 0), 1);
    const scale = 1.18 - (progress * 0.18);
    const blur = progress * 10;
    const opacity = 1 - (progress * 0.28);

    hero.style.setProperty('--article-hero-scale', scale.toFixed(3));
    hero.style.setProperty('--article-hero-blur', `${blur.toFixed(2)}px`);
    hero.style.setProperty('--article-hero-opacity', opacity.toFixed(3));
    framePending = false;
  }

  function requestArticleHeroUpdate() {
    if (framePending) return;
    framePending = true;
    window.requestAnimationFrame(updateArticleHero);
  }

  updateArticleHero();
  window.addEventListener('scroll', requestArticleHeroUpdate, { passive: true });
  window.addEventListener('resize', requestArticleHeroUpdate);
})();
