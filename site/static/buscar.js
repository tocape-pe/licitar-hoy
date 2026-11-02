/* Buscador de Licitar Hoy. build.py genera /buscar/indice.json (solo avisos vigentes) y
   aquí se filtra en el navegador: GitHub Pages no tiene servidor.
   - Busca sin mayúsculas ni tildes; cada palabra escrita tiene que aparecer.
   - Orden: consultas abiertas que cierran antes, luego consultas ya cerradas, luego sin plazo.
   - La tarjeta repite el marcado de templates/_tarjeta.html: si cambia una, cambiar la otra. */
(function () {
  'use strict';
  var form = document.querySelector('[data-buscador]');
  if (!form) return;
  var modo = form.dataset.modo;
  var base = form.dataset.base || '';
  var zona = document.getElementById('b-zona');
  var estado = document.getElementById('b-estado');
  var lista = document.getElementById('b-resultados');
  var mas = document.getElementById('b-mas');
  var nivel = lista.dataset.nivel || '3';
  var POR_TANDA = modo === 'portada' ? 6 : 50;
  var DIAS_URGENTE = 3;
  var MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre',
               'octubre', 'noviembre', 'diciembre'];
  var DIAS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
  var VACIAS = {};
  'de la el los las del en y a al para por con o u e su sus que se un una n nro'.split(' ')
    .forEach(function (w) { VACIAS[w] = true; });
  // Fecha de hoy en Lima (UTC-5, sin horario de verano)
  var HOY = new Date(Date.now() - 5 * 3600e3).toISOString().slice(0, 10);

  var datos = null, cargando = null, encontrados = [], mostrados = 0, espera = 0;

  function sinTildes(s) {
    return String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  }

  // "Computadoras, AREQUIPA" -> ["computadora", "arequipa"]. El plural se recorta para que
  // "camiones" encuentre "camion" y "computadoras" encuentre "computadora".
  function terminos(q) {
    return sinTildes(q).split(/\s+/).map(function (t) {
      t = t.replace(/^[^a-z0-9]+|[^a-z0-9]+$/g, '');
      if (/[^aeiou]es$/.test(t) && t.length > 5) return t.slice(0, -2);
      if (/s$/.test(t) && t.length > 4) return t.slice(0, -1);
      return t;
    }).filter(function (t) { return t && !VACIAS[t]; });
  }

  function cargar() {
    if (!cargando) {
      cargando = fetch(form.dataset.indice).then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      }).then(function (j) {
        var c = {};
        j.campos.forEach(function (nombre, i) { c[nombre] = i; });
        var nombreObjeto = j.objetos;
        datos = {deps: j.deps, objetos: nombreObjeto, avisos: j.avisos.map(function (f, i) {
          var a = {slug: f[c.slug], e: f[c.entidad], c: f[c.que], m: f[c.monto], o: f[c.objeto], t: f[c.tipo],
                   d: f[c.dep], fin: f[c.consultas_fin], n: f[c.nomenclatura], v: f[c.convocatoria], i: i};
          a.texto = sinTildes([a.e, a.c, a.n, j.deps[a.d], a.o, a.t, f[c.palabras]].join(' '));
          return a;
        })};
        return datos;
      });
      cargando.catch(function () {
        cargando = null;
        mostrarZona(true);
        estado.textContent = 'No se pudo cargar el buscador. Revisa tu conexión y vuelve a intentarlo.';
      });
    }
    return cargando;
  }

  function dias(fin) {
    return fin ? Math.round((Date.parse(fin) - Date.parse(HOY)) / 864e5) : null;
  }

  function fechaCorta(fin) {
    return Number(fin.slice(8, 10)) + ' de ' + MESES[Number(fin.slice(5, 7)) - 1];
  }

  // Igual que consultas_texto() de build.py
  function consultasTexto(d, fin) {
    if (d === null) return '';
    if (d < 0) return 'Consultas cerradas el ' + fechaCorta(fin);
    if (d === 0) return 'Consultas hasta hoy';
    if (d === 1) return 'Consultas hasta mañana';
    if (d <= 7) return 'Consultas hasta el ' + DIAS[new Date(fin + 'T12:00:00Z').getUTCDay()] + ' ' + fechaCorta(fin);
    return 'Consultas hasta el ' + fechaCorta(fin);
  }

  function el(tag, clase, texto) {
    var n = document.createElement(tag);
    if (clase) n.className = clase;
    if (texto) n.textContent = texto;
    return n;
  }

  function tarjeta(a) {
    var art = el('article', 'tarjeta');
    art.appendChild(el('p', 't-entidad', a.e));
    var h = el('h' + nivel, 't-que');
    var enlace = el('a', null, a.c.charAt(0).toUpperCase() + a.c.slice(1));
    enlace.href = base + '/licitacion/' + a.slug + '/';
    h.appendChild(enlace);
    art.appendChild(h);
    var fila = el('p', 't-datos');
    fila.appendChild(a.m ? el('strong', 't-monto', a.m) : el('span', 't-monto t-sin', 'Monto no publicado'));
    fila.appendChild(el('span', 't-tipo', (a.o || 'Contratación') + ' · ' + a.t));
    fila.appendChild(el('span', 't-lugar', datos.deps[a.d]));
    art.appendChild(fila);
    var plazo = el('p', 't-plazo');
    var d = dias(a.fin), txt = consultasTexto(d, a.fin);
    if (txt) {
      var t = el('time', 't-cierre' + (d >= 0 && d <= DIAS_URGENTE ? ' urgente' : ''), txt);
      t.dateTime = a.fin;
      plazo.appendChild(t);
    }
    if (a.v >= 2) plazo.appendChild(el('span', 't-chip', a.v + '.ª convocatoria'));
    art.appendChild(plazo);
    var ver = el('span', 't-ver', a.n);
    ver.setAttribute('aria-hidden', 'true');
    art.appendChild(ver);
    return art;
  }

  function valores() {
    return {q: form.elements.q.value.trim(), objeto: form.elements.objeto.value, dep: form.elements.dep.value};
  }

  function consulta(v) {
    var p = new URLSearchParams();
    ['q', 'objeto', 'dep'].forEach(function (k) { if (v[k]) p.set(k, v[k]); });
    return p.toString();
  }

  function mostrarZona(si) {
    if (modo === 'portada') zona.hidden = !si;
  }

  function filtrar(v) {
    var ts = terminos(v.q), objeto = datos.objetos[v.objeto] || '';
    var res = datos.avisos.filter(function (a) {
      if (objeto && a.o !== objeto) return false;
      if (v.dep && a.d !== v.dep) return false;
      for (var k = 0; k < ts.length; k++) if (a.texto.indexOf(ts[k]) < 0) return false;
      return true;
    });
    // El plazo se recalcula con la fecha de hoy: el índice pudo generarse ayer.
    function clave(a) {
      var d = dias(a.fin);
      return d === null ? 2 : d < 0 ? 1 : 0;
    }
    return res.sort(function (x, y) {
      var gx = clave(x), gy = clave(y);
      if (gx !== gy) return gx - gy;
      if (gx === 0 && x.fin !== y.fin) return x.fin < y.fin ? -1 : 1;
      return x.i - y.i;
    });
  }

  function pintarTanda() {
    var frag = document.createDocumentFragment();
    encontrados.slice(mostrados, mostrados + POR_TANDA).forEach(function (a) { frag.appendChild(tarjeta(a)); });
    lista.appendChild(frag);
    mostrados = Math.min(encontrados.length, mostrados + POR_TANDA);
    mas.hidden = mostrados >= encontrados.length;
  }

  function buscar() {
    var v = valores();
    var vacia = !v.q && !v.objeto && !v.dep;
    if (modo === 'pagina') history.replaceState(null, '', location.pathname + (vacia ? '' : '?' + consulta(v)));
    if (vacia) {
      mostrarZona(false);
      lista.textContent = '';
      mas.hidden = true;
      estado.textContent = modo === 'pagina' ? 'Escribe qué buscas o elige un tipo o un departamento.' : '';
      return;
    }
    mostrarZona(true);
    if (!datos) estado.textContent = 'Cargando las licitaciones…';
    cargar().then(function () {
      if (consulta(valores()) !== consulta(v)) return;  // ya escribió otra cosa
      encontrados = filtrar(v);
      mostrados = 0;
      lista.textContent = '';
      var n = encontrados.length;
      estado.textContent = n === 0
        ? 'Ninguna licitación vigente coincide' + (v.q ? ' con «' + v.q + '»' : '') + '. Prueba con menos palabras o quita un filtro.'
        : n === 1 ? '1 licitación vigente encontrada.'
        : n.toLocaleString('es-PE') + ' licitaciones vigentes encontradas.';
      if (modo === 'portada') {
        encontrados.slice(0, POR_TANDA).forEach(function (a) { lista.appendChild(tarjeta(a)); });
        mas.hidden = n <= POR_TANDA;
        var enlace = mas.querySelector('a');
        enlace.href = base + '/buscar/?' + consulta(v);
        enlace.textContent = 'Ver las ' + n.toLocaleString('es-PE') + ' licitaciones encontradas';
      } else {
        pintarTanda();
      }
    }).catch(function () {});  // el aviso de error ya lo puso cargar()
  }

  function alEscribir() {
    clearTimeout(espera);
    espera = setTimeout(buscar, 120);
  }

  form.elements.q.addEventListener('input', alEscribir);
  form.elements.q.addEventListener('focus', cargar, {once: true});
  form.elements.objeto.addEventListener('change', buscar);
  form.elements.dep.addEventListener('change', buscar);
  form.addEventListener('submit', function (ev) {
    var v = valores();
    ev.preventDefault();
    if (modo === 'portada') {
      location.href = base + '/buscar/' + (consulta(v) ? '?' + consulta(v) : '');
    } else {
      clearTimeout(espera);
      buscar();
      form.elements.q.blur();  // en el celular, cierra el teclado para ver los resultados
    }
  });
  if (modo === 'pagina') {
    mas.querySelector('button').addEventListener('click', pintarTanda);
    var p = new URLSearchParams(location.search);
    form.elements.q.value = p.get('q') || '';
    form.elements.objeto.value = p.get('objeto') || '';
    form.elements.dep.value = p.get('dep') || '';
    if (form.elements.objeto.selectedIndex < 0) form.elements.objeto.value = '';
    if (form.elements.dep.selectedIndex < 0) form.elements.dep.value = '';
    buscar();
    if (!form.elements.q.value) form.elements.q.focus();
  } else {
    // Al volver atrás desde una ficha, el navegador restaura lo escrito: se repite la búsqueda.
    window.addEventListener('pageshow', function () { if (consulta(valores())) buscar(); });
  }
})();
