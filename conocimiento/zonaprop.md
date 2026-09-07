# Zonaprop — como funciona, slugs y trampas

> Mantenido por el **Buscador edilicio**. Todo lo que esta marcado *(verificado)* viene de
> corridas reales; lo marcado *(hipotesis)* hay que confirmarlo antes de apoyarse en ello.

## URL y slugs

Los filtros van **en el path, no en query params**:

```
https://www.zonaprop.com.ar/{tipo}-alquiler-{barrio}-{features}-{N}-ambientes-{orden}.html
```

| Modificador | Slug |
|---|---|
| Con terraza | `-con-terraza` |
| Con patio | `-con-patio` |
| 2+ banos | `-mas-de-2-banos` |
| Sin cochera | `-sin-garages` |
| Dueno directo | `-dueno-directo` |
| A estrenar | `-a-estrenar` |
| Orden precio ascendente | `-orden-precio-ascendente` |
| Publicado ultimo mes | `-publicado-hace-menos-de-1-mes` |
| Paginado | `-pagina-2` |

**`-orden-precio-ascendente` NO alcanza solo, y creerlo fue el peor error del proyecto.**
Pone lo barato en la pagina uno, si — pero pedir "las N primeras paginas por precio" devuelve
**exactamente el mismo conjunto todos los dias**. Un aviso nuevo no entra arriba: entra en el
medio, en el lugar que le da su precio. Medido el 2026-08-21: 855 departamentos bajados de un
universo de 6.991 en las 9 zonas (12%), y ese 12% era el mas barato de cada barrio, o sea
monoambientes — solo 43 tenian 2 dormitorios y 3 ambientes.

**Los ordenes, y para que sirve cada uno** *(los dos verificados el 2026-08-21)*:

| Orden | Para que |
|---|---|
| `-orden-precio-ascendente` | **cubrir**: lo barato primero, combinado con un filtro de ambientes |
| `-orden-publicado-descendente` | **enterarse**: lo recien publicado arriba. Respeta el barrio |

### Filtros de la URL: cuales filtran de verdad *(probados uno por uno, 2026-08-21)*

| Slug | Veredicto |
|---|---|
| `-3-ambientes` `-4-ambientes` `-mas-de-5-ambientes` | **FILTRAN.** Palermo: 3.185 avisos (107 pag) -> 599 (20) con 3 ambientes |
| `-mas-de-2-ambientes` | **MIENTE: es ">=2".** Saavedra devolvio 98 avisos y los 30 de la primera pagina eran de 2 ambientes |
| `-menos-de-2000-dolares` | **NO FILTRA NADA.** Saavedra devolvio 158 de 158, y ordenado descendente el primero era de USD 8.000 |

La leccion es la misma de siempre en este portal: **un filtro que devuelve 200 no es un filtro
que funciono.** Hay que mirar los valores de lo que volvio, no el total ni el codigo HTTP.

**NO usar el filtro de fecha de publicacion.** La base ya resuelve que es nuevo con `first_seen`.
Filtrar por fecha esconde inventario vigente: el mejor PH de Colegiales tiene un aviso de meses y
sigue disponible. Guardar `publicado_hace_dias` como dato y marcar "verificar vigencia" arriba de
60 dias, pero no esconderlo.

## Prefijo del clasificado *(hipotesis, 12 muestras)*

Las URLs de detalle arrancan con un prefijo de 8 letras: `alcl` + 2 letras de tipo + 2 letras de
publicador.

```
alcl · ca|ph · in|pa
 |      |       |
 |      |       +-- in = inmobiliaria, pa = particular (dueno directo)
 |      +---------- ca = casa, ph = PH
 +----------------- alquiler clasificado
```

Evidencia: `alclcapa-dueno-alquila-casa-antigua-reciclada-...` (Giribone 1980) dice literalmente
"dueno alquila" y trae `pa`. `alclphpa-...` (Alvarez Thomas 225). Los otros diez traen `in`.

**Para que sirve:** permite marcar `dueno_directo` desde la URL del listado, sin abrir el detalle
ni gastar un request. Es barato de verificar y vale la pena hacerlo en la primera corrida real
(comparar el flag contra lo que dice la ficha del aviso en 20 casos).

## Trampas verificadas

**`casa-` y `casas-` no son lo mismo** *(verificado)*. El plural devuelve solo casas. El singular
es en realidad una busqueda de todos los tipos e **incluye PH**: en Saavedra devolvio 35 contra 5.
Casi todos los buenos hallazgos salieron del singular. **Usar siempre el singular.**

**El campo `dorm.` miente** *(verificado)*. Se vio "4 amb. 0 dorm." y avisos con 3 dormitorios
donde el tercero es un escritorio. **Cruzar siempre contra la descripcion.** El campo del listado
sirve como pre-filtro grueso, nunca como dato final.

**Superficie descubierta como proxy de terraza** *(verificado)*. Cuando
`m2_totales - m2_cubiertos > 30` hay algo interesante aunque el aviso solo diga "balcon".
**No filtrar por el tag `con-terraza` en PH y casas:** el volumen es bajo (5 a 10 por barrio) y se
pierden avisos que declaran la terraza en un campo suelto. El filtro de terraza sirve para
departamentos, donde el volumen justifica recortar.

