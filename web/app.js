/* Busqueda de alquiler — front vanilla. Sin framework, sin build step, sin servidor
   obligatorio. Los datos vienen de data.js (window.DATOS), que regenera scripts/build.py.

   DOS MODOS, detectados solos:
     - servido desde localhost (abrir.bat) -> cada accion escribe en data/eventos.jsonl
     - abierto con doble click (file://)   -> localStorage + "Exportar decisiones"

   CONVENCION: cada propiedad tiene un numero corto y estable (#7). Es la manija con la
   que Mario la nombra por chat. Aparece en la card, en la vista Explorar, en el panel y
   en la bitacora. */

(function () {
  "use strict";

  var D = window.DATOS || { avisos: [], descartados: [], eventos: [], resumen: {} };
  var LS_DEC = "alquiler.decisiones";
  var LS_COT = "alquiler.cotizacion";

  /* Cuantas tarjetas se pintan de entrada por seccion. No es paginado: es una primera
     tanda y un boton que AGREGA. Nunca se pierde lo que ya scrolleaste. */
  var TANDA = 60;

  var estado = {
    vista: "favoritos",
    abierto: null,
    limites: {},
    filtros: {
      precioMin: null, precioMax: null, dorm: null, banos: null, m2: null, ext: null,
      barrios: [], tipos: [], estado: "", orden: "default", flags: {}
    }
  };

  // ------------------------------------------------------------- utilidades

  function $(sel) { return document.querySelector(sel); }
  function el(tag, cls, txt) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (txt !== undefined && txt !== null) n.textContent = txt;
    return n;
  }
  function esc(s) {
    return String(s === null || s === undefined ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function num(n) { return n === null || n === undefined ? null : Number(n); }
  function fmt(n) { return n === null || n === undefined ? "-" : Number(n).toLocaleString("es-AR"); }
  function nd(txt) { return '<span class="nd">' + esc(txt || "sin dato") + "</span>"; }

  function decisiones() { try { return JSON.parse(localStorage.getItem(LS_DEC) || "{}"); } catch (e) { return {}; } }
  function guardarDecision(id, dec) {
    var d = decisiones();
    d[id] = dec;
    localStorage.setItem(LS_DEC, JSON.stringify(d));
    pintarPendientes();
  }

  function cotizacion() {
    return Number(localStorage.getItem(LS_COT) || 0) ||
           Number((D.meta_avisos || {}).cotizacion_bna_venta || 0) || null;
  }

  /* EL MODO SE DECIDE POR EL HOST, NO POR EL PROTOCOLO.
     Estaba en `protocol === "http:" || "https:"`, y mientras la pagina solo se abria
     con abrir.bat o con doble click eso alcanzaba: http era el servidor, file era el
     disco. Publicada en GitHub Pages deja de alcanzar y falla del peor modo posible:
     Pages es https, asi que la pagina creeria que hay servidor, mandaria cada descarte
     a /api/evento, recibiria un 404 y la decision se perderia. En un proyecto cuya
     unica regla es "lo peor es mostrar dos veces algo ya descartado", perder descartes
     en silencio es el fallo mas caro que puede tener.
     Solo el servidor local escribe en data/eventos.jsonl, y ese solo vive en localhost. */
  var CON_SERVIDOR = /^(localhost|127\.0\.0\.1|\[::1\]|::1)$/.test(location.hostname);

  function enviarEvento(ev) {
    /* Si el servidor contesta cualquier cosa que no sea ok, la decision NO se descarta:
       se degrada a modo archivo y se guarda local. Un descarte perdido no se recupera. */
    return fetch("/api/evento", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(ev)
    }).then(function (r) {
      return r.json().then(function (j) {
        if (!r.ok || !j.ok) throw new Error(j.error || ("error " + r.status));
        return j;
      });
    });
  }

  var _tostada = null;
  function avisar(txt, clase, accion) {
    if (!_tostada) { _tostada = el("div", "tostada"); document.body.appendChild(_tostada); }
    _tostada.innerHTML = "";
    _tostada.appendChild(el("span", null, txt));
    // El deshacer vive mas que el aviso: una accion de un click necesita vuelta atras.
    var vida = 3200;
    if (accion) {
      var b = el("button", "tostada-accion", accion.texto);
      b.type = "button";
      b.addEventListener("click", function () {
        clearTimeout(_tostada._t);
        _tostada.className = "tostada";
        accion.fn();
      });
      _tostada.appendChild(b);
      vida = 7000;
    }
    _tostada.className = "tostada visible" + (clase ? " " + clase : "");
    clearTimeout(_tostada._t);
    _tostada._t = setTimeout(function () { _tostada.className = "tostada"; }, vida);
  }

  // exterior efectivo, misma regla que score.py: primero el dato estructurado del
  // portal (m2 totales - cubiertos), y solo si no esta, la prosa del aviso.
  function extM2(a) {
    if (a.m2_descubiertos !== null && a.m2_descubiertos !== undefined) return Number(a.m2_descubiertos);
    var items = a.exterior || [], total = 0, hay = false;
    for (var i = 0; i < items.length; i++) {
      if (items[i].m2 === null || items[i].m2 === undefined) continue;
      hay = true;
      total += Number(items[i].m2) * (items[i].descubierto === false ? 0.5 : 1);
    }
    if (!hay && a.exterior_m2_total !== null && a.exterior_m2_total !== undefined) return Number(a.exterior_m2_total);
    return hay ? total : null;
  }

  function extTexto(a) {
    var items = a.exterior || [];
    if (!items.length) return "sin exterior declarado";
    return items.map(function (x) {
      return x.tipo + (x.m2 ? " " + x.m2 + " m²" : "") + (x.descubierto === false ? " (techado)" : "");
    }).join(" + ");
  }

  var ETIQ_ESTADO = {
    a_estrenar: "a estrenar", reciclado: "reciclado", bueno: "bueno",
    cosmetico: "cosmetico", a_refaccionar: "a refaccionar", sin_clasificar: "sin clasificar"
  };
  var RANK_ESTADO = { a_estrenar: 5, reciclado: 4, bueno: 3, sin_clasificar: 2, cosmetico: 0, a_refaccionar: -1 };

  var ETIQ_FALLO = {
    presupuesto: "caro", dormitorios: "pocos dorm", m2_cubiertos: "chico",
    amoblado: "amoblado", mascotas: "sin mascotas", uso: "uso", estado: "estado",
    expensas: "expensas altas", ambientes: "pocos amb", zona: "zona",
    terraza_depto: "sin terraza"
  };

  /* Un filtro duro que no se puede evaluar NO es un filtro que se cumple. 102 de 109
     candidatos pasan el duro de "no amoblado" porque el aviso no lo dice, no porque este
     sin amoblar; y 88 no declaran expensas teniendo un techo de USD 200. Callar eso hace
     que la lista mienta por omision: hay que preguntarlo antes de ir a ver. */
  var ETIQ_INDET = {
    amoblado: "¿amoblado?", expensas: "¿expensas?", mascotas: "¿mascotas?",
    presupuesto: "¿precio?", dormitorios: "¿dorm?", estado: "¿estado?",
    terraza_depto: "¿terraza?"
  };

  /* 106 de 107 candidatos tienen algun duro que NO se pudo evaluar. Poner un chip por
     cada uno seria tapar la card de ambar y, peor, dejar de informar: una senal que se
     enciende en todos no es una senal. Va UNA sola que dice cuantas preguntas hay, y el
     tooltip las enumera. Lo importante no es cual falta sino que hay que preguntar antes
     de perder un sabado yendo a verla. */
  function preguntas(a) {
    return ((a.duros || {}).indeterminados || [])
      .filter(function (x) { return ETIQ_INDET[x.filtro]; })
      .map(function (x) { return ETIQ_INDET[x.filtro].replace(/[¿?]/g, ""); });
  }

  function chipPreguntas(lista) {
    var c = el("span", "tag preguntar", lista.length + (lista.length === 1 ? " a preguntar" : " a preguntar"));
    c.setAttribute("data-tip", "El aviso no aclara: " + lista.join(", ") +
      ". Son filtros tuyos que no se pueden dar por cumplidos.");
    return c;
  }

  function claseEstado(e) {
    if (e === null || e === undefined || e === "sin_clasificar") return "estado-sindatos";
    return "estado-" + e;
  }
  function textoEstado(e) {
    if (e === null || e === undefined) return "sin datos";
    return ETIQ_ESTADO[e] || e;
  }

  function urlMapa(a) {
    return "https://www.google.com/maps/search/?api=1&query=" +
      encodeURIComponent(a.direccion + ", " + (a.barrio || "") + ", CABA, Argentina");
  }
  function urlStreet(a) {
    return "https://www.google.com/maps?q=" +
      encodeURIComponent(a.direccion + ", " + (a.barrio || "") + ", Buenos Aires") + "&layer=c";
  }

  /* Misma logica que procesar() en score.py. Los duros ya vienen calculados en data.js,
     asi que la seccion se puede recomputar en el navegador sin volver a correr nada. */
  function recomputarSeccion(a) {
    if (a.pinned) return "favoritos";
    var d = a.duros || {};
    if (d.pasa) return "candidatos";
    if (d.al_limite) return "al_limite";
    return "filtrados";
  }

  /* EL BUG QUE ESTO ARREGLA: en modo archivo la decision se guardaba en localStorage
     pero el render seguia pintando `a.pinned` tal como venia de data.js. Resultado:
     apagabas un corazon, recargabas, y volvia prendido. El dato nunca se habia perdido
     — simplemente no se leia de vuelta. */
  function aplicarDecisionesLocales() {
    var d = decisiones();
    if (!Object.keys(d).length) return;
    D.avisos.forEach(function (a) {
      var dec = d[a.id];
      if (!dec) return;
      if (dec.accion === "interesa") a.pinned = true;
      else if (dec.accion === "no_favorito") a.pinned = false;
      else if (dec.accion === "descartar") { a.decision = "descartado"; a.pinned = false; }
      // Sin esta linea vuelve el bug del corazon, pero al reves: deshacias un descarte,
      // recargabas, y el descarte volvia. La ultima decision manda, siempre.
      else if (dec.accion === "revivir") a.decision = null;
      else if (dec.accion === "vista_online") a.vista_online = true;
      a.seccion = recomputarSeccion(a);
    });

    /* MISMO BUG, OTRA TABLA. Arriba se reconstruye D.avisos desde localStorage, pero la
       vista Descartados lee D.descartados, que viene tal cual de data.js. Sin esta
       segunda pasada, en modo archivo descartabas algo, recargabas, y la propiedad
       desaparecia de la grilla (bien) pero tampoco figuraba en Descartados (mal): el
       motivo que acababas de escribir no estaba en ningun lado visible. Todo derivado
       tiene que reconstruirse desde la decision, no solo el primero que uno arregla. */
    D.descartados = (D.descartados || []).filter(function (x) {
      var dx = x.id && d[x.id];
      return !(dx && dx.accion === "revivir");
    });
    var yaListados = {};
    D.descartados.forEach(function (x) { if (x.id) yaListados[x.id] = true; });
    Object.keys(d).forEach(function (id) {
      var dec = d[id];
      if (!dec || dec.accion !== "descartar" || yaListados[id]) return;
      var a = porId(id) || {};
      D.descartados.push({
        id: id, direccion: dec.direccion || a.direccion, direccion_norm: a.direccion_norm,
        barrio: dec.barrio || a.barrio, precio_usd: dec.precio_usd || a.precio_total_usd,
        fecha_descarte: dec.fecha, motivo_literal: dec.motivo_literal,
        motivo_literal_verbatim: true, motivo_categorizado: dec.motivo_categorizado || null,
        reversible: true
      });
    });
  }

  var _porId = null;
  function porId(id) {
    if (!_porId) {
      _porId = {};
      D.avisos.forEach(function (a) { _porId[a.id] = a; });
    }
    return _porId[id];
  }

  /* Los 36 descartes de la semilla los anoto Mario por direccion, sin id. Para poder
     revivirlos hay que encontrar el aviso igual que lo hace clave() en eventos.py. */
  var _porDir = null;
  function porDireccion(dir) {
    if (!dir) return null;
    if (!_porDir) {
      _porDir = {};
      D.avisos.forEach(function (a) {
        if (a.direccion_norm) _porDir[a.direccion_norm] = a;
      });
    }
    return _porDir[dir] || null;
  }

  // --------------------------------------------------------------------- filtro

  /* Las mismas localidades que lib_config.GBA_NORTE. Se repiten aca porque data.js no
     viaja con esa marca por aviso: derivarla del barrio es una linea y evita agregar un
     campo a cada uno de los 4.000 avisos. Si se agrega una localidad al config, va aca. */
  var GBA_NORTE = ["vicente lopez", "san isidro", "olivos", "florida", "la lucila",
    "munro", "carapachay", "villa martelli", "martinez", "beccar", "acassuso",
    "la horqueta", "boulogne", "villa adelina"];

  function esGBA(barrio) {
    var b = (barrio || "").toLowerCase()
      .replace(/[áà]/g, "a").replace(/[éè]/g, "e")
      .replace(/[í]/g, "i").replace(/[ó]/g, "o").replace(/[ú]/g, "u")
      .replace(/ñ/g, "n");
    for (var i = 0; i < GBA_NORTE.length; i++) if (b.indexOf(GBA_NORTE[i]) >= 0) return true;
    return false;
  }

  function pasaFiltros(a) {
    var f = estado.filtros;
    var dec = decisiones()[a.id];
    var descartada = (dec && dec.accion === "descartar") || a.decision === "descartado";
    /* Un descartado NO se ve fuera de la pantalla Descartados. Antes habia un chip
       "Ver descartados" que los traia de vuelta a la grilla; se saco, porque para eso
       esta su pantalla y ese chip era la unica via por la que se colaban. */
    if (descartada) return false;
    /* Caido = el portal contesto 404/410 o "aviso no disponible" cuando se pidio su URL.
       No se muestra: no se puede alquilar algo que ya no se publica. El chip lo trae de
       vuelta para revisar el historial. */
    if (a.estado_aviso === "desaparecido" && !f.flags.ver_caidos) return false;
    if (f.precioMin !== null && (a.precio_total_usd || 0) < f.precioMin) return false;
    if (f.precioMax !== null && (a.precio_total_usd || 1e9) > f.precioMax) return false;
    if (f.dorm !== null && (a.dormitorios_reales || 0) < f.dorm) return false;
    if (f.banos !== null && (a.banos_completos || 0) < f.banos) return false;
    if (f.m2 !== null && (a.m2_cubiertos || 0) < f.m2) return false;
    if (f.ext !== null && (extM2(a) || 0) < f.ext) return false;
    /* CABA vs ZONA NORTE. Entro el 2026-08-24 junto con Vicente Lopez y San Isidro: la
       lista corta paso de 153 a 456 de un dia para el otro, y como el score premia el
       exterior (peso 25) y `casa_lote_propio` en tranquilidad, las casas con jardin de
       GBA se llevaron el top 15 entero. Eso NO esta mal -es lo que el perfil pide- pero
       deja los departamentos de CABA fuera de la primera pantalla. El arreglo va en la
       VISTA y no en el score: tocar los pesos para "equilibrar" seria falsear lo que
       Mario dijo que le importa. Los dos chips se excluyen entre si (ver el handler). */
    if (f.flags.solo_caba && esGBA(a.barrio)) return false;
    if (f.flags.solo_gba && !esGBA(a.barrio)) return false;
    if (f.barrios.length && f.barrios.indexOf(a.barrio) < 0) return false;
    if (f.tipos.length && f.tipos.indexOf(a.tipo) < 0) return false;
    if (f.estado) {
      if (a.estado === "sin_clasificar" || a.estado === null || a.estado === undefined) return false;
      if ((RANK_ESTADO[a.estado] === undefined ? 1 : RANK_ESTADO[a.estado]) < RANK_ESTADO[f.estado]) return false;
    }
    if (f.flags.parrilla && a.parrilla !== "propia") return false;
    if (f.flags.sin_expensas && !(a.expensas_usd === 0 || a.expensas_cat === "sin_expensas")) return false;
    if (f.flags.mascotas && ["si", "solo_gato", "a_confirmar"].indexOf(a.mascotas) < 0) return false;
    if (f.flags.dueno && !a.dueno_directo) return false;
    if (f.flags.con_fotos && !fotosDe(a).length) return false;
    /* POR DEFECTO NO SE VE LO QUE NO ENTRA. Antes era al reves -Explorar mostraba el
       inventario entero y habia un chip "Solo los que entran" apagado-, asi que de 1176
       avisos se veian 1073 que fallan algun duro: monoambientes, casas de USD 15.000,
       cosas sin ninguna relacion con lo buscado. Una superficie de escaneo que arranca
       con 91% de ruido no se escanea, se abandona. El chip sigue estando para cuando la
       pregunta sea "que hay ahi afuera", que es otra pregunta. */
    if (a.seccion === "filtrados" && !f.flags.ver_fuera_de_filtro) return false;
    return true;
  }

  function contarFiltros() {
    var f = estado.filtros, n = 0;
    ["precioMin", "precioMax", "dorm", "banos", "m2", "ext"].forEach(function (k) { if (f[k] !== null) n++; });
    if (f.barrios.length) n++;
    if (f.tipos.length) n++;
    if (f.estado) n++;
    n += Object.keys(f.flags).filter(function (k) { return f.flags[k]; }).length;
    return n;
  }

  function ordenar(lista) {
    var o = estado.filtros.orden;
    return lista.slice().sort(function (x, y) {
      switch (o) {
        case "score": return (y.score || 0) - (x.score || 0);
        case "precio": return (x.precio_total_usd || 1e9) - (y.precio_total_usd || 1e9);
        case "m2": return (y.m2_cubiertos || 0) - (x.m2_cubiertos || 0);
        case "ext": return (extM2(y) || 0) - (extM2(x) || 0);
        case "num": return (x.num || 1e9) - (y.num || 1e9);
        case "fecha":
          return (x.publicado_hace_dias === null || x.publicado_hace_dias === undefined ? 1e9 : x.publicado_hace_dias) -
                 (y.publicado_hace_dias === null || y.publicado_hace_dias === undefined ? 1e9 : y.publicado_hace_dias);
        default:
          // Mismo criterio que score.py: el desempate por estado usa el VISUAL (fotos),
          // no el del texto. Sin pasada de fotos, todos empatan y manda el score.
          var ry = y.estado_visual ? (RANK_ESTADO[y.estado_visual] || 0) : 0;
          var rx = x.estado_visual ? (RANK_ESTADO[x.estado_visual] || 0) : 0;
          return ry !== rx ? ry - rx : (y.score || 0) - (x.score || 0);
      }
    });
  }

  // ------------------------------------------------------------------ piezas

  /* El nombre del portal, como se escribe. `portal` esta en el 100% de los avisos desde
     que se sumo el segundo (sesion 7) y hasta hoy no se mostraba nunca. */
  var PORTALES = { zonaprop: "Zonaprop", mercadolibre: "MercadoLibre", argenprop: "Argenprop" };
  function portalChip(a) {
    var k = a.portal || "";
    var n = el("span", "card-portal p-" + (k || "otro"), PORTALES[k] || k || "sin portal");
    n.setAttribute("data-tip", "Este aviso salio de " + (PORTALES[k] || "un portal sin identificar") +
                   ". La misma propiedad publicada en dos portales se fusiona en una sola card.");
    return n;
  }


  var HEART = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20.7l-1.45-1.32C5.4 14.73 2 11.64 2 7.85 2 4.76 4.42 2.35 7.5 2.35c1.74 0 3.41.81 4.5 2.09 1.09-1.28 2.76-2.09 4.5-2.09 3.08 0 5.5 2.41 5.5 5.5 0 3.79-3.4 6.88-8.55 11.54L12 20.7z"/></svg>';
  var ICONO_LINK = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 3h7v7M20.5 3.5L11 13M18 13.5V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h5.5"/></svg>';
  var ICONO_IZQ = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg>';
  var ICONO_DER = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg>';
  // Circulo tachado, no una cruz: la cruz ya significa "cerrar" en el panel.
  var ICONO_DESCARTE = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="M6 6l12 12"/></svg>';

  /* Link directo al aviso, sin pasar por el panel. Es la accion que mas se repite despues
     del corazon: mirar la publicacion original. */
  function enlaceMini(a) {
    if (!a.url) return null;
    var link = document.createElement("a");
    link.className = "enlace-mini";
    link.href = a.url;
    link.target = "_blank";
    link.rel = "noopener";
    link.innerHTML = ICONO_LINK;
    link.title = "Abrir el aviso en " + (a.portal || "el portal");
    link.setAttribute("aria-label", "Abrir el aviso original de " + a.direccion + " en una pestaña nueva");
    link.addEventListener("click", function (e) { e.stopPropagation(); });
    return link;
  }

  function flecha(lado, alClic) {
    var b = el("button", "flecha flecha-" + lado);
    b.type = "button";
    b.innerHTML = lado === "izq" ? ICONO_IZQ : ICONO_DER;
    b.setAttribute("aria-label", lado === "izq" ? "Foto anterior" : "Foto siguiente");
    b.addEventListener("click", alClic);
    return b;
  }

  /* Carrusel compartido por la card y por el tile de Explorar.
     Las dos vistas tienen flechas + indicador de segmentos; el SCRUB por posicion del
     mouse queda solo en Explorar, que es la vista de escaneo rapido: ahi el mouse pasa
     por decenas de fotos sin hacer un solo click. En la grilla, donde se mira una
     propiedad a la vez, las flechas son mas precisas. */
  function montarCarrusel(cont, img, fotos, opciones) {
    opciones = opciones || {};
    if (fotos.length < 2) return;

    var tiras = el("div", "tiras");
    fotos.forEach(function (_, i) { tiras.appendChild(el("span", "tira" + (i ? "" : " on"))); });
    cont.appendChild(tiras);

    var actual = 0;
    function ir(i, ev) {
      if (ev) { ev.stopPropagation(); ev.preventDefault(); }
      actual = (i + fotos.length) % fotos.length;
      img.src = fotos[actual];
      Array.prototype.forEach.call(tiras.children, function (s, j) {
        s.className = "tira" + (j === actual ? " on" : "");
      });
      // precarga de la siguiente: sin esto el salto muestra un hueco mientras baja del CDN
      var sig = new Image();
      sig.src = fotos[(actual + 1) % fotos.length];
    }

    cont.appendChild(flecha("izq", function (ev) { ir(actual - 1, ev); }));
    cont.appendChild(flecha("der", function (ev) { ir(actual + 1, ev); }));


    if (opciones.scrub) {
      cont.addEventListener("mousemove", function (ev) {
        if (ev.target.closest(".flecha, .corazon, .enlace-mini, .descartar-mini")) return;
        var r = cont.getBoundingClientRect();
        var i = Math.max(0, Math.min(fotos.length - 1,
          Math.floor((ev.clientX - r.left) / r.width * fotos.length)));
        if (i !== actual) ir(i);
      });
      cont.addEventListener("mouseleave", function () { if (actual) ir(0); });
    }
  }

  /* Los motivos que ya aparecen en los 36 descartes de la semilla, mas los que se
     desprenden de los duros. Cada chip manda MOTIVO (lo que se lee) y CATEGORIA (lo que
     se agrupa): sin la categoria, todo descarte hecho desde la web caeria en
     "sin_categoria" y el conteo por motivo de build.py dejaria de servir. */
  var MOTIVOS_RAPIDOS = [
    { chip: "uso comercial", motivo: "es para uso comercial", cat: "uso_comercial" },
    { chip: "amoblado", motivo: "viene amoblado", cat: "amoblado" },
    { chip: "el estado", motivo: "el estado no da", cat: "estado" },
    { chip: "mascotas", motivo: "no acepta mascotas", cat: "mascotas" },
    { chip: "dormitorios", motivo: "faltan dormitorios", cat: "dormitorios" },
    { chip: "sin exterior", motivo: "no tiene exterior propio", cat: "exterior" },
    { chip: "ruidosa", motivo: "muy sobre la avenida", cat: "tranquilidad" },
    { chip: "cara", motivo: "cara para lo que es", cat: "precio" },
    /* El unico motivo que no es un atributo. Sin el, un rechazo que no encaja en ningun
       chip obliga a escribir, y el que no quiere escribir termina eligiendo un chip que
       no es el suyo: eso ensucia descartados_por_motivo, que es de donde sale el patron.
       Va ultimo y con su propia categoria, no dentro de "sin_categoria". */
    { chip: "no me gusta", motivo: "no me gusta", cat: "no_gusta" }
  ];

  function botonDescartar(a) {
    var fuera = a.decision === "descartado";
    var b = el("button", "descartar-mini" + (fuera ? " on" : ""));
    b.type = "button";
    b.innerHTML = ICONO_DESCARTE;
    b.title = fuera ? "Ya esta descartada. Click para volver a considerarla."
                    : "Descartar #" + (a.num || "?");
    b.setAttribute("aria-label", (fuera ? "Volver a considerar " : "Descartar ") + a.direccion);
    b.setAttribute("aria-pressed", fuera ? "true" : "false");
    if (!fuera) b.setAttribute("aria-haspopup", "dialog");
    b.addEventListener("click", function (e) {
      e.stopPropagation();
      e.preventDefault();
      if (fuera) registrar(a, "revivir", "", null);
      else abrirPopDescarte(a, b);
    });
    return b;
  }

  function accionesFoto(a) {
    var caja = el("div", "acciones-foto");
    var link = enlaceMini(a);
    if (link) caja.appendChild(link);
    caja.appendChild(botonDescartar(a));
    caja.appendChild(corazon(a));
    return caja;
  }

  /* El motivo ES el dato. Un descarte sin motivo no ensena nada: el bucle de aprendizaje
     ("despues de cada tanda, buscar el patron") se alimenta de estas palabras. Antes esto
     era un window.prompt: bloqueaba, era feo y no podia ofrecer el vocabulario que ya se
     repite. Ahora un chip = un descarte completo en un click, y el campo libre queda para
     lo que ningun chip explica. */
  var _pop = null;

  function cerrarPop() {
    if (!_pop) return;
    var p = _pop; _pop = null;
    document.removeEventListener("keydown", p._esc, true);
    document.removeEventListener("mousedown", p._fuera, true);
    p.remove();
    if (p._volverA && document.body.contains(p._volverA)) p._volverA.focus();
  }

  function abrirPopDescarte(a, ancla) {
    cerrarPop();
    var p = el("div", "pop-descarte");
    p.setAttribute("role", "dialog");
    p.setAttribute("aria-label", "Descartar " + a.direccion);
    p._volverA = ancla;

    var cab = el("div", "pop-cab");
    cab.appendChild(el("span", "pop-sello", "#" + (a.num || "?")));
    cab.appendChild(el("b", null, a.direccion));
    p.appendChild(cab);
    p.appendChild(el("p", "pop-nota",
      "Por que no. Queda anotado y no vuelve a aparecer. El motivo es opcional."));

    var chips = el("div", "pop-chips");
    MOTIVOS_RAPIDOS.forEach(function (m) {
      var c = el("button", "chip-motivo", m.chip);
      c.type = "button";
      c.title = "Descartar: " + m.motivo;
      c.addEventListener("click", function () {
        cerrarPop();
        registrar(a, "descartar", m.motivo, m.cat);
      });
      chips.appendChild(c);
    });
    p.appendChild(chips);

    var ta = document.createElement("textarea");
    ta.className = "pop-texto";
    ta.rows = 2;
    ta.placeholder = "...o escribilo vos: «la cocina esta hecha pelota»";
    p.appendChild(ta);

    var pie = el("div", "pop-pie");
    var cancel = el("button", "btn", "Cancelar");
    cancel.type = "button";
    cancel.addEventListener("click", cerrarPop);
    var ok = el("button", "btn peligro", "Descartar sin motivo");
    ok.type = "button";
    function confirmar() {
      var t = ta.value.trim();
      // Sin texto ya NO se frena: descarta igual y queda como `sin_motivo`. El boton
      // dice cual de las dos cosas va a hacer, asi que no hay descarte mudo por sorpresa.
      cerrarPop();
      registrar(a, "descartar", t, null);
    }
    ok.addEventListener("click", confirmar);
    // La etiqueta del boton sigue al textarea: es el unico aviso de que se va a guardar
    // sin razon, y tiene que estar donde se hace el click, no en un cartel aparte.
    ta.addEventListener("input", function () {
      ta.classList.remove("falta");
      ok.textContent = ta.value.trim() ? "Descartar" : "Descartar sin motivo";
    });
    ta.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); confirmar(); }
    });
    pie.appendChild(cancel);
    pie.appendChild(ok);
    p.appendChild(pie);

    document.body.appendChild(p);

    // Anclado al boton, pero corregido para que no se salga de la ventana.
    var r = ancla.getBoundingClientRect();
    var ancho = p.offsetWidth, alto = p.offsetHeight;
    var x = Math.min(Math.max(8, r.left + r.width / 2 - ancho / 2), window.innerWidth - ancho - 8);
    var y = r.bottom + 8 + alto > window.innerHeight ? r.top - alto - 8 : r.bottom + 8;
    p.style.left = Math.round(x) + "px";
    p.style.top = Math.round(Math.max(8, y)) + "px";
    requestAnimationFrame(function () { p.classList.add("abierto"); });

    p._esc = function (e) {
      if (e.key === "Escape") { e.stopPropagation(); cerrarPop(); }
    };
    p._fuera = function (e) { if (!p.contains(e.target) && e.target !== ancla) cerrarPop(); };
    document.addEventListener("keydown", p._esc, true);
    document.addEventListener("mousedown", p._fuera, true);
    _pop = p;
    (chips.firstChild || ta).focus();
  }

  var ICO_FOTO = '<svg viewBox="0 0 24 24" aria-hidden="true">' +
    '<path d="M4 7.5h3l1.4-2h7.2l1.4 2h3v11H4zM12 15.5a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"/></svg>';

  function sello(a) {
    var s = el("span", "sello");
    s.appendChild(el("b", null, "#" + (a.num || "?")));
    /* El conteo de fotos vive DENTRO del sello. Flotando aparte se pisaba con la
       direccion en la vista densa, y ademas asi refuerza la firma de la pagina: el sello
       es una etiqueta de negativo en una hoja de contactos, y un negativo lleva su
       numero de cuadros. Con 8 fotos de mediana (hay avisos de 50), decir cuantas hay es
       la diferencia entre "esta es la foto" y "hay 33 mas". */
    var n = fotosDe(a).length;
    if (n > 1) {
      var cf = el("span", "sello-fotos");
      cf.innerHTML = ICO_FOTO + n;
      s.appendChild(cf);
    }
    s.title = "Numero de referencia. Podes decirme «descarta el " + (a.num || "?") + "».";
    return s;
  }

  function corazon(a) {
    var b = el("button", "corazon" + (a.pinned ? " on" : ""));
    b.innerHTML = HEART;
    b.type = "button";
    b.setAttribute("aria-pressed", a.pinned ? "true" : "false");
    b.setAttribute("aria-label", (a.pinned ? "Sacar de" : "Marcar como") + " favorito: " + a.direccion);
    b.title = a.pinned ? "Sacar de favoritos" : "Me interesa";
    b.addEventListener("click", function (e) {
      e.stopPropagation();
      alternarFavorito(a, b);
    });
    return b;
  }

  /* Las fotos locales (web/fotos/) existen solo para la lista corta. Para el resto se usa
     la URL del portal: bajar 6 imagenes de cientos de avisos no tiene sentido. */
  /* EL BUG QUE ESTO ARREGLA. Devolvia las locales apenas hubiera una, y las locales son
     3 por decision de Mario (bajar 6 por aviso son pedidos al portal que no hacen falta).
     Pero las REMOTAS no cuestan nada: las sirve el CDN del portal y son 8 de mediana, hasta
     50. O sea que la pagina estaba mostrando el set chico teniendo el grande al lado.

     Las locales existen por otra razon: son las unicas que Claude puede abrir para
     clasificar el estado por fotos. Son la copia de trabajo, no lo que se muestra. */
  function fotosDe(a) {
    var l = a.fotos || [];
    var r = a.fotos_remotas || [];
    return r.length > l.length ? r : l;
  }

  function imagen(src, alt, ansiosa) {
    var im = new Image();
    // Lazy en las listas (con 330 avisos es lo que evita que la pagina muera), pero NO en
    // el panel: ahi las fotos son el motivo por el que se abrio, y esperar al scroll para
    // pedirlas hace que se vea un panel vacio.
    im.loading = ansiosa ? "eager" : "lazy";
    im.decoding = "async";
    im.src = src;
    im.alt = alt || "";
    return im;
  }

  function claseScore(s) { return s >= 75 ? "verde" : (s >= 50 ? "ambar" : ""); }

  /* Decia «70 / hasta 74» y Mario no entendio que era, tres veces seguidas. El problema no
     era el concepto sino que el numero no decia de que escala hablaba: "hasta 74" sin un
     "de 100" al lado no se puede interpretar. Ahora la escala esta siempre a la vista y el
     techo solo aparece cuando la diferencia importa (>=3 puntos). */
  function badgeScore(a) {
    var sd = a.score_desglose || {};
    var piso = Math.round(a.score || 0);
    var techo = Math.round(sd.score_techo || piso);
    var b = el("div", "badge-score " + claseScore(a.score));
    var sube = sd.parcial && techo - piso >= 3;
    b.innerHTML = '<b>' + piso + "</b><small>de 100</small>" +
      (sube ? '<small class="techo">↑ ' + techo + "</small>" : "");
    b.title = "Cuanto se ajusta a tu perfil, de 0 a 100: exterior, ambientes, banos, " +
      "cochera, estado y tranquilidad." +
      (sube
        ? "\n\nAhora suma " + piso + " con lo que se sabe. Podria llegar a " + techo +
          " cuando se miren las fotos (" + sd.cobertura + "% de los criterios ya tienen dato)."
        : "\n\nNo le falta ningun dato: este es el numero final.") +
      (sd.peso_inferido
        ? "\n\nOjo: " + sd.peso_inferido + " de los " + sd.peso_total + " puntos de peso son " +
          "SUPUESTOS, no medidos (la tranquilidad se deduce del tipo de propiedad cuando el " +
          "aviso no dice nada)."
        : "");
    return b;
  }

  /* La fecha de publicacion sale de la FICHA, no del listado, asi que la tienen pocos.
     Devolver null y no "0 dias" importa: un "sin fecha" no es un aviso recien publicado. */
  function diasPublicado(a) {
    var d = a.publicado_hace_dias;
    return (d === null || d === undefined) ? null : Number(d);
  }

  function textoAntiguedadAviso(a) {
    var d = diasPublicado(a);
    if (d === null) return null;
    if (d <= 1) return "publicado hoy";
    if (d < 14) return "publicado hace " + d + " dias";
    if (d < 60) return "publicado hace " + Math.round(d / 7) + " semanas";
    if (d < 365) return "publicado hace " + Math.round(d / 30) + " meses";
    var an = Math.floor(d / 365);
    return "publicado hace " + an + (an === 1 ? " año" : " años");
  }

  function tags(a, dec) {
    var izq = el("div", "badge-izq");
    izq.appendChild(el("span", "tag " + claseEstado(a.estado), textoEstado(a.estado)));
    if ((a.al_limite_por || []).length) izq.appendChild(el("span", "tag limite", "al limite"));
    if ((a.riesgos || []).length) izq.appendChild(el("span", "tag riesgo", "riesgo"));
    if (a.estado_aviso === "desaparecido") izq.appendChild(el("span", "tag riesgo", "caido"));
    var pre = preguntas(a);
    if (pre.length) izq.appendChild(chipPreguntas(pre));
    // El «Na publicado» que estaba aca decia lo mismo que la fila de fecha del cuerpo.
    // Un solo lugar para el dato, con tres estados: nuevo (verde), normal, viejo (ambar).
    if (a.dueno_directo) izq.appendChild(el("span", "tag directo", "dueño directo"));
    if (dec && dec.accion === "descartar") izq.appendChild(el("span", "tag riesgo", "descartada"));
    return izq;
  }

  // -------------------------------------------------------------------- card

  function card(a) {
    var dec = decisiones()[a.id];
    var n = el("article", "card" +
      (a.decision === "descartado" || (dec && dec.accion === "descartar") ? " descartada" : ""));
    n.dataset.id = a.id;
    n.tabIndex = 0;
    n.setAttribute("role", "button");
    n.setAttribute("aria-label", "#" + a.num + " " + a.direccion + ", " + (a.barrio || ""));

    var fotos = fotosDe(a);
    var foto = el("div", "card-foto" + (fotos.length ? "" : " vacia"));
    if (fotos.length) {
      var img = imagen(fotos[0], a.direccion);
      foto.appendChild(img);
      montarCarrusel(foto, img, fotos, { scrub: false });
    } else {
      /* Un rectangulo gris no dice nada. Argenprop bloquea el hotlink de sus imagenes,
         asi que sus avisos no tienen foto mostrable hasta que detalle.py las baje: el
         hueco tiene que explicar por que esta vacio y ofrecer la salida. */
      var vacio = el("div", "foto-vacia");
      vacio.innerHTML =
        '<svg viewBox="0 0 24 24" aria-hidden="true">' +
        '<path d="M4 7.5h3l1.4-2h7.2l1.4 2h3v11H4zM12 15.5a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"/></svg>' +
        "<b>" + ((a.fotos_portal || []).length || "sin") + " fotos en el aviso</b>" +
        "<span>este portal no deja mostrarlas aca</span>";
      foto.appendChild(vacio);
    }
    foto.appendChild(sello(a));
    foto.appendChild(badgeScore(a));
    foto.appendChild(tags(a, dec));
    foto.appendChild(accionesFoto(a));
    n.appendChild(foto);

    var cuerpo = el("div", "card-cuerpo");
    var dir = el("div", "card-dir", a.direccion);
    dir.appendChild(el("span", "card-barrio", "  " + (a.barrio || "")));
    cuerpo.appendChild(dir);

    var pr = el("div", "card-precio");
    pr.innerHTML = "<b>USD " + fmt(a.precio_total_usd) + "</b>";
    var c = cotizacion();
    pr.appendChild(el("span", null, c && a.precio_total_usd
      ? "$ " + fmt(Math.round(a.precio_total_usd * c)) : "sin cotizacion"));
    cuerpo.appendChild(pr);

    var e = extM2(a);
    var m2 = el("div", "card-m2");
    m2.innerHTML = fmt(a.m2_cubiertos) + " m² cub <i>·</i> " +
      (e !== null ? fmt(Math.round(e)) + " m² ext" : "<i>ext s/d</i>") +
      (a.antiguedad_anios !== null && a.antiguedad_anios !== undefined
        ? ' <i>·</i> ' + Math.round(a.antiguedad_anios) + (Math.round(a.antiguedad_anios) === 1 ? " año" : " años") : "");
    cuerpo.appendChild(m2);

    /* Cuanto lleva publicado es informacion de negociacion, no decorativa: un aviso de
       hace tres dias compite con otros interesados, uno de 1600 dias es un precio que
       nadie acepto. Cuando no hay dato se dice, no se omite. */
    var dpub = diasPublicado(a);
    var clase = dpub === null ? "" : dpub <= DIAS_NUEVO ? " nuevo" : dpub > 180 ? " viejo" : "";
    var fila = el("div", "card-fecha" + clase);
    if (dpub === null) {
      fila.innerHTML = "<i>sin fecha de publicacion</i>";
      fila.title = "La fecha sale de la ficha del aviso, no del listado. Se completa corriendo scripts/detalle.py.";
    } else {
      fila.textContent = textoAntiguedadAviso(a) + (dpub <= DIAS_NUEVO ? "  ·  NUEVO" : "");
      if (dpub > 180) {
        fila.title = "Lleva " + dpub + " dias publicado. Un aviso que no se alquila en todo " +
          "ese tiempo es un precio que el mercado no convalido: hay margen para ofertar.";
      }
    }
    cuerpo.appendChild(fila);
    cuerpo.appendChild(iconos(a));

    /* Quien publica, al pie de la card. La garantia la define la inmobiliaria, no la
       propiedad, asi que saber con quien hablas antes de abrir nada ahorra tiempo. */
    var pie = el("div", "card-publicador");
    if (a.dueno_directo === true) pie.appendChild(el("span", "chip-directo", "dueño directo"));
    /* DE QUE PORTAL SALIO. Estaba SOLO en el title del link de la foto, o sea en ningun
       lado: Mario pregunto "no veo nada de mercado libre" teniendo 69 avisos de ML en la
       lista, un tercio del total. Un aviso sin su procedencia se lee como si viniera del
       unico portal que uno recuerda. Va en mono porque es un dato, no prosa. */
    pie.appendChild(portalChip(a));
    pie.appendChild(el("span", "card-inmo", a.publicador || "sin identificar"));
    if (a.publicador_url) {
      var lp = document.createElement("a");
      lp.href = a.publicador_url;
      lp.target = "_blank";
      lp.rel = "noopener";
      lp.className = "card-inmo-link";
      lp.textContent = "su cartera ↗";
      lp.title = "Ver todas las propiedades de " + (a.publicador || "esta inmobiliaria");
      lp.addEventListener("click", function (e) { e.stopPropagation(); });
      pie.appendChild(lp);
    }
    cuerpo.appendChild(pie);
    n.appendChild(cuerpo);

    n.addEventListener("click", function () {
      abrirPanel(a.id);
    });
    n.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); this.click(); }
    });
    return n;
  }

  /* Los emoji (🛏 🚿 🚗 🔥 🐱) eran lo mas flojo de la pagina: cada sistema operativo los
     dibuja distinto, tienen su propio color y su propio peso, y al lado de los iconos de
     trazo del resto de la interfaz se veian pegoteados. Un solo juego de trazo, un solo
     grosor, y el color lo pone el ESTADO del dato, no el icono. */
  var ICO = {
    dorm: '<path d="M3 18v-6a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v6M3 18h18M3 19.5V18M21 19.5V18M6.5 10V7.5a1.5 1.5 0 0 1 1.5-1.5h3.5a1.5 1.5 0 0 1 1.5 1.5V10"/>',
    bano: '<path d="M4 12.5h16v2.5a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4v-2.5ZM7.5 12.5V5.8A1.8 1.8 0 0 1 11 5.4M7 20l-1.2 1.6M17 20l1.2 1.6"/>',
    cochera: '<path d="M4.5 16.5h15M6 16.5l1.6-5.2A2 2 0 0 1 9.5 9.9h5a2 2 0 0 1 1.9 1.4l1.6 5.2M4.5 16.5h15v3h-15zM7.5 19.5V21M16.5 19.5V21"/>',
    parrilla: '<path d="M12 3.5c.4 3-2.6 3.6-2.6 6.4a2.6 2.6 0 0 0 5.2 0c0-1.2-.6-2-.6-2s2.6 1.7 2.6 4.6a4.6 4.6 0 1 1-9.2 0C7.4 8 12 7 12 3.5Z"/>',
    mascotas: '<circle cx="6" cy="10.5" r="1.7"/><circle cx="9.8" cy="6.8" r="1.7"/><circle cx="14.2" cy="6.8" r="1.7"/><circle cx="18" cy="10.5" r="1.7"/><path d="M12 20.8c-2.7 0-5-1.5-5-3.7 0-2.3 2.3-4.3 5-4.3s5 2 5 4.3c0 2.2-2.3 3.7-5 3.7Z"/>'
  };

  function dato(clave, texto, estado, tip) {
    var s = el("span", "dato" + (estado ? " " + estado : ""));
    s.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true">' + ICO[clave] + "</svg>" +
      (texto ? '<i>' + esc(texto) + "</i>" : "");
    s.setAttribute("data-tip", tip);
    return s;
  }

  function iconos(a) {
    var ic = el("div", "iconos");
    var d = a.dormitorios_reales;
    var b = a.banos_completos;
    ic.appendChild(dato("dorm", d || "?", d ? "" : "duda",
      d ? d + (d === 1 ? " dormitorio real" : " dormitorios reales") : "no declara dormitorios"));
    ic.appendChild(dato("bano", (b === null || b === undefined ? "?" : b) + (a.toilettes ? "+" + a.toilettes : ""),
      (b === null || b === undefined) ? "duda" : "",
      b === null || b === undefined ? "no declara banos"
        : b + (b === 1 ? " bano completo" : " banos completos") +
          (a.toilettes ? " y " + a.toilettes + " toilette" + (a.toilettes > 1 ? "s" : "") : "")));
    ic.appendChild(dato("cochera", "", a.cochera ? "" : (a.cochera === false ? "no" : "duda"),
      a.cochera ? "tiene cochera" : (a.cochera === false ? "sin cochera" : "no dice si tiene cochera")));
    ic.appendChild(dato("parrilla", "", a.parrilla === "propia" ? "" : (a.parrilla ? "no" : "duda"),
      a.parrilla === "propia" ? "parrilla propia"
        : a.parrilla === "amenity" ? "parrilla comun del edificio, no propia"
        : "no dice si tiene parrilla"));
    var m = a.mascotas;
    ic.appendChild(dato("mascotas", m === "a_confirmar" || !m ? "?" : "",
      (m === "a_confirmar" || !m) ? "duda" : (m === "si" || m === "solo_gato" ? "si" : "no"),
      m === "si" ? "acepta mascotas" : m === "solo_gato" ? "acepta gatos"
        : m === "solo_perro" ? "solo perros: tu gato no entra"
        : m === "no" ? "no acepta mascotas"
        : "no aclara mascotas: hay que preguntar"));
    return ic;
  }

  // ---------------------------------------------------------------- explorar

  /* Hoja de contactos: el mouse recorre la foto y va pasando las imagenes. Sirve para
     lo que Mario pidio — escanear muchas y despues preguntar por el numero. */
  function tile(a) {
    var fotos = fotosDe(a);
    var t = el("article", "tile");
    t.tabIndex = 0;
    t.setAttribute("role", "button");
    t.setAttribute("aria-label", "#" + a.num + " " + a.direccion + ", " + fotos.length + " fotos");

    var img = fotos.length ? imagen(fotos[0], a.direccion) : el("div");
    t.appendChild(img);

    montarCarrusel(t, img, fotos, { scrub: true });

    t.appendChild(sello(a));
    t.appendChild(accionesFoto(a));

    /* Explorar muestra TODO el inventario, no solo lo que pasa los duros. Pero lo que no
       pasa tiene que decir por que: una lista larga sin esa marca es ruido. */
    if (a.seccion === "filtrados") {
      var fallos = ((a.duros || {}).fallos || []).map(function (f) { return ETIQ_FALLO[f.filtro] || f.filtro; });
      t.appendChild(el("span", "tile-fuera", fallos.length ? fallos.join(" · ") : "no entra"));
    } else if (a.seccion === "al_limite") {
      t.appendChild(el("span", "tile-fuera limite", "al limite"));
    }
    var pre = preguntas(a);
    if (pre.length && a.seccion !== "filtrados") {
      var cp = chipPreguntas(pre);
      cp.classList.add("tile-preguntar");
      t.appendChild(cp);
    }

    var v = el("div", "tile-vidrio");
    var e = extM2(a);
    v.innerHTML =
      '<span class="tile-precio">USD ' + fmt(a.precio_total_usd) + "</span>" +
      '<span class="tile-datos">' + fmt(a.m2_cubiertos) + " + " +
        (e !== null ? fmt(Math.round(e)) : "?") + " m² · " +
        (a.dormitorios_reales || "?") + " dorm · " +
        (a.banos_completos === null || a.banos_completos === undefined ? "?" : a.banos_completos) +
        (a.banos_completos === 1 ? " baño" : " baños") + "</span>" +
      /* EL PORTAL TAMBIEN EN EL TILE. Se agrego primero solo a la card y quedaba el
         agujero peor: Explorar es la superficie de ESCANEO, donde estan casi todos los
         avisos de los portales secundarios (ninguno de ML es favorito hoy), asi que
         mirando Explorar seguia sin verse de donde sale nada. Comparte fila con la
         direccion para no sumar una linea al vidrio. Nombre completo, no sigla: la
         pagina ya tiene abreviaturas de sobra. */
      '<span class="tile-pie"><span class="tile-dir">' + esc(a.direccion) + " · " +
        esc(a.barrio || "") + '</span><span class="tile-portal tp-' + esc(a.portal || "otro") +
        '">' + esc(PORTALES[a.portal] || a.portal || "?") + "</span></span>";
    t.appendChild(v);

    t.addEventListener("click", function () { abrirPanel(a.id); });
    t.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); this.click(); }
    });
    return t;
  }

  var RANK_SECCION = { favoritos: 0, candidatos: 1, al_limite: 2, filtrados: 3 };

  function vistaExplorar(cont) {
    // Los favoritos tienen su propia pantalla: aca va todo lo que NO tiene corazon.
    var lista = ordenar(D.avisos.filter(function (a) { return pasaFiltros(a) && !a.pinned; }));

    /* Explorar es una lista PLANA con todo el inventario, asi que el orden tiene que
       poner primero lo que efectivamente entra. Ordenar solo por score dejaba arriba
       caserones de USD 15.000: el precio no entra en el score (filtra como duro), asi
       que un lote enorme fuera de presupuesto puntuaba mejor que un PH que si sirve.
       Solo se aplica cuando el orden es el automatico; si Mario elige uno, manda el suyo. */
    if (estado.filtros.orden === "default") {
      lista.sort(function (x, y) {
        var rx = RANK_SECCION[x.seccion] === undefined ? 3 : RANK_SECCION[x.seccion];
        var ry = RANK_SECCION[y.seccion] === undefined ? 3 : RANK_SECCION[y.seccion];
        return rx !== ry ? rx - ry : (y.score || 0) - (x.score || 0);
      });
    }
    var s = el("div", "seccion");
    var fuera = (D.avisos || []).filter(function (a) {
      return a.seccion === "filtrados" && a.decision !== "descartado" && a.estado_aviso !== "desaparecido";
    }).length;
    var viendoFuera = !!estado.filtros.flags.ver_fuera_de_filtro;
    s.innerHTML = '<div class="seccion-cab"><h2>Explorar</h2><span class="cuenta">' +
      lista.length + "</span></div><p class='seccion-nota'>" +
      "<b>Lo que pasa tus filtros duros y no marcaste con el corazon</b>, ordenado por lo " +
      "que mejor se ajusta a tu perfil. " +
      (viendoFuera
        ? "Estas viendo tambien los <b>" + fuera + " que NO entran</b>, con una etiqueta roja " +
          "diciendo por que; apaga «Ver los que no entran» en Filtros para sacarlos. "
        : "Quedan <b>" + fuera + " afuera</b> por fallar algun duro (precio, ambientes, " +
          "dormitorios, zona): estan en Filtros, con «Ver los que no entran». ") +
      "<b>Pasa el mouse por una foto y recorre las demas</b> sin abrir nada. " +
      "Despues decime el numero: «contame del 7» o «descarta el 3 porque la cocina esta hecha pelota».</p>";

    if (!lista.length) {
      s.appendChild(el("div", "vacio", "Ningun aviso pasa los filtros actuales."));
      cont.appendChild(s);
      return;
    }
    var g = el("div", "explorar");
    pintarTanda(g, lista, "explorar", tile, s);
    cont.appendChild(s);
  }

  /* Primera tanda + boton que AGREGA. No es paginado: no se pierde el scroll ni hay que
     acordarse en que pagina estabas. */
  /* EL BUG DE UBICACION. El boton se agregaba a la seccion ANTES de que la grilla
     estuviera adentro (`pintarTanda(g, ...)` y recien despues `s.appendChild(g)`), asi que
     terminaba ARRIBA de las cards, pegado a la barra. Ahora la funcion mete la grilla ella
     misma y despues el boton: el orden deja de depender de quien llame.

     Sigue sin haber paginado, y es a proposito: en una herramienta de busqueda un paginado
     te hace perder el scroll y acordarte en que pagina estabas. Lo que faltaba no era
     paginar sino que el boton dijera donde estas parado. */
  function pintarTanda(contenedor, lista, clave, fabrica, seccion) {
    var limite = estado.limites[clave] || TANDA;
    lista.slice(0, limite).forEach(function (a) { contenedor.appendChild(fabrica(a)); });
    if (contenedor.parentNode !== seccion) seccion.appendChild(contenedor);

    var faltan = lista.length - limite;
    if (faltan <= 0) return;
    var wrap = el("div", "mas");
    wrap.appendChild(el("span", "mas-cuenta",
      "mostrando " + Math.min(limite, lista.length) + " de " + lista.length));
    var b = el("button", "btn primario", "Mostrar " + Math.min(faltan, TANDA) + " mas");
    b.addEventListener("click", function () {
      estado.limites[clave] = limite + TANDA;
      render();
    });
    wrap.appendChild(b);
    var todas = el("button", "btn", "Ver las " + lista.length);
    todas.addEventListener("click", function () {
      estado.limites[clave] = lista.length;
      render();
    });
    wrap.appendChild(todas);
    seccion.appendChild(wrap);
  }

  // ------------------------------------------------------------------ panel

  function barra(comp) {
    var b = el("div", "barra");
    b.appendChild(el("div", "nom", comp.componente.replace(/_/g, " ")));
    var riel = el("div", "riel");
    var rel = el("div", "relleno" + (comp.puntos === null ? " nodato" : ""));
    if (comp.puntos !== null) rel.style.width = Math.max(0, Math.min(100, comp.puntos)) + "%";
    riel.appendChild(rel);
    b.appendChild(riel);
    b.appendChild(el("div", "val", comp.puntos === null ? "s/d" : Math.round(comp.puntos) + " · peso " + comp.peso));
    if (comp.detalle) b.appendChild(el("div", "det", comp.detalle));
    return b;
  }

  function filaFicha(rot, val) {
    return "<tr><td>" + esc(rot) + "</td><td>" +
      (val === null || val === undefined || val === "" ? nd() : val) + "</td></tr>";
  }

  function abrirPanel(id) {
    var a = porId(id);
    if (!a) return;
    estado.abierto = id;

    var p = $("#panel");
    p.innerHTML = "";

    var cab = el("div", "panel-cab");
    cab.appendChild(el("span", "sello-panel", "#" + (a.num || "?")));
    var t = el("div");
    t.style.flex = "1";
    t.innerHTML = "<h2>" + esc(a.direccion) + "</h2><div class='sub'>" +
      esc(a.barrio || "") + " · " + esc(a.tipo || "") + " · USD " + fmt(a.precio_total_usd) + "</div>";
    cab.appendChild(t);
    // El aviso original tambien vive al final del panel, pero ahi hay que scrollear.
    var linkCab = enlaceMini(a);
    if (linkCab) cab.appendChild(linkCab);
    cab.appendChild(corazon(a));
    var x = el("button", "cerrar", "✕");
    x.setAttribute("aria-label", "Cerrar");
    x.addEventListener("click", cerrarPanel);
    cab.appendChild(x);
    p.appendChild(cab);

    var b = el("div", "panel-cuerpo");
    var sd = a.score_desglose || {};

    // fotos
    var bf = el("div", "bloque");
    var _fp = fotosDe(a);
    bf.appendChild(el("h3", null, "Fotos" + (_fp.length ? " (" + _fp.length + ")" : "")));
    if (_fp.length) {
      /* Grilla, no tira horizontal. Con 8 fotos de mediana (y hasta 50), en una tira se
         veian dos y las demas quedaban fuera de pantalla. El panel es donde se mira una
         propiedad en serio: que entren todas de un vistazo. Click en una la agranda. */
      var g = el("div", "galeria");
      _fp.forEach(function (u, i) {
        var fig = el("figure");
        fig.appendChild(imagen(u, a.direccion + " — foto " + (i + 1), i < 12));
        var cap = (a.fotos_captions || [])[i];
        if (cap) fig.appendChild(el("figcaption", null, cap));
        fig.addEventListener("click", function () { fig.classList.toggle("grande"); });
        fig.title = "Click para agrandar";
        g.appendChild(fig);
      });
      bf.appendChild(g);
    } else {
      bf.appendChild(el("div", "sin-fotos", "Este aviso no publico ninguna foto."));
    }
    b.appendChild(bf);

    /* Quien lo publica. Estaba en el 100% de los avisos (320 con link a su listado) y no
       se mostraba en ningun lado. Importa por dos motivos: la garantia la define la
       inmobiliaria, no la propiedad; y ver el resto de su cartera es la forma mas rapida
       de encontrar mas de lo mismo. */
    if (a.publicador || a.dueno_directo) {
      var bp = el("div", "bloque bloque-publicador");
      bp.appendChild(el("h3", null, "Quien lo publica"));
      var fila = el("div", "publicador-fila");
      if (a.dueno_directo === true) {
        fila.appendChild(el("span", "tag directo", "dueño directo"));
      }
      fila.appendChild(el("b", null, a.publicador || "sin identificar"));
      if (a.publicador_url) {
        var lp = document.createElement("a");
        lp.className = "btn btn-portal";
        lp.href = a.publicador_url;
        lp.target = "_blank";
        lp.rel = "noopener";
        lp.textContent = "Ver toda su cartera";
        fila.appendChild(lp);
      }
      bp.appendChild(fila);
      var mismos = D.avisos.filter(function (x) {
        return x.publicador && x.publicador === a.publicador && x.id !== a.id;
      });
      if (mismos.length) {
        bp.appendChild(el("p", "publicador-nota",
          "Publica otras " + mismos.length + " en tu busqueda: " +
          mismos.slice(0, 6).map(function (x) { return "#" + x.num; }).join(" · ")));
      }
      b.appendChild(bp);
    }

    // alertas
    var alertas = el("div");
    if ((a.riesgos || []).length) a.riesgos.forEach(function (r) { alertas.appendChild(el("div", "caja-nota alerta", r)); });
    if ((a.al_limite_por || []).length) {
      alertas.appendChild(el("div", "caja-nota aviso", "AL LIMITE por: " + a.al_limite_por.join(", ") +
        ". Se muestra aparte y no compite en el mismo ranking."));
    }
    if (a.estado_aviso === "desaparecido") {
      alertas.appendChild(el("div", "caja-nota alerta", "ESTE AVISO YA NO ESTA PUBLICADO (" + esc(a.desaparecido_el || "") + ")."));
    }
    if (a.estado_aviso === "vigente_sin_verificar") {
      alertas.appendChild(el("div", "caja-nota aviso", "Vigencia sin verificar contra el portal."));
    }
    if (a.uso_permitido === "ambos") {
      alertas.appendChild(el("div", "caja-nota aviso", "El aviso ofrece la propiedad tambien para USO COMERCIAL. " +
        "No la descalifica para vivienda, pero cambia con quien competis por ella."));
    }
    if (a.discrepancia_exterior) {
      alertas.appendChild(el("div", "caja-nota aviso", "Discrepancia: " + a.discrepancia_exterior +
        ". Para el score se usa el dato del portal, que es el estructurado."));
    }
    if ((a.dormitorios_a_verificar || []).length) {
      alertas.appendChild(el("div", "caja-nota aviso", "El aviso nombra " + a.dormitorios_a_verificar.join(", ") +
        ": verificar si alguno de los dormitorios declarados es en realidad eso."));
    }
    if ((a.alertas_intencion || []).length) {
      alertas.appendChild(el("div", "caja-nota alerta", "Señal de que el dueño no quiere alquilar de verdad: " +
        a.alertas_intencion.join(" · ")));
    }
    if (a.publicado_hace_dias > 365) {
      alertas.appendChild(el("div", "caja-nota aviso", "Publicado hace " + fmt(a.publicado_hace_dias) +
        " días. Antes de invertir tiempo: por qué sigue publicado."));
    }
    if (alertas.children.length) b.appendChild(alertas);

    // a favor / en contra
    if ((a.a_favor || []).length || (a.en_contra || []).length) {
      var bl = el("div", "bloque");
      bl.appendChild(el("h3", null, "A favor"));
      var ul = el("ul", "lista a-favor");
      (a.a_favor || []).forEach(function (s) { ul.appendChild(el("li", null, s)); });
      bl.appendChild(ul);
      var h2 = el("h3", null, "En contra");
      h2.style.marginTop = "16px";
      bl.appendChild(h2);
      var ul2 = el("ul", "lista en-contra");
      (a.en_contra || []).forEach(function (s) { ul2.appendChild(el("li", null, s)); });
      bl.appendChild(ul2);
      b.appendChild(bl);
    }

    if (a.primera_pregunta) {
      b.appendChild(el("div", "caja-nota " + (a.llamaria_hoy ? "bien" : ""),
        (a.llamaria_hoy ? "LA LLAMARIA HOY. " : "No la llamaria todavia. ") + "Primera pregunta: " + a.primera_pregunta));
    }

    // score
    var bs = el("div", "bloque");
    bs.appendChild(el("h3", null, "Score " + Math.round(sd.score_piso || 0) +
      (sd.parcial ? " (piso) · techo " + Math.round(sd.score_techo || 0) + " · " + sd.cobertura + "% con dato" : "")));
    var barras = el("div", "barras");
    (sd.componentes || []).forEach(function (c) { barras.appendChild(barra(c)); });
    bs.appendChild(barras);
    if ((sd.caps || []).length) bs.appendChild(el("div", "caja-nota", sd.caps.join(" · ")));
    b.appendChild(bs);

    // ficha
    var bfi = el("div", "bloque");
    bfi.appendChild(el("h3", null, "Ficha"));
    var tb = el("table", "ficha");
    tb.innerHTML =
      filaFicha("Tipo", esc((a.tipo || "") + (a.subtipo ? " / " + a.subtipo : ""))) +
      filaFicha("Ambientes declarados", a.ambientes_declarados) +
      filaFicha("Dormitorios reales / declarados",
        (a.dormitorios_reales === null || a.dormitorios_reales === undefined ? "?" : a.dormitorios_reales) + " / " +
        (a.dormitorios_declarados === null || a.dormitorios_declarados === undefined ? "?" : a.dormitorios_declarados)) +
      filaFicha("Banos completos", a.banos_completos) +
      filaFicha("Toilettes", a.toilettes) +
      filaFicha("m² cubiertos", a.m2_cubiertos) +
      filaFicha("m² descubiertos", a.m2_descubiertos) +
      filaFicha("m² totales", a.m2_totales) +
      filaFicha("Exterior", esc(extTexto(a))) +
      filaFicha("Antigüedad", a.antiguedad_anios === null || a.antiguedad_anios === undefined
        ? null : Math.round(a.antiguedad_anios) + " años") +
      filaFicha("Publicado hace", a.publicado_hace_dias === null || a.publicado_hace_dias === undefined
        ? null : fmt(a.publicado_hace_dias) + " días" + (a.publicado_hace_dias > 60 ? " ⚠" : "")) +
      filaFicha("Luminosidad", a.luminosidad) +
      filaFicha("Orientacion", a.orientacion) +
      filaFicha("Parrilla", a.parrilla) +
      filaFicha("Cochera", a.cochera === null || a.cochera === undefined ? null : (a.cochera ? "si" : "no")) +
      filaFicha("Unidades en el edificio", a.unidades_en_el_edificio) +
      filaFicha("Entrada independiente", a.entrada_independiente === null || a.entrada_independiente === undefined
        ? null : (a.entrada_independiente ? "si" : "no")) +
      filaFicha("Dueno directo", a.dueno_directo ? "si" : "no") +
      filaFicha("Mascotas", a.mascotas) +
      filaFicha("Amoblado", a.amoblado === null || a.amoblado === undefined ? null : (a.amoblado ? "SI" : "no")) +
      filaFicha("Uso permitido", a.uso_permitido);
    bfi.appendChild(tb);
    b.appendChild(bfi);

    // condiciones
    var co = a.condiciones || {};
    var bc = el("div", "bloque");
    bc.appendChild(el("h3", null, "Condiciones"));
    var tc = el("table", "ficha");
    tc.innerHTML =
      filaFicha("Garantias aceptadas", (co.garantias_aceptadas || []).join(", ")) +
      filaFicha("Deposito (meses)", co.deposito_meses) +
      filaFicha("Plazo de contrato (meses)", co.contrato_meses) +
      filaFicha("Ajuste", co.ajuste) +
      filaFicha("Moneda de publicacion", a.moneda_publicacion) +
      filaFicha("Expensas USD", a.expensas_usd) +
      filaFicha("Expensas declaradas", a.expensas_declaradas === undefined ? null : (a.expensas_declaradas ? "si" : "no aparecen en el aviso")) +
      filaFicha("Cotizacion usada", a.cotizacion_usada) +
      filaFicha("ABL", co.abl) +
      filaFicha("AYSA", co.aysa) +
      filaFicha("Disponibilidad", a.disponibilidad);
    bc.appendChild(tc);
    b.appendChild(bc);

    if ((a.preguntas || []).length) {
      var bq = el("div", "bloque");
      bq.appendChild(el("h3", null, "Preguntas antes de ir"));
      var uq = el("ul", "lista");
      a.preguntas.forEach(function (q) { uq.appendChild(el("li", null, q)); });
      bq.appendChild(uq);
      b.appendChild(bq);
    }

    if ((a.historial_precio || []).length > 1) {
      var bh = el("div", "bloque");
      bh.appendChild(el("h3", null, "Historial de precio"));
      var th = el("table", "ficha");
      th.innerHTML = a.historial_precio.map(function (h) {
        return "<tr><td>" + esc(h.fecha) + "</td><td>USD " + fmt(h.precio_total_usd) + "</td></tr>";
      }).join("");
      bh.appendChild(th);
      b.appendChild(bh);
    }

    if ((a.notas || []).length || (a.notas_mario || []).length) {
      var bn = el("div", "bloque");
      bn.appendChild(el("h3", null, "Notas"));
      (a.notas_mario || []).forEach(function (t) {
        bn.appendChild(el("div", "caja-nota bien", t.fecha + " — " + t.texto));
      });
      (a.notas || []).forEach(function (t) { bn.appendChild(el("div", "caja-nota", t)); });
      b.appendChild(bn);
    }

    var be = el("div", "bloque");
    be.appendChild(el("h3", null, "Enlaces"));
    var en = el("div", "enlaces");
    en.innerHTML =
      '<a href="' + esc(a.url) + '" target="_blank" rel="noopener">Aviso original</a>' +
      '<a href="' + esc(urlStreet(a)) + '" target="_blank" rel="noopener">Street View</a>' +
      '<a href="' + esc(urlMapa(a)) + '" target="_blank" rel="noopener">Mapa</a>' +
      (a.duplicados || []).map(function (d, i) {
        return '<a href="' + esc(d.url || d) + '" target="_blank" rel="noopener">Duplicado ' + (i + 1) + "</a>";
      }).join("");
    be.appendChild(en);
    b.appendChild(be);

    var acc = el("div", "acciones");
    var esDesc = a.decision === "descartado";
    var b2 = el("button", "btn " + (esDesc ? "" : "peligro"), esDesc ? "Volver a considerar" : "Descartar");
    b2.addEventListener("click", function (e) {
      if (esDesc) registrar(a, "revivir", "", null);
      else abrirPopDescarte(a, b2);
      e.stopPropagation();
    });
    var b3 = el("button", "btn", "Ya la vi online");
    b3.addEventListener("click", function () { registrar(a, "vista_online", "", null); });
    acc.appendChild(b2);
    acc.appendChild(b3);
    acc.appendChild(el("span", "cotiz",
      "Arriba: el corazon marca «me interesa», el circulo tachado descarta."));
    b.appendChild(acc);

    p.appendChild(b);
    $("#velo").classList.add("abierto");
    p.classList.add("abierto");
    x.focus();
  }

  function cerrarPanel() {
    $("#velo").classList.remove("abierto");
    $("#panel").classList.remove("abierto");
    estado.abierto = null;
    render();
  }

  // ------------------------------------------------------------- decisiones

  var TIPO_POR_ACCION = {
    interesa: "favorito", descartar: "descarte",
    vista_online: "vista_online", revivir: "revivir"
  };

  function alternarFavorito(a, boton) {
    var quiere = !a.pinned;
    var ev = {
      tipo: quiere ? "favorito" : "no_favorito", id: a.id,
      direccion: a.direccion, barrio: a.barrio, precio_usd: a.precio_total_usd, url: a.url
    };

    // Optimista: el corazon responde ya, el disco confirma despues.
    a.pinned = quiere;
    a.seccion = recomputarSeccion(a);
    if (boton) {
      boton.classList.toggle("on", quiere);
      boton.setAttribute("aria-pressed", quiere ? "true" : "false");
      if (quiere) { boton.classList.add("late"); setTimeout(function () { boton.classList.remove("late"); }, 400); }
    }

    if (!CON_SERVIDOR) {
      guardarDecision(a.id, decisionLocal(a, quiere ? "interesa" : "no_favorito", ""));
      avisar((quiere ? "#" + a.num + " a favoritos" : "#" + a.num + " fuera de favoritos") +
             " — solo en este navegador, falta exportar");
      if (estado.vista !== "explorar") render();
      return;
    }
    enviarEvento(ev).then(function (r) {
      D.eventos = (D.eventos || []).concat([r.evento]);
      avisar(quiere ? "#" + a.num + " a favoritos" : "#" + a.num + " fuera de favoritos", "bien");
      if (estado.vista !== "explorar") render();
    }).catch(function (e) {
      // Si el POST falla, la decision NO se pierde: cae a localStorage y se aplica igual.
      guardarDecision(a.id, decisionLocal(a, quiere ? "interesa" : "no_favorito", ""));
      avisar("Sin conexion con el servidor: guardado local, hay que exportar", "error");
      if (estado.vista !== "explorar") render();
    });
  }

  function registrar(a, accion, motivo, categoria) {
    motivo = (motivo || "").trim();

    /* DESCARTAR SIN MOTIVO. Antes se cortaba aca y no pasaba nada: el motivo era
       obligatorio "sin excepcion". Mario, 2026-08-24: "a veces no tengo ganas de poner
       la razon" — y un boton que a veces no hace nada es peor que uno que registra menos.
       El motivo sigue importando (descartados_por_motivo es de donde salen los patrones
       que se proponen como cambios de config), asi que el descarte mudo NO queda vacio:
       queda con categoria propia `sin_motivo`. Es la diferencia entre "no lo sabemos" y
       "no lo preguntamos", la misma distincion que el proyecto ya hace entre
       estado=null y estado="sin_clasificar". Asi se puede contar cuantos son y ofrecer
       etiquetarlos despues en tanda, en vez de perderlos en silencio. */
    if (accion === "descartar" && !motivo) categoria = "sin_motivo";

    var ev = {
      tipo: TIPO_POR_ACCION[accion], id: a.id, direccion: a.direccion, barrio: a.barrio,
      precio_usd: a.precio_total_usd, url: a.url
    };
    if (motivo) ev.motivo = motivo;
    if (categoria) ev.categoria = categoria;

    var abierto = estado.abierto === a.id;
    var msj = accion === "descartar"
      ? (motivo ? "#" + a.num + " descartada — «" + motivo + "»"
                : "#" + a.num + " descartada, sin motivo")
      : accion === "revivir" ? "#" + a.num + " vuelve a la lista" : "Guardado";
    // Un chip descarta de un click: sin deshacer, un click equivocado se paga caro.
    var deshacer = accion === "descartar"
      ? { texto: "deshacer", fn: function () { registrar(a, "revivir", "", null); } }
      : null;

    if (CON_SERVIDOR) {
      enviarEvento(ev).then(function (r) {
        aplicarLocal(a, accion, motivo, categoria);
        D.eventos = (D.eventos || []).concat([r.evento]);
        avisar(msj, "bien", deshacer);
        if (abierto) cerrarPanel(); else render();
      }).catch(function (e) {
        avisar("No se pudo guardar: " + e.message + " — queda local", "error");
        guardarDecision(a.id, decisionLocal(a, accion, motivo, categoria));
        aplicarLocal(a, accion, motivo, categoria);
        if (abierto) cerrarPanel(); else render();
      });
      return;
    }
    guardarDecision(a.id, decisionLocal(a, accion, motivo, categoria));
    aplicarLocal(a, accion, motivo, categoria);
    avisar(msj + " — solo en este navegador, falta exportar", null, deshacer);
    if (abierto) cerrarPanel(); else render();
  }

  function decisionLocal(a, accion, motivo, categoria) {
    return {
      id: a.id, num: a.num, direccion: a.direccion, barrio: a.barrio, precio_usd: a.precio_total_usd,
      accion: accion, motivo_literal: motivo, motivo_categorizado: categoria || null,
      fecha: new Date().toISOString().slice(0, 10), url: a.url
    };
  }

  function aplicarLocal(a, accion, motivo, categoria) {
    if (accion === "descartar") {
      a.decision = "descartado";
      a.pinned = false;
      a.seccion = recomputarSeccion(a);
      D.descartados = (D.descartados || []).concat([{
        id: a.id, direccion: a.direccion, direccion_norm: a.direccion_norm, barrio: a.barrio,
        precio_usd: a.precio_total_usd, fecha_descarte: new Date().toISOString().slice(0, 10),
        motivo_literal: motivo, motivo_literal_verbatim: true,
        motivo_categorizado: categoria || null, reversible: true
      }]);
    } else if (accion === "revivir") {
      a.decision = null;
      a.seccion = recomputarSeccion(a);
      D.descartados = (D.descartados || []).filter(function (d) { return d.id !== a.id; });
    } else if (accion === "vista_online") {
      a.vista_online = true;
    }
  }

  // ------------------------------------------------------------- descartados

  function vistaDescartados(cont) {
    var s = el("div", "seccion");
    s.innerHTML = '<div class="seccion-cab"><h2>Descartados</h2><span class="cuenta">' +
      (D.descartados || []).length + "</span></div>" +
      '<p class="seccion-nota">El archivo mas importante del sistema: mientras un descarte este aca con su motivo, ' +
      "no se vuelve a mostrar. Solo reaparece si baja el precio mas de 15% o si el aviso se edito y resuelve el motivo.</p>";
    var t = el("table", "tabla-desc");
    t.innerHTML = "<tr><th>#</th><th>Direccion</th><th>Barrio</th><th>USD</th><th>Motivo</th><th>Con tus palabras</th><th>Aprendizaje</th><th></th></tr>" +
      (D.descartados || []).map(function (d, i) {
        var a = (d.id ? porId(d.id) : null) || porDireccion(d.direccion_norm);
        return "<tr><td>" + (a && a.num ? "#" + a.num : "") + "</td><td>" + esc(d.direccion) +
          (d.es_regla ? " <span class='motivo'>regla</span>" : "") +
          "</td><td>" + esc(d.barrio || "-") +
          "</td><td>" + (d.precio_usd ? fmt(d.precio_usd) : "-") +
          "</td><td><span class='motivo'>" + esc((d.motivo_categorizado || "sin categoria").replace(/_/g, " ")) + "</span>" +
          "</td><td class='cita'>" + esc(d.motivo_literal || "") +
          (d.motivo_literal_verbatim === false ? " <span class='nd'>(resumido)</span>" : "") +
          "</td><td class='aprend'>" + esc(d.aprendizaje || "") +
          (d.accion_pendiente ? "<br><b>Pendiente: " + esc(d.accion_pendiente) + "</b>" : "") +
          "</td><td class='revivir-celda'" + (a ? " data-rev='" + i + "'" : "") + "></td></tr>";
      }).join("");

    /* Un descarte se revierte, y tiene que poder revertirse DESDE aca: es el unico lugar
       donde se ven todos juntos con su motivo. El evento `revivir` ya existia en la
       bitacora; lo que faltaba era la via para emitirlo desde la pagina. */
    (D.descartados || []).forEach(function (d, i) {
      var a = (d.id ? porId(d.id) : null) || porDireccion(d.direccion_norm);
      if (!a) return;
      var celda = t.querySelector("[data-rev='" + i + "']");
      if (!celda) return;
      var b = el("button", "btn mini", "volver a considerar");
      b.type = "button";
      b.title = "Saca el descarte y la devuelve a la lista. El motivo queda en la bitacora.";
      b.addEventListener("click", function () { registrar(a, "revivir", "", null); });
      celda.appendChild(b);
    });
    s.appendChild(t);
    cont.appendChild(s);
  }

  // --------------------------------------------------------------- actividad

  var ETIQ_EVENTO = {
    favorito: ["me interesa", "ev-fav"], no_favorito: ["saco de favoritos", "ev-vista"],
    descarte: ["descartada", "ev-desc"], vista_online: ["ya la vi online", "ev-vista"],
    revivir: ["revivida", "ev-fav"], visita: ["visita", "ev-visita"], nota: ["nota", "ev-nota"],
    contacto: ["contacto", "ev-nota"], prioridad: ["prioridad", "ev-nota"], corrida: ["corrida", "ev-corrida"]
  };

  function vistaActividad(cont) {
    var evs = (D.eventos || []).slice().sort(function (a, b) {
      return (b.ts || "").localeCompare(a.ts || "");
    });
    var s = el("div", "seccion");
    s.innerHTML = '<div class="seccion-cab"><h2>Actividad</h2><span class="cuenta">' +
      evs.length + "</span></div><p class='seccion-nota'>" +
      "Todo lo que decidiste, en orden. Es la bitacora de <code>data/eventos.jsonl</code>: " +
      "append-only, nada la pisa, y el estado de la pagina se reconstruye desde aca. " +
      (CON_SERVIDOR
        ? "Estas con el servidor local: cada accion se escribe sola."
        : "Abriste el archivo directo, asi que las decisiones quedan en el navegador hasta que las exportes. Para que se guarden solas, abri con <b>abrir.bat</b>.") +
      "</p>";

    if (!evs.length) {
      s.appendChild(el("div", "vacio", "Todavia no hay eventos. En cuanto marques algo aparece aca."));
      cont.appendChild(s);
      return;
    }

    var porDia = {};
    evs.forEach(function (ev) {
      var dia = (ev.ts || "").slice(0, 10);
      (porDia[dia] = porDia[dia] || []).push(ev);
    });

    var linea = el("div", "linea-tiempo");
    Object.keys(porDia).sort().reverse().forEach(function (dia) {
      var cab = el("div", "dia");
      cab.appendChild(el("span", null, dia));
      cab.appendChild(el("span", "cuantos", porDia[dia].length + " evento" + (porDia[dia].length > 1 ? "s" : "")));
      linea.appendChild(cab);

      porDia[dia].forEach(function (ev) {
        var meta = ETIQ_EVENTO[ev.tipo] || [ev.tipo, "ev-nota"];
        var a = ev.id ? porId(ev.id) : null;
        var txt = ev.motivo || ev.texto || ev.nota || "";
        var it = el("div", "evento " + meta[1]);
        it.innerHTML =
          '<span class="hora">' + esc((ev.ts || "").slice(11, 16)) + "</span>" +
          '<span class="tipo">' + esc(meta[0]) + "</span>" +
          '<span class="que">' + (a && a.num ? '<span class="num">#' + a.num + "</span>" : "") +
            esc(ev.direccion || ev.id || "") + "</span>" +
          '<span class="cita">' + (txt ? "“" + esc(txt) + "”" : "") + "</span>" +
          '<span class="origen">' + esc(ev.origen || "") + "</span>";
        if (a) {
          it.style.cursor = "pointer";
          it.addEventListener("click", function () { abrirPanel(a.id); });
        }
        linea.appendChild(it);
      });
    });
    s.appendChild(linea);
    cont.appendChild(s);
  }

  // --------------------------------------------------------------- favoritos

  var LEYENDA_SCORE =
    "El numero sobre cada foto es <b>cuanto se ajusta a tu perfil, de 0 a 100</b>: " +
    "exterior, ambientes, banos, cochera, estado y tranquilidad. La flecha (<b>↑</b>) " +
    "es hasta donde puede subir cuando se miren las fotos.";

  /* TRES ESTADOS, NO CUATRO SECCIONES. La grilla mostraba favoritos, candidatos, al
     limite y fuera de filtro, y habia que aprenderse la diferencia. El modelo real que
     usa Mario es mas simple y es el que manda:

        corazon rojo  -> Favoritos     (lo que le importa)
        sin corazon   -> Explorar      (todo lo demas, con su etiqueta de por que entra o no)
        descartado    -> Descartados   (y no vuelve)

     Candidato / al limite no desaparecen: siguen ordenando Explorar y siguen pintados en
     la etiqueta de cada card. Dejan de ser una pantalla que hay que entender. */
  function vistaFavoritos(cont) {
    var lista = ordenar(D.avisos.filter(function (a) {
      return a.pinned && a.decision !== "descartado";
    }));
    var s = el("div", "seccion");
    s.innerHTML = '<div class="seccion-cab"><h2>Favoritos</h2><span class="cuenta">' +
      lista.length + "</span></div><p class='seccion-nota'>" +
      "Lo que marcaste con el corazon. <b>No se filtran nunca</b>, aunque alguno no cierre " +
      "un filtro duro: una decision tuya pesa mas que una regla. " + LEYENDA_SCORE + "</p>";

    if (!lista.length) {
      s.appendChild(el("div", "vacio",
        "Todavia no marcaste ninguno. Anda a Explorar y toca el corazon de los que te interesen."));
      cont.appendChild(s);
      return;
    }
    var g = el("div", "grilla");
    pintarTanda(g, lista, "favoritos", card, s);
    cont.appendChild(s);
  }

  // ------------------------------------------------------------------ nuevos

  var DIAS_NUEVO = 14;

  /* «Solo lo publicado en las ultimas 2 semanas».
     La fecha SI viene del listado desde el 2026-08-21: estaba en el campo `antiquity`
     ("Publicado hace 14 dias") y el proyecto creia que habia que abrir la ficha de cada
     aviso para tenerla. Hoy la tiene practicamente el 100% del inventario, sin un pedido
     extra. El bloque de «sin fecha» se queda igual: cuando alguno queda sin dato hay que
     decirlo, porque un filtro que esconde en silencio lo que no sabe se lee como «no hay
     nada nuevo» cuando en realidad es «no lo sabemos». */
  function vistaNuevos(cont) {
    var considerados = D.avisos.filter(function (a) {
      return pasaFiltros(a) && a.seccion !== "filtrados";
    });
    var nuevos = ordenar(considerados.filter(function (a) {
      var d = diasPublicado(a);
      return d !== null && d <= DIAS_NUEVO;
    }));
    var sinFecha = ordenar(considerados.filter(function (a) { return diasPublicado(a) === null; }));
    var conFecha = considerados.length - sinFecha.length;

    var s = el("div", "seccion");
    s.innerHTML = '<div class="seccion-cab"><h2>Ultimas 2 semanas</h2><span class="cuenta">' +
      nuevos.length + "</span></div><p class='seccion-nota'>" +
      "Favoritos, candidatos y al limite <b>publicados hace " + DIAS_NUEVO + " dias o menos</b>. " +
      "Es la lista para llamar hoy: un aviso recien salido todavia no junto cola. " +
      LEYENDA_SCORE + "</p>";
    if (nuevos.length) {
      var g = el("div", "grilla");
      pintarTanda(g, nuevos, "nuevos", card, s);
    } else {
      s.appendChild(el("div", "vacio",
        conFecha ? "Ninguno de los " + conFecha + " avisos con fecha se publico en las ultimas dos semanas."
                 : "Todavia no hay ningun aviso con fecha de publicacion."));
    }
    cont.appendChild(s);

    if (!sinFecha.length) return;

    /* Este bloque es el que evita el peor resultado: creer que "no hay nada nuevo". */
    var s2 = el("div", "seccion");
    s2.innerHTML = '<div class="seccion-cab"><h2>Sin fecha</h2><span class="cuenta">' +
      sinFecha.length + "</span></div>" +
      "<div class='aviso-dato'><b>De " + considerados.length + " propiedades que te sirven, " +
      "solo " + conFecha + " tienen fecha de publicacion.</b> No es que sean viejas: la fecha " +
      "vive en la ficha de cada aviso y el barrido solo lee el listado. Hasta completarlas, " +
      "esta vista muestra una parte del inventario, no todo el que se publico esta quincena. " +
      "Se completa corriendo <code>python scripts/detalle.py</code> (un pedido por aviso).</div>";
    var g2 = el("div", "grilla");
    pintarTanda(g2, sinFecha, "nuevos-sinfecha", card, s2);
    cont.appendChild(s2);
  }

  // ------------------------------------------------------------------ render

  function pintarPendientes() {
    var n = Object.keys(decisiones()).length;
    var e = $("#pendientes");
    if (CON_SERVIDOR) {
      e.textContent = "se guarda solo";
      e.className = "estado-guardado";
      e.title = "Servido desde localhost: cada decision se escribe en data/eventos.jsonl";
      $("#btn-exportar").hidden = !n;
      return;
    }
    e.textContent = n ? n + " sin exportar" : "modo archivo";
    e.className = "estado-guardado manual";
    e.title = "Abriste el archivo directo. Para que se guarde solo, abri con abrir.bat";
  }

  function diasDesde(fechaISO) {
    if (!fechaISO) return null;
    var p = String(fechaISO).slice(0, 10).split("-");
    if (p.length !== 3) return null;
    var d = new Date(+p[0], +p[1] - 1, +p[2]);
    if (isNaN(d)) return null;
    var hoy = new Date();
    hoy = new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate());
    return Math.max(0, Math.round((hoy - d) / 86400000));
  }

  function pintarBanda() {
    var r = D.resumen || {};
    var banda = $("#banda");

    /* En modo archivo el aviso tiene que ser imposible de pasar por alto: lo que marques
       queda solo en este navegador. El chip chico de la barra no alcanzaba. */
    if (!CON_SERVIDOR) {
      banda.hidden = false;
      banda.className = "banda alerta";
      banda.innerHTML =
        (location.hostname.indexOf("github.io") >= 0
          ? "<b>Solo lectura.</b> <span>Esta es la copia publicada: se actualiza cuando la " +
            "busqueda corre en la compu. Lo que marques desde aca queda <b>solo en este " +
            "telefono</b> y no lo ve nadie mas todavia.</span>"
          : "<b>Modo archivo.</b> <span>Abriste <code>index.html</code> directo, asi que lo que " +
            "marques queda <b>solo en este navegador</b> y no se escribe en el disco. Para que se " +
            "guarde solo: cerra esto y hace doble click en <code>abrir.bat</code>.</span>");
      return;
    }

    /* Tercera version de este texto. Las dos anteriores describian un paso interno del
       pipeline ("sin analisis de fotos", "cobertura de datos 87%") que Mario no tenia por
       que conocer. Lo que hay que explicar es lo que EL VE en pantalla: por que el puntaje
       son dos numeros y no uno. Se explica ese simbolo concreto, no el proceso. */
    var lineas = [];

    /* LO PRIMERO: hace cuanto que no se baja nada del portal.
       El 2026-08-21 Mario dijo "siempre me salen las mismas busquedas" y la causa numero
       uno era que hacia SEIS DIAS que no corria el barrido. En la pantalla no habia forma
       de saberlo: el pie dice "generado", que se actualiza con cualquier rebuild aunque no
       se haya tocado la red. Un sistema congelado que no avisa que esta congelado se lee
       como un mercado quieto — y es la unica conclusion que este proyecto no puede
       permitirse. Por eso ocupa la banda entera y no un chip. */
    var dias = diasDesde((D.meta_avisos || {}).ultimo_barrido);
    if (dias === null || dias >= 1) {
      var comoActualizar = "Para actualizar: cerra esto y hace doble click en <code>abrir.bat</code>.";
      if (dias === null || dias >= 3) {
        banda.hidden = false;
        banda.className = "banda alerta";
        banda.innerHTML = "<b>Estos datos estan viejos.</b> <span>" +
          (dias === null ? "No hay registro de cuando se busco por ultima vez."
                         : "Hace <b>" + dias + " dias</b> que no se baja nada del portal, " +
                           "asi que lo que ves es la foto de ese dia: no es que no haya " +
                           "propiedades nuevas, es que nadie fue a buscarlas.") +
          " " + comoActualizar + "</span>";
        return;
      }
      lineas.push("<b>Ultima busqueda: hace " + dias + (dias === 1 ? " dia" : " dias") +
        ".</b> <span>Lo publicado desde entonces todavia no esta en esta lista. " +
        comoActualizar + "</span>");
    }

    if (r.sin_estado_visual) {
      lineas.push("<b>Los puntajes estan incompletos.</b> <span>Por eso cada propiedad " +
        "muestra <b>dos numeros</b> (por ejemplo <span class='dato'>48</span> y " +
        "<span class='dato'>hasta 66</span>): el primero es lo que tiene comprobado con los " +
        "datos que hay hoy, el segundo hasta donde podria llegar. Se juntan en un solo " +
        "numero cuando alguien mire las fotos y diga si cada propiedad esta reciclada de " +
        "verdad o solo recien pintada.</span>");
    }
    if (r.sin_verificar) {
      lineas.push("<b>Vigencia sin chequear:</b> <span><span class='dato'>" + r.sin_verificar +
        "</span> avisos no se compararon hoy contra el portal. Alguno puede haberse caido.</span>");
    }
    banda.className = "banda";
    if (!lineas.length) { banda.hidden = true; return; }
    banda.hidden = false;
    banda.innerHTML = lineas.map(function (l) { return "<div>" + l + "</div>"; }).join("");
  }

  function render() {
    _porId = null;
    var m = $("#main");
    m.innerHTML = "";
    if (estado.vista === "favoritos") vistaFavoritos(m);
    else if (estado.vista === "nuevos") vistaNuevos(m);
    else if (estado.vista === "explorar") vistaExplorar(m);
    else if (estado.vista === "actividad") vistaActividad(m);
    else vistaDescartados(m);

    var r = D.resumen || {};
    /* De donde sale la lista corta. Sin esto, un portal puede dejar de aportar durante
       dias -o aportar un tercio- sin que se note: la card no decia su origen y el pie
       tampoco. Va sobre la lista corta, no sobre el total: Zonaprop gana el total
       siempre por volumen y ese numero no informa nada. */
    var NOM = { zonaprop: "Zonaprop", mercadolibre: "MercadoLibre", argenprop: "Argenprop" };
    var pp = r.lista_corta_por_portal || {};
    var mix = Object.keys(pp).sort(function (x, y) { return pp[y] - pp[x]; })
      .map(function (k) { return pp[k] + " " + (NOM[k] || k); }).join(" · ");

    $("#pie").textContent = (r.total_avisos || 0) + " avisos · " + (r.descartados || 0) +
      " descartes" + (mix ? " · en la lista corta: " + mix : "") +
      " · dolar BNA " + ((D.meta_avisos || {}).cotizacion_bna_venta || "?") +
      " · generado " + (D.generado || "?") +
      " · ultima busqueda en el portal " + ((D.meta_avisos || {}).ultimo_barrido || "?");

    var n = contarFiltros();
    var pill = $("#filtros-activos");
    pill.textContent = n;
    pill.hidden = !n;

    var nuevos = D.avisos.filter(function (a) {
      var d = diasPublicado(a);
      return a.seccion !== "filtrados" && d !== null && d <= DIAS_NUEVO && pasaFiltros(a);
    }).length;
    var pn = $("#cuenta-nuevos");
    pn.textContent = nuevos;
    pn.hidden = !nuevos;

    var favs = D.avisos.filter(function (a) {
      return a.pinned && a.decision !== "descartado";
    }).length;
    var pf = $("#cuenta-favoritos");
    pf.textContent = favs;
    pf.hidden = !favs;

    pintarPendientes();
  }

  // ----------------------------------------------------------------- eventos

  function leerFiltros() {
    var f = estado.filtros;
    f.precioMin = num($("#f-precio-min").value) || null;
    f.precioMax = num($("#f-precio-max").value) || null;
    f.dorm = num($("#f-dorm").value) || null;
    f.banos = num($("#f-banos").value) || null;
    f.m2 = num($("#f-m2").value) || null;
    f.ext = num($("#f-ext").value) || null;
    f.estado = $("#f-estado").value;
    f.orden = $("#f-orden").value;
    f.barrios = Array.prototype.slice.call($("#f-barrio").selectedOptions).map(function (o) { return o.value; });
    f.tipos = Array.prototype.slice.call($("#f-tipo").selectedOptions).map(function (o) { return o.value; });
    estado.limites = {};
    render();
  }

  function iniciar() {
    var barrios = [], tipos = [];
    D.avisos.forEach(function (a) {
      if (a.barrio && barrios.indexOf(a.barrio) < 0) barrios.push(a.barrio);
      if (a.tipo && tipos.indexOf(a.tipo) < 0) tipos.push(a.tipo);
    });
    barrios.sort(); tipos.sort();
    $("#f-barrio").innerHTML = barrios.map(function (b) { return "<option>" + esc(b) + "</option>"; }).join("");
    $("#f-tipo").innerHTML = tipos.map(function (t) { return "<option>" + esc(t) + "</option>"; }).join("");

    var c = localStorage.getItem(LS_COT) || (D.meta_avisos || {}).cotizacion_bna_venta;
    if (c) $("#cotizacion").value = c;
    var fc = (D.meta_avisos || {}).cotizacion_fecha;
    if (fc) $("#cotizacion").title = "Dolar oficial BNA venta del " + fc;

    $("#tabs").addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      Array.prototype.forEach.call(this.children, function (x) {
        x.classList.remove("on");
        x.setAttribute("aria-selected", "false");
      });
      b.classList.add("on");
      b.setAttribute("aria-selected", "true");
      estado.vista = b.dataset.vista;
      estado.limites = {};
      render();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });

    $("#btn-filtros").addEventListener("click", function () {
      var f = $("#filtros");
      f.hidden = !f.hidden;
      this.setAttribute("aria-expanded", String(!f.hidden));
    });

    $("#filtros").addEventListener("change", leerFiltros);
    $("#filtros").addEventListener("input", function (e) { if (e.target.type === "number") leerFiltros(); });

    $("#f-chips").addEventListener("click", function (e) {
      var c = e.target.closest(".chip");
      if (!c) return;
      var on = c.getAttribute("aria-pressed") !== "true";
      c.setAttribute("aria-pressed", String(on));
      estado.filtros.flags[c.dataset.flag] = on;
      // "Solo CABA" y "Solo Zona Norte" son excluyentes: con los dos encendidos no
      // quedaria un solo aviso, y un filtro que vacia la pantalla se lee como roto.
      var opuesto = c.dataset.flag === "solo_caba" ? "solo_gba"
                  : c.dataset.flag === "solo_gba" ? "solo_caba" : null;
      if (on && opuesto) {
        estado.filtros.flags[opuesto] = false;
        var otro = $("#f-chips").querySelector('[data-flag="' + opuesto + '"]');
        if (otro) otro.setAttribute("aria-pressed", "false");
      }
      estado.limites = {};
      render();
    });

    $("#btn-limpiar").addEventListener("click", function () {
      ["#f-precio-min", "#f-precio-max", "#f-dorm", "#f-banos", "#f-m2", "#f-ext"].forEach(function (s) { $(s).value = ""; });
      $("#f-estado").value = "";
      $("#f-orden").value = "default";
      Array.prototype.forEach.call($("#f-barrio").options, function (o) { o.selected = false; });
      Array.prototype.forEach.call($("#f-tipo").options, function (o) { o.selected = false; });
      Array.prototype.forEach.call($("#f-chips").children, function (c) { c.setAttribute("aria-pressed", "false"); });
      estado.filtros.flags = {};
      leerFiltros();
    });

    $("#cotizacion").addEventListener("input", function () {
      localStorage.setItem(LS_COT, this.value);
      render();
    });

    $("#btn-exportar").addEventListener("click", function () {
      var d = decisiones();
      var payload = {
        exportado: new Date().toISOString(),
        cotizacion_bna_venta: cotizacion(),
        decisiones: Object.keys(d).map(function (k) { return d[k]; })
      };
      var blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "decisiones.json";
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
      if (window.confirm("Descargado decisiones.json.\n\nMovelo a web/pendiente.json y avisame.\n\nAceptar = vaciar las decisiones locales.\nCancelar = dejarlas guardadas.")) {
        localStorage.removeItem(LS_DEC);
        render();
      }
    });

    $("#velo").addEventListener("click", cerrarPanel);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && estado.abierto) cerrarPanel();
    });

    aplicarDecisionesLocales();   // antes del primer render, o el corazon miente
    pintarBanda();
    render();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar);
  else iniciar();
})();
