/* Tema claro u oscuro, compartido por el panel y el login.
   Se carga en <head> para aplicar el tema guardado antes de pintar. */
(function () {
    try {
        var t = localStorage.getItem('tema');
        if (t) document.documentElement.dataset.theme = t;
    } catch (e) { /* sin almacenamiento */ }
})();

function temaClaroActivo() {
    var raiz = document.documentElement;
    return raiz.dataset.theme === 'light'
        || (!raiz.dataset.theme && matchMedia('(prefers-color-scheme: light)').matches);
}

function etiquetarBotonTema() {
    var boton = document.getElementById('theme-toggle');
    if (boton) boton.setAttribute('aria-label', temaClaroActivo() ? 'Cambiar a tema oscuro' : 'Cambiar a tema claro');
}

function alternarTema() {
    document.documentElement.dataset.theme = temaClaroActivo() ? 'dark' : 'light';
    try { localStorage.setItem('tema', document.documentElement.dataset.theme); } catch (e) { /* sin almacenamiento */ }
    etiquetarBotonTema();
}

document.addEventListener('DOMContentLoaded', etiquetarBotonTema);