**Avisos de prueba** *(verificado)*. Hay publicaciones de sistemas de CRM con textos como
"propiedades ficticias para pruebas de tokko broker", con precios y superficies absurdas.
Descartar todo lo que contenga `ficticia`, `de prueba`, `no contactar`, y todo lo que declare mas
de 2.000 m2 totales.

**Imagenes generadas por IA** *(verificado)*. Algunos avisos aclaran al final que las fotos fueron
creadas o editadas con IA. Detectar esa clausula y **bajar la confianza de la evaluacion visual**
(que dispara el cap de score en 70).

## Deduplicacion — **el precio NO va en la clave**

**Nunca por ID.** La clave es **direccion normalizada + m2 cubiertos**, y nada mas.

Meter el precio parecia razonable y estaba mal. Casos reales de la primera corrida grande:

| Caso | Que pasaba |
|---|---|
| **Conde 4700** | la MISMA inmobiliaria lo publico dos veces, una en pesos ($ 2.400.000) y otra en dolares (USD 1.590). Con el precio en la clave nunca matcheaban: quedaron **tres** Conde 4700 en la lista |
| **Malasia 800** | la misma casa de 300 m2 listada por tres inmobiliarias a USD 4.500, 4.900 y 5.200 |

Una propiedad es la misma aunque tres agencias le pongan tres precios. Lo que la identifica
es la direccion y los metros cubiertos.

Si falta la altura o faltan los m2, **no se fusiona**: sin esos dos no se puede afirmar que
dos avisos son el mismo inmueble, y fusionar de mas es peor que mostrar de mas.

Y la deduplicacion corre sobre **todo el inventario**, no solo sobre lo recien bajado: un
aviso nuevo puede ser el mismo inmueble que uno que ya estaba en la base. Asi aparecio el
tercer Conde 4700.

### La direccion viene sucia

Los anunciantes pegan anotaciones al campo direccion:

    "CONDE 1985. Entre Echeverria y Sucre, antonio j. de"
    "GODOY CRUZ 3213. Entre Av Libertador y ..."

Sin cortar en el primer punto/coma y en `entre|esq|casi`, la direccion normalizada se
quedaba con media cuadra adentro, la altura no se podia extraer y **el veto por descarte no
matcheaba**: Conde 1985 estaba descartado por mascotas y volvia a aparecer igual.

Y cuando aparece un duplicado, **fusionar los campos en vez de descartar la copia**: cada
publicacion trae datos que la otra omite.

> Caso real verificado: el mismo triplex publicado por la misma inmobiliaria como Saavedra y como
> Belgrano. Solo la version Belgrano decia "se alquila sin muebles" — o sea que quedarse con una
> sola de las dos publicaciones habria dejado el filtro de amoblado sin resolver.

Normalizacion de direccion: minusculas, sin acentos, sin `av.` / `avenida` / `calle`, calle +
altura exacta. **La altura no se redondea para el veto**: Conde 4700 es favorito, Conde 4400 es
descarte por uso comercial y Conde 1985 es descarte por mascotas. Tres destinos en la misma calle.

## Rate limiting y etiqueta

- Pausa de **2 a 3 segundos** entre requests.
- User-Agent normal (el del config).
- **Dos corridas por dia como maximo.**
- Si empiezan a volver 403: **bajar la frecuencia**, no rotar proxies ni evadir bloqueos. Esto es
  una busqueda personal, no un negocio de datos. Si un portal corta, avisar.

## Alertas nativas

Zonaprop tiene "Crear alerta" en cada busqueda. **Armarlas a mano en las URLs principales como red
de seguridad** para cuando el scraper se rompa y no nos enteremos. Es el unico mecanismo del
sistema que no depende de que el codigo siga funcionando.

Estado: **pendiente**, requiere cuenta logueada en Zonaprop (accion manual de Mario).

## Acceso — RESUELTO *(verificado 2026-08-14, 13 requests)*

**No hay proteccion anti-bot en la ficha de detalle.** `urllib` de la biblioteca estandar con
User-Agent de navegador devuelve **HTTP 200** y el HTML completo (~520 KB). Ni captcha, ni
DataDome, ni Cloudflare, ni pagina de desafio. Se bajaron 12 fichas y 72 imagenes seguidas sin un
solo bloqueo, respetando la pausa de 2-3 s.

> La sesion anterior habia advertido que esto podia requerir Playwright. **Era exagerado.** No hace
> falta ninguna dependencia nueva. Si alguna vez empieza a devolver 403, la respuesta sigue siendo
> bajar la frecuencia, no evadir.

## Estructura del LISTADO *(verificado 2026-08-14, 14 paginas, 330 avisos)*

`window.__PRELOADED_STATE__ = {...}` y adentro:

    listStore.listPostings[]   los 30 avisos de la pagina
    listStore.paging           {currentPage, totalPages, total}

