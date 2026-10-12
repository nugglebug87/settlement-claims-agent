'use strict';
let installPrompt;
const installed = () => window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
const installButton = document.querySelector('#install-app');
installButton.hidden = installed();
window.addEventListener('beforeinstallprompt', event => {
  event.preventDefault();
  installPrompt = event;
  if (!installed()) installButton.hidden = false;
});
window.addEventListener('appinstalled', () => {
  installPrompt = null;
  installButton.hidden = true;
});
installButton.addEventListener('click', async () => {
  if (installPrompt) {
    const prompt = installPrompt;
    installPrompt = null;
    await prompt.prompt();
    await prompt.userChoice;
    return;
  }
  modal('Install Settlement Assistant', `<p>Add the app to your phone’s home screen, then open it using its icon.</p><h3>iPhone or iPad</h3><p>Open this website in Safari. Tap <strong>Share</strong>, choose <strong>Add to Home Screen</strong>, then tap <strong>Add</strong>.</p><h3>Android</h3><p>Open this website in Chrome. Tap the <strong>⋮ menu</strong>, then <strong>Install app</strong> or <strong>Add to Home screen</strong>. Confirm the installation.</p><h3>On your PC</h3><p>Open this website in Chrome or Edge and use the browser’s install option in the address bar or menu.</p><p class="finder-help">An internet connection and your existing workspace sign-in are required. Installation does not sign or submit any claim.</p>`);
});
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js', {scope:'/', updateViaCache:'none'}).catch(() => {
    // Browser-menu installation remains available where supported.
  });
}
