const menuButton = document.querySelector('.menu-toggle');
const mobileNav = document.querySelector('.mobile-nav');
if (menuButton) menuButton.addEventListener('click', () => mobileNav.classList.toggle('open'));

const searchForm = document.querySelector('.search-form');
const searchInput = searchForm?.querySelector('input');
const searchButton = searchForm?.querySelector('button');
if (searchForm && searchInput && searchButton) {
  searchButton.addEventListener('click', (event) => {
    if (window.matchMedia('(max-width: 600px)').matches && !searchForm.classList.contains('search-open')) {
      event.preventDefault();
      searchForm.classList.add('search-open');
      searchInput.focus();
    } else if (searchInput.value.trim()) {
      searchForm.submit();
    }
  });
}

for (const card of document.querySelectorAll('.movie-card')) {
  card.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') card.click();
  });
}