**El listado trae casi todo lo que trae la ficha**, y eso cambia la economia del sistema:
un request devuelve 30 propiedades con descripcion completa, fotos, expensas, antiguedad e
inmobiliaria. Abrir la ficha de cada aviso —lo que se creia obligatorio— es innecesario
para el grueso: se reserva para revalidar favoritos y para bajar fotos a local.

| Campo del item | Contenido |
|---|---|
| `postingId`, `url`, `title` | identidad |
| `generatedTitle` | `"PH · 37m² · 2 Ambientes"` |
| `realEstateType` | `{"name": "PH"｜"Casa"｜"Departamento"}` |
| `postingLocation` | `address.name` (la direccion) y `location.name` (el barrio) |
| `priceOperationTypes` | precio y moneda. **La mitad publica en pesos** |
| `expenses.amount` | las expensas, que en la ficha cuestan mas de sacar |
| `antiquity` | antiguedad en anos |
| `mainFeatures` | los mismos codigos CFT que la ficha (ver abajo) |
| `visiblePictures.pictures[]` | fotos, 5 tamanos cada una |
| **`descriptionNormalized`** | **la descripcion completa** — habilita `reglas.py` sin abrir la ficha |
| `publisher` | la inmobiliaria: nombre y URL |

### Paginacion

    Pagina 1:  {tipo}-alquiler-{barrio}-orden-precio-ascendente.html
    Pagina N:  {tipo}-alquiler-{barrio}-orden-precio-ascendente-pagina-{N}.html

Cuantas paginas hay se lee de `listStore.paging.totalPages`, asi que no se piden de mas ni
se corta una busqueda por la mitad.

### Volumen real por barrio *(una corrida)*

Palermo 114 · Belgrano 72 · Nunez 39 · Saavedra 34 · Almagro 28 · Colegiales 27 ·
Villa Ortuzar 16. Total 330 avisos en **14 requests**.

## Estructura de la FICHA DE DETALLE *(verificado)*

No hay `__NEXT_DATA__` ni `__PRELOADED_STATE__` — buscarlos da cero. Los datos estan en un bloque
de `<script>` con asignaciones de la forma `'clave': <valor JSON o string citado>`. Las utiles:

| Clave | Contenido |
|---|---|
| `'pictures'` | lista de fotos. Cada una trae **5 variantes de tamano** (`url1200x1200`, `url730x532`, `url360x266`, `url215x159`, `url100x75`) y un `title` que es la **leyenda** de la foto ("1 FRENTE", "Living", "cocina"). La leyenda dice que ambiente es cada imagen: sirve para el analisis visual |
| `'mainFeatures'` | ver tabla de codigos abajo |
| `'description'` | descripcion completa con HTML adentro (`<br>`). Es la larga; el `<meta name="description">` viene truncado |
| `'price'` | `'USD 1.400'` o `'$ 2.400.000'`. **La mitad de los avisos publica en pesos** |
| `'publicationDateFormatted'` | ISO de la PRIMERA publicacion. Es el dato de antiguedad del aviso |
| `'address'` | `{"name": "Giribone 1980", "visibility": "EXACT"}` |
| `'realEstateType'` | `{"name": "Casa"}` / `"PH"` / `"Departamento"` |
| `'publisherTypeId'` | **1 = particular (dueno directo)**, otro = inmobiliaria |

### Codigos de `mainFeatures`

| Codigo | Campo |
|---|---|
| `CFT100` | superficie **TOTAL** en m2 |
| `CFT101` | superficie **CUBIERTA** en m2 |
| `CFT1` | ambientes |
| `CFT2` | dormitorios |
| `CFT3` | banos |
| `CFT5` | **antiguedad en anos** |
| `1000029` | orientacion (N, S, E, O, NE...) |
| `1000027` | luminosidad |

> ⚠️ **CFT100 es TOTAL, CFT101 es CUBIERTA.** Confundirlas es el error que tenia la carga manual:
> Giribone 1980 figuraba con 120 m2 cubiertos y en realidad son 120 **totales** y 80 cubiertos.
>
> Y el corolario bueno: `CFT100 - CFT101` da la **superficie descubierta**, que es el mejor proxy
> de exterior que existe y ahora se tiene para todos los avisos. Es dato estructurado del portal,
> no prosa del anunciante — y hay avisos que declaran 64 m2 de terraza sobre 40 de descubierto.

### Hipotesis del prefijo — **CONFIRMADA 12/12**

`alcl` + `ca|ph` + `in|pa`, donde `pa` = particular. Los dos avisos con `pa` de la muestra
(Giribone 1980 y Alvarez Thomas 225) tienen `publisherTypeId: 1`; los diez con `in`, no. Se puede
marcar `dueno_directo` desde la URL del listado sin abrir el detalle ni gastar un request.

### Fotos

Patron: `https://imgar.zonapropcdn.com/avisos/1/<id-partido-en-pares>/<tamano>/<foto>.jpg`

El `<id-partido-en-pares>` es el id del aviso a 10 digitos partido de a dos: el aviso 49100787 da
`00/49/10/07/87`. El CDN **no pide referer ni cookie**; un GET pelado alcanza. Se usa `720x532`,
que pesa ~50 KB y alcanza para la card y para el carrusel (6 fotos por aviso ≈ 290 KB).
