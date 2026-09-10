const menuButton = document.querySelector('.menu-toggle');
const mobileNav = document.querySelector('.mobile-nav');
if (menuButton) menuButton.addEventListener('click', () => mobileNav.classList.toggle('open'));

for (const card of document.querySelectorAll('.movie-card')) {
  card.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') card.click();
  });
}
