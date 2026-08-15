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
