function bindDarkModeForm() {
  var darkModeForm = document.getElementById('dark-mode-settings');
  if (fetch !== undefined) {
    darkModeForm.addEventListener('submit', function(e) {
      e.preventDefault();
      var data = new FormData(darkModeForm);
      if (e.submitter) {
        data.set('mode', e.submitter.getAttribute('value'));
      }

      fetch(darkModeForm.getAttribute('action'),
        {method: 'post', body: data, redirect: 'manual'})
        .then(function(response) {
          console.log(response);
        });

      document.body.setAttribute('data-dark-mode', data.get('mode'));
    });
  }
}

$(document).ready(bindDarkModeForm);
