function showModal(html) {
  document.getElementById('modal-box').innerHTML = html;
  document.getElementById('modal-box').classList.add('open');
  document.getElementById('modal-overlay').classList.add('open');
}

function closeModal() {
  document.getElementById('modal-box').classList.remove('open');
  document.getElementById('modal-overlay').classList.remove('open');
}

document.getElementById('modal-overlay').addEventListener('click', closeModal);
