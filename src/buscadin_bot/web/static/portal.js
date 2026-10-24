// Progressive enhancement only. Jobs and forms already work without JavaScript.
// Keep the first results close to the top on phones; native <details> remains
// keyboard-accessible and the user controls it after this initial adjustment.
const filters = document.querySelector('.filters');
if (filters && window.matchMedia('(max-width: 680px)').matches) {
  filters.open = false;
}
