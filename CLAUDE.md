# Memoria operativa — busqueda de alquiler CABA

> Memoria entre sesiones. Se actualiza al final de cada corrida.
> Ultima actualizacion: **2026-08-31** (sesion 16: la cobertura de departamentos no
> corria nunca — la rotacion giraba en la dimension equivocada).
>
> **Las convenciones de trabajo viven en la skill `busqueda-alquiler`**
> (`~/.claude/skills/busqueda-alquiler/SKILL.md`): como correr el sistema, el sistema
> visual de la pagina, el vocabulario de los avisos y como reportar. Este archivo guarda
> el ESTADO: que se sabe hoy, que esta roto, que falta decidir.

## La convencion mas util: el numero

Cada propiedad tiene un `#N` corto y estable. Mario dice **"descarta el 3"** y eso es:

```bash
python scripts/eventos.py descarte 3 "la cocina esta hecha pelota"
```

El numero **nunca se reasigna**: si el #7 de hoy fuera otra propiedad que el #7 de ayer,
cualquier conversacion pasada quedaria inservible.

| # | Propiedad | | # | Propiedad |
|---|---|---|---|---|
| 1 | Giribone 1980 · V. Ortuzar | | 7 | Jose A. Cabrera 5962 · P. Hollywood |
| 2 | Alvarez Thomas 225 · Colegiales | | 8 | Conde 4700 · Saavedra |
| 3 | Plaza 2474 · Belgrano R | | 9 | Betbeder 1307 · Nunez |
| 4 | Garcia del Rio 4000 · Saavedra | | 10 | Paroissien 4400 · Saavedra |
| 5 | Nunez 2306 · Nunez | | 11 | Gorriti 4989 · Palermo Soho |
| 6 | Vedia 3000 · Saavedra | | 12 | Superi 4300 · Saavedra |

## Que es este proyecto

Un sistema de largo plazo, no una busqueda puntual: corre todos los dias, acumula historia,
aprende de las devoluciones y va afinando que es "el correcto".

**Lo peor que puede pasar es mostrar dos veces algo ya descartado.** Todo lo demas es secundario.

## Como se usa

```
abrir.bat                        <- DOBLE CLICK. ES EL UNICO QUE HACE FALTA.
                                    Si ya se busco hoy, abre la pagina directo.
                                    Si no, busca primero (5-15 min) y despues abre.
actualizar.bat                   <- forzar una busqueda aunque ya se haya hecho hoy.
```

Ademas corre **solo todos los dias a las 9:00** (tarea de Windows
`BusquedaAlquiler-Diaria`), asi que lo normal es que `abrir.bat` abra directo.

```bash
python scripts/main.py           # corrida completa
python scripts/main.py --sin-red # re-scoring y rebuild, sin tocar la red
python scripts/detalle.py        # fichas + fotos + revalidacion de vigencia
python scripts/cotizacion.py     # dolar BNA del dia y recalculo de precios
python scripts/reglas.py         # clasificacion por vocabulario (gratis)
python scripts/score.py          # recalcula y muestra el ranking
python scripts/eventos.py descarte 3 "muy sobre la avenida" tranquilidad  # <- desde el chat
                                 #   ^numero  ^motivo (obligatorio)  ^categoria (opcional)
python scripts/eventos.py csv    # planilla para Excel (solo lectura)
```

`web/index.html` tambien abre con doble click, pero en ese modo las decisiones quedan en el
navegador hasta que las exportes. Usar `abrir.bat`.

## Arquitectura de datos — la decision central

```
data/avisos.json      HECHOS.      scrapeados. Se pueden borrar y volver a bajar.
data/eventos.jsonl    DECISIONES.  append-only. Es lo UNICO irreemplazable del proyecto.
        |
        +--> replay determinista --> descartados.json · favoritos.json · visitas.json
                                     (100% derivados: si se pierden, se regeneran)
```

**Por que separado:** si las decisiones viven mezcladas con los datos scrapeados, un re-scrapeo
te puede pisar un descarte. Separadas, no hay forma.

**Por que append-only:** escribir es agregar una linea, nunca modificar. Dos procesos pueden
escribir sin pisarse, y el historial completo queda como auditoria del bucle de aprendizaje.

**Por que NO Excel como almacen** (se evaluo, fue la sugerencia de Mario):
- Excel **bloquea el archivo mientras esta abierto**: la corrida diaria falla si la planilla
  quedo abierta.
- Reformatea solo: fechas, numeros con punto, acentos en CSV.
- Los datos son anidados (lista de exteriores, historial de precio, listas de a-favor/en-contra);
  aplanarlos pierde estructura.
- **Como superficie de LECTURA si sirve**: `python scripts/eventos.py csv` genera
  `data/propiedades.csv` para abrir, ordenar y filtrar en Excel. Es una via, no un ida y vuelta:
  no se re-importa, porque tener dos escritores sobre el mismo estado es como se pierden datos.

**Regla:** todo lo que escribe una decision pasa por `eventos.registrar()`. Un solo camino.

## Orden de las pasadas (de mas barato a mas caro)

1. `parse.py` — listado. Gratis. Trae poco y el campo `dorm.` miente.
2. `detalle.py` — ficha + fotos. Un request por aviso. **Solo para los que pasan los duros o
   estan marcados a mano.**
3. `reglas.py` — vocabulario deterministico. Gratis. Resuelve los binarios.
4. `clasificar.py pendientes` / `aplicar` — mirar las fotos. **Gratis: lo hace Claude en la
   sesion, sin API ni creditos.** Solo sobre candidatos con fotos locales, por score piso.

## Decisiones de diseno que conviene no reabrir sin motivo

**El score es un RANGO piso–techo.** Normalizar sobre lo conocido premiaba la falta de datos.
El piso es lo demostrado; el techo, lo que daria si lo desconocido saliera bien. Se ordena por piso.

**El desempate por estado usa `estado_visual` (fotos), NO `estado` (texto).** Usar el de texto
ordenaba mal: dejaba arriba avisos de score bajo porque el anunciante escribio "reciclado", y
hundia a Conde 4700 (63) por debajo de Plaza 2474 (40) porque uno se callo sobre el estado.

**El exterior sale de `m2_totales - m2_cubiertos` del portal**, no de la prosa. Es dato
estructurado y ya excluye lo techado por definicion. La prosa exagera: hay avisos que declaran
64 m2 de terraza sobre 40 de superficie descubierta.

**`estado: null` y `estado: "sin_clasificar"` son distintos.** El primero es el anunciante
callandose (penaliza 20). El segundo es que nosotros no lo leimos (no penaliza, deja score parcial).

**El veto de descartados va por calle + altura EXACTA.** Conde 4700 favorito, Conde 4400 descarte
por uso comercial, Conde 1985 descarte por mascotas.

**Los favoritos marcados a mano no se filtran nunca**, aunque fallen un duro.

**El precio no entra en el score.** Ya filtra como duro.

**Las reglas nunca pisan a la API** (`confianza_texto == "alta"` gana), y **emiten siempre el
campo, incluido el `None`**: si no lo emitieran, un valor equivocado de una corrida vieja
sobrevive a la correccion de la regla que lo produjo. **Unica excepcion: `sobre_avenida`**,
que no es lectura de prosa sino un hecho sobre la direccion, y se recalcula siempre.

**El juicio propio vive aparte del dato scrapeado.** `analisis.json` (prosa) y
`clasificacion_visual.json` (lo que se ve en las fotos) no estan en `avisos.json` porque el
proximo barrido los pisaria. `build.py` los fusiona **antes** de puntuar.

## Decisiones tomadas por Mario el 2026-08-14

**El perfil original estaba mal en dos duros.** Sus palabras: *"no me interesa tanto los
metros cuadrados si algo medianamente grande, me interesa mas el tema de las habitaciones.
minimo 2, 3 amb minimo, idealmente dos banos, o bano y toillet, cochera, jardin o terraza
amplia"*. Aplicado: dormitorios 3 -> **2**, ambientes -> **3 minimo**, m2 cubiertos 90 ->
**60** (deja de ser criterio). El score bajo `m2_cubiertos` de 20 a 10, subio `banos` a 12
con media unidad por toilette, y sumo `cochera` con 8. **El inventario alcanzable paso de
43 a 106.**

**El presupuesto de USD 2.000 es techo firme.** No se toca, aunque 82 avisos cumplan todo
lo demas y caigan solo por precio.

**La garantia, por fin definida:** caucion + recibos/facturacion + propietaria en **GBA**.
**No tiene propietaria en CABA**, que es la que piden por defecto. Ver `garantia.md`: el
primer filtro de una operacion no es el precio, es si aceptan caucion.

**Zonas sumadas: Villa Urquiza y Coghlan.** Villa Urquiza resulto el mejor hallazgo del
proyecto: 46 avisos, 41 % de tasa de candidatos y **9 duenos directos**, mas que Saavedra.

### Almagro afuera (2026-08-23)

Salio de `zonas.incluidas`. Estaba desde el config inicial y nunca se habia revisado: no
es del corredor Colegiales-Saavedra, esta pegado a Once. La evidencia estaba antes de
preguntar — 337 avisos, 18 en la lista corta, **cero favoritos**, y los 5 unicos eventos
del barrio son los 5 descartes ("no me gusta", "cara para lo que es", "se ven poco
mantenidos y medio viejos"). La lista corta paso de 199 a 186 y el barrido deja de gastar
pedidos ahi. Como la comparacion de zona es por substring, tambien salieron Almagro Norte
(76) y Almagro Sur (25).

**La leccion no es Almagro: es que ninguna zona se habia vuelto a mirar desde el dia uno.**
El resto tiene tasas de candidato muy distintas (Villa Ortuzar 11,3% · Villa Urquiza 9,5% ·
Saavedra 8,8% · Belgrano 2,6% · Coghlan 2,3%) y nadie las reviso nunca.

### Descartar sin motivo (2026-08-24)

Mario: *"a veces no tengo ganas de poner la razon"*. El motivo paso de obligatorio a
**opcional** en los tres caminos: la pagina, `POST /api/evento` y la CLI.

**Pero el descarte mudo NO queda vacio: queda con categoria `sin_motivo`.** La sesion 10
ya habia visto que un motivo forzado ensucia mas de lo que aporta (por eso entro el chip
"no me gusta"); esto es el paso siguiente, sin perder la trazabilidad. Y `sin_motivo` es
distinto de `sin_categoria`: uno es *no lo quiso decir*, el otro es *lo dijo y no lo
clasificamos*. Es la misma distincion que el proyecto ya hace entre `estado: null` y
`estado: "sin_clasificar"`; metidos en el mismo balde, no se sabe si es trabajo pendiente
o silencio deliberado.

En la pagina **la etiqueta del boton sigue al textarea**: dice "Descartar sin motivo"
cuando esta vacio y "Descartar" cuando escribis. El aviso de que se va a guardar sin
razon tiene que estar donde se hace el click, no en un cartel aparte. Y sigue habiendo
"deshacer" en la tostada.

**Lo que hay que hacer con esto:** cuando `sin_motivo` se acumule, ofrecerle a Mario
etiquetar la tanda de una (mostrarle los N juntos), en vez de dejar que el bucle de
aprendizaje se vacie de a poco sin que nadie lo note.

## Contradicciones abiertas (necesitan decision de Mario)

### 0. El minimo combinado de m2 quedo sin resolver — y ya no importa igual

Se propuso reemplazar "90 m2 cubiertos" por "110 combinado con piso de 70". Mario contesto
que **los metros no le interesan tanto**, asi que el minimo bajo a 60 y el debate perdio
sentido. Queda anotado que la propuesta era **mas estricta, no mas laxa** (daba 40
candidatos contra 43): sacaba propiedades de 95 m2 sin exterior. Si algun dia el exterior
tiene que ser duro y no blando, esa es la forma.

### 1. La tolerancia de "Al limite" deja afuera su propio caso testigo

Regla: falla un solo duro por **menos del 15%** -> se muestra. Ejemplo dado: Alvarez Thomas 225,
73 m2 contra un minimo de 90. **73 vs 90 es -18,9%**: con el 15% ese caso no entra.

Ahora hay mas evidencia que la sesion pasada. Con los m2 reales del portal:

| | cubiertos | descubiertos | suma | veredicto de Mario |
|---|---|---|---|---|
| Alvarez Thomas 225 | 73 | 47 | 120 | **aceptado** |
| Donado 3686 | 70 | ? | ? | rechazado |
| Giribone 1980 | **80** | 40 | 120 | aceptado (con 120 mal cargados) |

Giribone tiene 80 m2 cubiertos, no 120: entra a "Al limite" (-11%) sin que nadie lo decidiera.
Dos de los tres casos suman exactamente **120 m2 entre cubierto y descubierto**.

Propuesta: reemplazar el minimo de 90 cubiertos por **minimo combinado de 110 m2 (cubierto +
descubierto) con piso duro de 70 en cubiertos**. Explica los tres casos sin excepciones.
**No aplicado: espera confirmacion.**

### 2. Que hacer con los avisos de uso mixto

Dos favoritos ofrecen la propiedad **tambien para uso comercial**: Giribone 1980 ("ESPECIAL
PRODUCTORAS: ZONA DISTRITO AUDIOVISUAL") y Plaza 2474 (el aviso arranca con "uso comercial / o
vivienda"). No los descalifica para vivienda —el config acepta `ambos`— pero cambia contra quien
competis y que le interesa al dueno. Hoy se muestra como aviso en la ficha. Si Mario quiere que
sea descarte, es un renglon de `config.yaml`.

## Hallazgos verificados en la sesion 2

**Zonaprop no tiene proteccion anti-bot en la ficha.** `urllib` pelado, HTTP 200, 12 fichas y 72
imagenes sin un bloqueo. La advertencia de la sesion 1 sobre Playwright era exagerada.

**Hipotesis del prefijo de URL: CONFIRMADA 12/12.** `alcl`+`ca|ph`+`in|pa`, `pa` = particular.
Coincide con `publisherTypeId: 1` en los dos casos de dueno directo.

**La carga manual de la semilla estaba bien salvo dos casos**: Giribone (120 -> 80 m2 cubiertos)
y Gorriti (120 -> 90). Los otros diez coincidian exactos.

**Los 12 favoritos siguen publicados.** Primera revalidacion real del proyecto.

**La mitad de los avisos publica en pesos.** La cotizacion BNA del dia (1515,00) coincide con la
que Mario habia usado a mano en 6 de 7 conversiones.

**Gorriti 4989 bajo de precio.** La semilla decia USD 1.518 (= $2.300.000 a 1515); hoy publica
$2.000.000 = **USD 1.320**. Un 13% menos.

**Giribone 1980 lleva 1653 dias publicado** (desde 2022-02-02) y tiene 75 anos de antiguedad.
Era el #1 del ranking de la sesion 1; hoy es el #7.

**Bug de reglas que costo encontrar:** buscar `"vacio"` como substring daba positivo dentro de
`"conservacion"` (conser-VACIO-n) y marcaba avisos como "se entrega vacio". Todo el matching de
vocabulario va con `\b`. Del mismo tipo: `"equipada"` matcheaba *cocina* equipada y `"con muebles"`
matcheaba "cocina con muebles nuevos" — las dos marcaban favoritos como amoblados.

**Bug de replay:** al principio `aplicar()` no reseteaba los campos que son propiedad de la
bitacora, asi que borrar un evento no revertia nada. Se arreglo reseteando primero y sembrando la
semilla como eventos, para que la bitacora sea el registro COMPLETO y los derivados sean 100%
derivados.

## El 403 del 2026-08-14 — que lo causo y como no repetirlo

Zonaprop devolvio **403 en la pagina 10** de un barrido. No fue por la frecuencia: fue por
un bug propio.

La lista de barrios del config se escribio en **dos lineas**. El parser de YAML de este
proyecto lee linea por linea y no sabe juntarlas, asi que devolvio el string crudo
`"[Palermo, ..., Villa Ortuzar,"` — e iterar sobre un string da **caracteres**. El barrido
pidio entonces la busqueda del barrio `"["`, que en Zonaprop es la busqueda **sin barrio**:
toda CABA, 476 paginas. Bajo 9 antes de que el portal cortara, y metio en la base avisos de
Pinamar, Carilo y Lomas de Zamora.

Tres defensas puestas despues:

1. `lib_config` **rompe fuerte** si encuentra una lista o un mapa YAML sin cerrar en una
   sola linea, en vez de devolver un string que se itera como caracteres.
2. `fetch.py` saltea cualquier barrio cuyo slug quede vacio o con menos de 3 letras.
3. El duro `zona` ahora exige que el barrio **este en las zonas incluidas**, no solo que no
   este en la lista negra. Antes alcanzaba con no estar prohibido.

Y `main.py --desde-cache` reprocesa todo lo bajado **sin tocar la red**, que es lo que hay
que usar despues de un 403 o cuando cambia el parser.

**La leccion:** el rate limit protege del abuso deliberado, no del bug. Una lista mal
parseada genero un patron de requests indistinguible de un scraper agresivo.

## Hallazgos de la sesion 4 (primer barrido completo)

**El listado de Zonaprop trae casi todo lo que trae la ficha.** Un request = 30
propiedades con descripcion completa, fotos, expensas, antiguedad e inmobiliaria. Se creia
que habia que abrir la ficha de cada aviso; no hace falta. La ficha quedo reservada para
(a) revalidar favoritos y (b) bajar fotos a local de la lista corta. Esto cambio el costo
del sistema en un orden de magnitud: **330 avisos en 14 requests**.

**284 avisos en base, 31 candidatos.** Ver `conocimiento/mercado.md` para la lectura.

**Tres bugs de deduplicacion, todos reales, todos encontrados mirando la lista:**

1. *El precio no puede formar parte de la clave.* Conde 4700 aparecia **tres veces**: la
   misma inmobiliaria lo publico en pesos y en dolares, y con el precio en la clave nunca
   matcheaban. La clave correcta es **direccion + m2 cubiertos**, sin precio.
2. *La deduplicacion tiene que correr sobre TODO el inventario*, no solo sobre lo recien
   bajado: un aviso nuevo puede ser el mismo inmueble que uno que ya estaba en la base.
3. *La direccion viene sucia.* `"CONDE 1985. Entre Echeverria y Sucre, antonio j. de"`
   no permitia extraer la altura, y por eso **el veto por descarte no matcheaba**: Conde
   1985 estaba descartado por mascotas y volvia a aparecer igual.

**Las Cañitas se colaba.** El perfil la excluye, pero se publica *como* Belgrano y *como*
Palermo, asi que filtrar por el campo barrio no alcanza. Ahora hay un duro `zona` que mira
el barrio Y el texto del aviso.

**Explorar tenia el orden al reves.** Al mostrar todo el inventario en una lista plana
ordenada por score, arriba quedaban caserones de USD 15.000: el precio no entra en el score
(filtra como duro), asi que un lote enorme fuera de presupuesto puntuaba mejor que un PH
que si sirve. El orden correcto en una lista plana es **por seccion primero** (favoritos,
candidatos, al limite, resto) y por score dentro de cada una.

## Hallazgos de la sesion 5 (carrusel, descarte, fecha de publicacion)

**El badge del score fallaba por falta de escala, no de concepto.** Decia `70` / `hasta
74`. Mario pregunto que era **tres veces**, y las tres veces yo explique el concepto
(piso, techo, cobertura) en el chat en vez de arreglar lo que se ve. Un numero sin su
escala no se puede interpretar: "hasta 74" no dice hasta 74 **de que**. Ahora dice `70` /
`DE 100` / `↑ 74`. **Si algo se pregunta dos veces, el texto no alcanza: falta un dato en
pantalla.**

**Solo 34 de 103 candidatos tienen fecha de publicacion**, porque `publicado_hace_dias`
sale de la **ficha** y el barrido solo lee el listado. La vista "Ultimas 2 semanas" (12
avisos) muestra los **69 sin fecha** en un bloque aparte con el conteo a la vista: un
filtro que esconde en silencio lo que no tiene dato se lee como "no hay nada nuevo" cuando
en realidad es "no lo sabemos". **Pendiente de decision de Mario:** correr
`scripts/detalle.py` sobre los candidatos (~100 pedidos) para completarlas. No se corrio
por el 403 del mismo dia.

**La fecha estaba duplicada.** El tag `10m publicado` sobre la foto y la fila del cuerpo
decian lo mismo. Quedo un solo lugar con tres estados: verde+NUEVO (<=14 dias), gris,
ambar (>180 dias).



**El mismo bug de persistencia tiene una cara por cada tabla derivada.** El bug del
corazon se arreglo para `D.avisos` y volvio a aparecer en `D.descartados`: en modo
archivo descartabas algo, recargabas, y desaparecia de la grilla (bien) pero **tampoco
figuraba en Descartados** (mal). El motivo recien escrito no quedaba en ningun lado
visible. `aplicarDecisionesLocales()` ahora reconstruye tambien la tabla de descartados.
La regla: al tocar esa funcion, preguntarse **que otra vista lee un derivado que no
toca**.

**El motivo del descarte tenia un agujero: la CLI.** La web y el endpoint del servidor ya
lo exigian; `eventos.py descarte <id>` sin texto escribia un descarte mudo. Ahora falla, y
acepta un cuarto argumento opcional de categoria.

**Los chips de motivo mandan categoria, no solo texto.** Sin eso, cada descarte hecho
desde la pagina caia en `sin_categoria` y el conteo `descartados_por_motivo` de
`build.py` —que es como se detectan los patrones— se iba degradando corrida a corrida.

**`revivir` existia en la bitacora y no tenia via desde la pagina.** Ahora sale de tres
lados: el boton encendido en la card, "deshacer" en la tostada, y "volver a considerar"
en cada fila de Descartados. Los 36 descartes de la semilla no tienen `id` (Mario los
anoto por direccion), asi que la fila los resuelve por `direccion_norm`, igual que
`clave()` en `eventos.py`.

## Hallazgos de la sesion 3 (interfaz)

**Sin paginado, y no es pereza.** Un paginado clasico en una herramienta de busqueda te
hace perder el scroll y acordarte en que pagina estabas. Se resolvio con: `loading="lazy"`
en todas las imagenes + primera tanda de 60 por seccion + un boton que **agrega** la
siguiente. Con 200 avisos por dia el cuello de botella son las imagenes, no el DOM.

**Dos bugs de CSS que costaron una captura cada uno:**

1. `[hidden]` no ocultaba nada: `.btn { display: inline-flex }` es un selector de clase y
   le gana al atributo. Hace falta `[hidden] { display: none !important }`.
2. La barra se apilaba en seis lineas: con `flex-wrap` y un espaciador `flex: 1`, cada
   item se iba a su propia linea. Se arreglo agrupando en dos bloques que envuelven juntos.

**Las capturas de pagina completa mienten con lazy loading.** Las imagenes debajo del fold
no se piden nunca. Para verificar visualmente hay que scrollear primero y esperar el
`decode()`.

**El bug del corazon que volvia (reportado por Mario).** En modo archivo se apagaba un
corazon, se recargaba y volvia prendido. El dato NO se perdia: `guardarDecision()` lo
escribia en `localStorage`, pero el render seguia pintando `a.pinned` tal como venia de
`data.js` y nadie leia el `localStorage` de vuelta. Se arreglo con
`aplicarDecisionesLocales()`, que corre antes del primer render y aplica lo guardado sobre
los datos en memoria, recalculando la seccion con `recomputarSeccion()` (misma logica que
`procesar()` en score.py, usando el `a.duros` que ya viaja en data.js).

**Leccion de eso:** el modo archivo era demasiado silencioso. Un chip chico que decia
"modo archivo" no alcanzaba para que se notara que nada se estaba escribiendo en disco.
Ahora ese modo pinta una banda roja imposible de pasar por alto. **Si un modo degradado no
se nota, el usuario cree que el sistema esta roto — y tiene razon en creerlo.**

## Sesion 6 — auditoria con numeros (2026-08-14)

**La API nunca fue el cuello de botella, y yo lo dije mal tres veces.** Se midio: de los
106 candidatos, los puntos de peso perdidos por falta de dato son **cochera 720 ·
expensas 425 · parrilla 225 · orientacion 92 · estado 80**. Pero el numero de `estado`
enganaba: 70 candidatos tienen `estado = None`, que el score puntua **20 sobre 100 con
certeza** (la regla "el silencio no es neutro"). O sea que no aparecia como "sin dato" y
sin embargo era el criterio de peso 20 decidido a ciegas — y ademas el primer desempate
del orden. **Mirar las fotos si vale, pero por esa razon, no por la que yo decia.**

**El texto de los avisos esta AGOTADO.** De 90 candidatos sin dato de cochera, el texto la
menciona en 2. De 75 sin parrilla, en 1. `reglas.py` ya saca todo lo que hay: no queda
mineria de texto por hacer. Lo que falta esta en la ficha (CFT7, expensas) o no lo publica
nadie.

**`cochera` pesa 8 y esta sin dato en el 85%.** En la practica no ordena nada: solo
ensancha el rango de todos por igual. Es una pregunta para la primera llamada, no un
criterio de ranking. Lo mismo `expensas` (80% sin dato) y `parrilla` (71%).

**Performance: no hay nada que arreglar.** DOM listo en 107 ms, 4.294 nodos, 320 lecturas
de `localStorage` en 0,3 ms. Medido, no supuesto. No gastar esfuerzo ahi.

**Bug de orden de pasos:** `build.py` fusionaba el analisis **despues** de `procesar()`,
asi que el score nunca veia `estado_visual` — y el orden por defecto desempata justamente
por ese campo. Se ordenaba por un dato que no habia entrado en la cuenta. Corregido.

**`sobre_avenida` estaba poblado en 1 aviso de 320** y `tranquilidad` (peso 15,
"prioritario" en el perfil) salia de una constante por tipo. Ahora se deduce de la
direccion: **22 avisos sobre avenida, 13 de ellos candidatos**, con −25 en tranquilidad.

**Valores inferidos vs medidos.** `score_desglose.peso_inferido` es nuevo: dice cuantos
puntos de peso son supuesto y no medicion. Hoy son 15 de 100 en casi todo el inventario.
**No cambia la cuenta** — cambiarla reordenaria el ranking entero y esa decision es de
Mario.

## Propuestas abiertas (NO aplicadas, esperan confirmacion)

**1. ~~El presupuesto no es un techo firme hoy.~~ RESUELTO 2026-08-25** (ver sesion 14:
`presupuesto` entro a `filtros_sin_tolerancia` y salieron 29 avisos). Decia: Mario dijo "USD 2.000 es techo firme", pero
`presupuesto` no esta en `filtros_sin_tolerancia`, asi que la seccion "Al limite" lo deja
pasar hasta un 15%: **USD 2.300 aparece igual**. Hoy hay 3 candidatos arriba del tope por
esa via (#51 ravignani 2.200, #191 Uriarte 2.178, #253 11 de Septiembre 2.100).

```diff
 al_limite:
   tolerancia: 0.15
-  filtros_sin_tolerancia: [mascotas, amoblado, uso, zona]
+  filtros_sin_tolerancia: [mascotas, amoblado, uso, zona, presupuesto]
```

**2. Las expensas desconocidas cuentan como cero.** 85 de 106 candidatos no las declaran, y
el filtro duro de USD 2.000 se aplica solo al alquiler. **18 ya estan arriba de USD 1.700**:
con expensas reales de $300-500k se pasan del tope sin que el sistema lo note. No hay
arreglo tecnico —el dato no se publica—, pero conviene decidir si se muestra una marca de
"presupuesto sin verificar" en esos 18.

**3. Valores inferidos en el score.** Ver arriba: hoy 15 de 100 puntos de peso son supuesto
y entran al piso como si fueran medidos.


## Sesion 7 — segundo portal (2026-08-14)

**Se sondearon cuatro portales, un pedido cada uno, leyendo robots.txt primero.** Los
cuatro permiten la busqueda para `User-agent: *`; los `Disallow: /` que aparecen en sus
robots son de bloques para OTROS bots (Semrush, Ahrefs). Mi primera lectura fue burda
—agarre todos los Disallow sin mirar a que agente correspondian— y casi reporto que
MercadoLibre y Remax lo prohibian. **No lo prohiben.**

| Portal | Veredicto |
|---|---|
| **Argenprop** | **Se implemento.** 20 avisos/pagina, HTML plano, datos duros como atributos del `<a class="card">` |
| MercadoLibre | Medido: casas+alquiler+Saavedra = **11 resultados**. No justifica el parser |
| Remax | SPA contra API propia, y su stock ya se publica en Zonaprop |
| Properati | **Mismo grupo que Zonaprop** -> inventario duplicado |

**La deduplicacion entre portales funciono sin tocar nada.** La clave `(calle, altura,
m2/10)` no mira el portal: de 20 avisos de Argenprop en Saavedra, **10 eran los mismos
inmuebles que ya estaban por Zonaprop** y se fusionaron solos (entre ellos #4 Garcia del
Rio, #6 Vedia y #10 Paroissien). Esa clave se diseño en la sesion 4 por otro motivo y
resulto ser exactamente lo que hacia falta.

**Argenprop suma inventario real: 50% de solapamiento, 50% nuevo.** De los 10 propios,
**3 son candidatos que Zonaprop no tenia**: Pinto 4800 (130 m2, USD 1.188), Donado 3600
(70 m2, USD 1.056) y Quintana 4800 (160 m2, USD 2.100, al limite).

**Argenprop empezo a devolver 202 con cuerpo vacio.** Es mitigacion de bots. Causa: arme
mal la URL de busqueda —la saque de un atributo `data-change-view` del HTML en vez de la
que usa el sitio para navegar— y el barrido pidio los 9 barrios con una URL que devuelve
200 y cero tarjetas. **Nueve pedidos inutiles.** Sumados a los del sondeo, alcanzaron.
NO se reintento, NO se cambio el user-agent, NO se rotó nada.

**Defensa nueva, el CANARIO:** `argenprop.buscar()` prueba UNA url antes de barrer, y si
no trae tarjetas aborta todo. **Una URL equivocada cuesta pedidos igual que una correcta.**
Es la misma leccion del 403 de la sesion 4 con otra cara: el rate limit no te protege de
tu propio bug.

**Pendiente de verificar:** el formato de paginado de Argenprop. Saavedra entero son 20
avisos (una sola pagina), asi que el HTML guardado no trae links de paginado para copiar.
`paginas: 1` en el config hasta confirmarlo.

**Fotos: 6 -> 3 por aviso** (decision de Mario). Pero **no las 3 primeras**:
`detalle.repartir()` toma primera, del medio y ultima. El anunciante ordena las fotos para
vender y las utiles estaban al final: la que delataba que Superi 4300 hoy es una oficina
era la 6 de 6, y la que confirmaba el reciclado de Paroissien 4400 era la 5.


## Sesion 8 — tres pantallas y lenguaje visual (2026-08-15)

**Comparar borrada.** Mario: *"no sirve y no quiero q este nunca la voy a usar"*. Se fue
entera: vista, `estado.seleccion`, la tabla y su CSS.

**El modelo pasa a ser el que Mario ya usaba:** corazon rojo -> **Favoritos** (pantalla de
arranque, cards completas) · sin corazon -> **Explorar** · descartado -> **Descartados**.
Candidato y al limite siguen ordenando Explorar y siguen en la etiqueta de cada card, pero
dejaron de ser una pantalla que hay que entender.

**BUG: la pagina mostraba 3 fotos teniendo 8.** `fotosDe()` devolvia las LOCALES apenas
hubiera una, y las locales son 3 por decision de Mario. Las remotas no cuestan nada (las
sirve el CDN del portal) y son **8 de mediana, hasta 50**. Ahora devuelve el set mas
grande. Las locales existen por otro motivo: son las unicas que Claude puede abrir para
clasificar.

**BUG: las fotos de Argenprop rompian las de Zonaprop.** Su CDN rechaza el pedido
cross-origin (`ERR_BLOCKED_BY_ORB`) en cualquier tamano, y al fusionar un duplicado esas
URL inservibles **pisaban las de Zonaprop, que si funcionan**. Van a `fotos_portal`: sirven
para bajar con `detalle.py`, no para mostrar. **Leccion: comprobar en el navegador que una
imagen carga, no que la URL existe.**

**La inmobiliaria estaba en el 100% de los avisos y no se mostraba en ningun lado.** Ahora
va al pie de cada card (con chip de *dueño directo* cuando corresponde) y en el panel, con
boton a su cartera completa y el conteo de cuantas otras publica dentro de la busqueda.

**Rediseño visual:** se fueron los emoji (cada sistema los dibuja distinto) y entro un juego
de iconos de trazo donde **el color lo pone el estado del dato**, no el icono. Tooltips
propios en vez de `title`. El sello ahora lleva numero + cuenta de fotos. El link al aviso
pasa a azul solido: era el unico pedido explicito de Mario sobre visibilidad.


## Sesion 9 — departamentos y perfil nuevo (2026-08-15)

**Perfil corregido por Mario:** *"es importante que sean no amoblados... veo mucho casa y
ph y poco depto... mismas especificaciones pero con terrazas amplias con parrilla,
idealmente edificios nuevos sin portero, expensas hasta 200 con cochera opcional"*.

| | antes | ahora |
|---|---|---|
| expensas | solo puntuaban | **duro: USD 200 max** (solo filtra al que las declara) |
| cochera | peso 8 | peso 4 — "opcional" |
| parrilla | peso 3 | **peso 8** |
| m2 cubiertos | peso 10 | peso 6 |
| departamento | prioridad 0.4 | prioridad 1.0 |
| edificio nuevo | no existia | peso 3 |
| sin portero | no existia | peso 2 |

Los pesos suman **100 exactos**: estado 20->18 y tranquilidad 15->14 para compensar. Eso
reordena el ranking; si no va, se revierte cambiando cuatro numeros.

**POR QUE NO HABIA DEPARTAMENTOS: nunca se pidieron.** `busqueda.tipos_slug` era `[casa]`.
No era un problema de ranking ni de filtros: el barrido literalmente no los bajaba.

**Bug de un plural que anulo 856 avisos.** El portal escribe `"Departamentos"` en plural y
el mapa `TIPOS` del parser solo tenia el singular. Resultado: `tipo = None`, ninguno paso
el filtro de tipo, y la busqueda devolvio cero **sin un solo error**. Un plural que no
matchea no se queja: desaparece.

**El canario fallo, y la leccion es la importante.** Se probo la URL con tag
`departamentos-alquiler-con-terraza-<barrio>`: devolvio 200, 30 avisos y **1501 paginas**.
El canario dijo "hay avisos, adelante" y el barrido bajo 810 departamentos de **Montevideo,
Pocitos, Punta Carretas y Mar del Plata**. **Un canario que solo pregunta "vinieron filas"
es inutil cuando la falla es "vinieron las filas equivocadas":** ahora verifica que el
barrio devuelto sea el pedido. Se borro lo bajado y se uso la URL sin tag, que si respeta
el barrio.

**"Un balcon no alcanza" estaba en el perfil desde el dia uno y no estaba codificado.** La
primera corrida de departamentos dio 16 candidatos con exteriores de 2, 3 y 6 m2. Medido
sobre 826 departamentos: **la mediana de exterior es 2 m2** y el percentil 75 es 4. Se
agrego el duro `departamento_exterior_min_m2: 15`. Quedan **3 departamentos**, y solo uno
—#562 Estomba, Coghlan, 61+27 m2, exp USD 142— cumple de verdad.

**SESGO DE LA MUESTRA, a resolver:** el barrido ordena por precio ascendente y se tomaron 4
paginas de hasta 21 por barrio. O sea que se bajaron **los 120 mas baratos de cada barrio**,
que en departamentos son monoambientes: de 855, solo 43 tienen 2 dorm y 3 ambientes. Lo que
Mario busca esta mas adentro de la lista. Falta una corrida mas profunda.

**106 de 107 candidatos tienen al menos un filtro duro que NO se pudo evaluar** (mascotas
102, amoblado 100, expensas 83). Se muestra un solo chip ambar *"N a preguntar"* con el
detalle en el tooltip: un chip por cada uno seria tapar la card, y **una senal que se
enciende en todos deja de ser una senal**.

## Sesion 10 — el label "caido" mentia, y Explorar mostraba el inventario entero (2026-08-16)

Cuatro cosas reportadas por Mario en la misma corrida. Tres eran bugs.

**"Veo muchas cards con el label de caido."** Lo eran: **304 de 1180 avisos** (26% de la
base) figuraban desaparecidos, 300 de ellos marcados el mismo dia. Se pidieron 8 URLs al
portal: **7 seguian publicadas**. El label mentia en ~87% de los casos.

*La causa:* `reconciliar()` en `main.py` declaraba desaparecido todo lo que no volvia en el
barrido del dia. El comentario del propio codigo prometia una defensa —"solo si su barrio
se barrio hoy"— que **nunca se implemento**; y aun implementada no habria alcanzado, porque
**el corte es por pagina, no por barrio**: el barrido baja `max_paginas_por_barrio`
ordenado por precio ascendente, asi que todo lo que queda debajo del corte desaparece del
listado sin haberse caido. El 15 se sumaron departamentos al barrido y empujaron cientos de
casas y PH fuera del cupo.

*La regla que queda:* **no salir en un barrido no es evidencia de nada.** La unica evidencia
valida de una caida es pedir la URL y que el portal conteste 404/410 o "aviso no
disponible", y eso solo lo hace `detalle.py`, que ahora es **el unico que escribe
`estado_aviso = "desaparecido"`**. `main.py` solo cuenta `ausente_veces`, que sirve para una
cosa: poner primeros en la cola de revalidacion a los que generan duda.

*Nuevo:* `python scripts/detalle.py --solo-vigencia [ids]` — pide la URL y decide si vive,
sin bajar fotos ni reparsear la ficha. Un request por aviso.

*Limpieza:* los 304 se revirtieron a vigente y se revalidaron los 30 candidatos de mas
score. **28 vivos, 2 caidos de verdad: Conde 4700 (#8, era el candidato #1 con 70,4) y
Altolaguirre 1936 (#473).** Quedan ~70 candidatos sin confirmar; las proximas corridas los
toman por prioridad.

**"En Explorar me aparecen cosas absurdamente caras, de 1 amb, 1 hab."** No era un bug de
filtros: Explorar mostraba **todo** el inventario y el chip "Solo los que entran" venia
**apagado por defecto**. De 1176 avisos se veian 1073 que fallan algun duro. **Una
superficie de escaneo que arranca con 91% de ruido no se escanea, se abandona.** Se invirtio
el default: el chip pasa a llamarse *"Ver los que no entran"* y arranca apagado.

**"Los filtros, un desastre, no se ven bien en el layout."** El panel se dibujaba **encima**
de la marca y de los tabs. Causa: **dos reglas `.barra` en el mismo stylesheet** — el header
sticky de la app (linea 127) y las barritas del desglose de score (linea 1010), estas
ultimas escritas como `.barra` a secas. La segunda ganaba por orden y convertia el `<header>`
en un `grid: 124px 1fr 78px`. Se acotaron a `.barras .barra`. **Al nombrar una clase, mirar
si el nombre ya existe: la que se escribe despues gana, y el sintoma aparece en otra parte
de la pagina.**

Ademas el panel era un `flex-wrap` con `align-items: flex-end`, asi que los seis campos
numericos compartian fila con los `<select multiple>` de Barrio y Tipo (tres veces mas
altos) y cada label quedaba a una altura distinta. Pasa a **grilla** de columnas iguales,
con los campos altos al final. Verificado sin superposicion ni desborde a 820, 1100 y 1440 px.

**"Cuando quiero descartar, las opciones no concuerdan; 'no me gusta' no esta."** Agregado
como noveno chip, con categoria propia `no_gusta`. **Sin un motivo que sea "ninguno de los
anteriores", el que no quiere escribir elige el chip que menos le miente** — y eso ensucia
`descartados_por_motivo`, que es de donde sale el patron.

**"Si descarte algo, solo quiero verlo si entro a Descartados."** Ya se filtraba en toda
lista, pero existia el chip *"Ver descartados"* que los devolvia a la grilla. Se saco: para
eso esta su pantalla, y ese chip era la unica via por la que se colaban.

## Sesion 11 — "siempre me salen las mismas busquedas" (2026-08-21)

Lo dijo Mario y era literal, por tres razones apiladas.

**1. Hacia seis dias que no se bajaba nada.** Ultimo barrido de red: el 15. `first_seen`
solo tenia dos fechas (321 el 14, 855 el 15); lo tocado el 16 y el 18 eran rebuilds y sus
descartes. **El primer chequeo ante "no pasa nada" es cuando corrio la red por ultima vez.**

**2. El barrido pedia todos los dias el mismo conjunto, por diseño.** Una sola pasada,
`-orden-precio-ascendente`, las N primeras paginas. Las N paginas mas baratas de un barrio
son las mismas hoy que ayer: **un aviso nuevo no entra arriba, entra en el medio, en el
lugar que le da su precio.** Un 3 ambientes publicado hoy en Palermo a USD 1.400 cae cerca
de la pagina 40 de 107 y no se veia nunca.

**3. La cobertura era del 12%, y del 12% equivocado.** 855 departamentos bajados sobre un
universo de **6.991** en las 9 zonas; Palermo, 4 paginas de 107 (**3,7%**). Y como el orden
era por precio, ese 12% eran los mas baratos: monoambientes. De 855, **43** tenian 2 dorm
y 3 amb.

### Lo que se cambio: dos pasadas en vez de una

| Pasada | URL | Para que |
|---|---|---|
| **Novedades** | `-orden-publicado-descendente`, 2 paginas por barrio y tipo | lo unico que trae algo distinto cada dia |
| **Cobertura** | `-3-ambientes` / `-4-ambientes` / `-mas-de-5-ambientes` + precio ascendente, hasta el final | el universo que importa, entero |

Con el filtro de ambientes Palermo pasa de 3.185 avisos (107 paginas) a **599 (20)**, y
ordenar por precio ascendente ahi ya no trae monoambientes: trae los 3 ambientes mas
baratos, que es exactamente lo que se busca.

**Los filtros del portal se probaron uno por uno, y dos mienten:**

| Slug | Veredicto |
|---|---|
| `-3-ambientes` `-4-ambientes` `-mas-de-5-ambientes` | filtran de verdad |
| `-mas-de-2-ambientes` | **es ">=2"**: los 30 de la primera pagina eran de 2 ambientes |
| `-menos-de-2000-dolares` | **no filtra nada**: Saavedra devolvio 158 de 158 y el primero era de USD 8.000 |

**Un filtro que devuelve 200 no es un filtro que funciono.** Es la misma leccion del canario
con otra cara: hay que mirar los VALORES de lo que volvio.

### Resultado de la corrida

**761 avisos nuevos** (base 1176 -> 1754), candidatos 87 -> **103 vigentes**, y sobre todo:
**32 publicados en los ultimos 14 dias** contra los 12 de antes, con la lista entera
distinta. Lo mejor que aparecio: **#1931 Juramento e/ Pacheco** (Villa Urquiza, PH 5 amb,
280+94 m2, USD 1.716, publicado HOY) y **#1666 Miller 3154** (Villa Urquiza, PH 4 amb, 70+35,
USD 845, **dueño directo**).

### El 403, y por que esta vez no fue un bug

Zonaprop corto en el pedido ~100 de la corrida, con pausa de 2-3 s y sin ninguna URL mal
armada: **fue volumen legitimo**. Los dos 403 anteriores fueron bugs propios; este es el
techo real del portal. De ahi salieron tres numeros del config, todos medidos y no elegidos
a ojo: **presupuesto de 90 pedidos por corrida**, **pausa 3-5 s**, **8 paginas por barrio y
slot**.

Y una defensa nueva: **la cobertura rota el orden de los barrios segun el dia**
(`date.today().toordinal() % n`). El corte del 403 dejo Palermo completo y el resto sin
tocar; con orden fijo, el mismo corte castigaria siempre a los mismos barrios y volveriamos
al problema original por otra puerta.

### La fecha de publicacion estaba en el listado desde el dia uno

`publicado_hace_dias` se creia dato exclusivo de la FICHA, y por eso lo tenia 1 de cada 3
candidatos y la vista "Ultimas 2 semanas" mostraba mas avisos sin fecha que con fecha.
Estaba en el campo **`antiquity`** del listado ("Publicado hace 14 dias"), en el 100% de los
avisos. **Cero pedidos extra.** Hoy la tienen 741 de 1754, y de los candidatos, casi todos.

Tres precisiones que costaron medirlas:

1. **`antiquity` solo viene poblado con `-orden-publicado-descendente`.** En los listados
   por precio es `None`. La fecha la trae la pasada de novedades, que es donde importa.
2. **Se guarda la fecha ABSOLUTA (`publicado_el`), no los dias.** "Hace 2 dias" guardado en
   la base sigue diciendo 2 dias dentro de un mes; `build.py` recalcula los dias en cada
   corrida. Y al reprocesar un HTML viejo se fecha contra **el dia del barrido**, no contra
   hoy.
3. **`modified_date` NO sirve como fecha de publicacion** y se probo: coincide en el 59% de
   205 avisos, 71% con un dia de tolerancia. Un aviso de hace ocho meses reeditado ayer
   apareceria como NUEVO. Se guarda aparte como `modificado_el`, que es lo que realmente es.

### BUG: la antiguedad del edificio salia de los dias de publicacion

`item_a_aviso` usaba `antiquity` como fallback de `antiguedad_anios`, y `_numero()` le sacaba
el numero: **"Publicado hace 35 dias" -> edificio de 35 años**. 10 de cada 148 avisos
afectados; 55 corregidos en la base releyendo los HTML guardados. Alimentaba `edificio_nuevo`
(peso 3) y se mostraba en la ficha. **Un campo mal leido es peor que un campo vacio: nadie lo
vuelve a mirar.**


## Sesion 11b — que corra solo, y que se note cuando no corrio (2026-08-21)

Mario: *"para que se actualice que onda? tengo que correr esto todos los dias y ver?"*

**No. El sistema tiene que correr solo y avisar cuando no corrio.**

| | |
|---|---|
| `abrir.bat` | **el unico que hace falta.** Decide solo: si los datos no son de hoy busca, y despues abre la pagina |
| `actualizar.bat` | forzar una busqueda mas en el mismo dia |
| Tarea `BusquedaAlquiler-Diaria` | Programador de tareas de Windows, **todos los dias 9:00**, sin ventanas. Corre `scripts/corrida_automatica.bat`; salida cruda en `data/logs/ultima-corrida.txt` y el resumen de siempre en `corridas/<fecha>.md`. Se saca con `schtasks /delete /tn BusquedaAlquiler-Diaria /f` |

Tiene `StartWhenAvailable`: si la maquina estaba apagada a las 9, corre cuando arranca.

**Por que `abrir.bat` decide solo.** La primera version dejaba dos archivos parecidos y
Mario tuvo que preguntar dos veces cual abrir. **Cuando alguien pregunta dos veces lo
mismo, el problema no es que no escuche: es que el diseño le esta pidiendo una decision
que no tendria que tomar.** Ahora hay un archivo y hace lo que corresponde; la decision la
toma `scripts/estado.py`, que compara `meta.ultimo_barrido` contra hoy y devuelve un
codigo de salida (2 = buscar, 1 = abrir directo). En un .bat eso no se puede resolver:
`%date%` depende del idioma de Windows.

**La banda de "estos datos estan viejos".** Es la contracara del reclamo que abrio la
sesion: el sistema llevaba seis dias congelado y en la pantalla no habia forma de notarlo,
porque el pie decia *"generado"*, que se actualiza con cualquier rebuild aunque no se haya
tocado la red. Ahora `avisos.json` guarda **`meta.ultimo_barrido`** (solo lo escribe una
corrida que realmente bajo del portal) y la pagina avisa: **1-2 dias** una linea en la
banda, **3 o mas** banda roja entera. **Un sistema congelado que no avisa que esta
congelado se lee como un mercado quieto** — la peor conclusion posible en una busqueda.

**Tope de barridos por dia, ahora que hay dos vias.** La etiqueta con el portal (2 corridas
por dia) se sostenia en que las lanzaba Mario a mano. Con una tarea programada mas una
corrida manual, nadie lleva la cuenta. `meta.barridos_por_dia` la lleva: pasado el tope,
la corrida **saltea la red** (tambien Argenprop) y reprocesa gratis lo que ya bajo.

### BUG: "182 avisos nuevos" todos los dias, con la base clavada en 1.916

Tres corridas seguidas reportaron ~182 altas sin que la base creciera un aviso. Dos cosas
sacan avisos de `avisos.json` despues de que entraron —la **deduplicacion** (fusiona el
duplicado y lo borra) y el **veto por descarte**— pero el HTML los sigue trayendo en cada
barrido, asi que volvian a contarse como novedad para siempre.

Se arreglo con `data/ids_vistos.json`: el registro de todo id que paso por la base alguna
vez. Un alta es un id **nunca visto**, no un id que hoy no esta. Hoy: 2.098 vistos, 1.916
en base, 0 altas en la corrida de reproceso.

**Era el numero mas mentiroso del sistema, y encima el que decide si vale la pena mirar.**
Cuando un contador de novedades no baja nunca a cero, sospechar del contador.

### Detalle chico con moraleja: `%date%` en un .bat

El primer `corrida_automatica.bat` armaba el nombre del log con `%date%` y genero
`21-08-Fri.txt`, y despues `.txt` a secas. El formato de `%date%` depende del idioma y la
config regional de Windows. Se resolvio sacando la fecha del nombre: un solo
`ultima-corrida.txt` que se sobrescribe, porque el historico ya lo escribe la corrida en
`corridas/<fecha>.md`. **Si un dato ya lo tiene quien sabe hacerlo bien, no lo recalcules
en el eslabon mas tonto de la cadena.**

## Sesion 12 — MercadoLibre, y dos contadores que mentian (2026-08-23)

Mario pregunto si se estaba tomando de MercadoLibre. No: estaba `activo: false` desde el
sondeo de la sesion 7. **La medicion que lo dejo afuera era el peor caso posible**:
`casas + alquiler + Saavedra = 11 resultados` — el barrio mas chico del perfil, el tipo
que ML casi no publica, y medido ANTES de que los departamentos entraran (sesion 9).

Medido de nuevo sobre departamentos y el corredor norte: **1.109 avisos**
(Villa Urquiza 414 · Nunez 370 · Colegiales 165 · Saavedra 97 · Coghlan 63).

**Zonas propias del portal.** Mario: *"no pondria Palermo, ni Almagro, seria mas de
Colegiales hasta Saavedra aprox"*. Viven en `portales.mercadolibre_zonas` y son 7; el
resto de la busqueda no cambia. Van en una clave aparte y **en un solo renglon** porque
el parser de YAML del proyecto es por linea y adentro de `{...}` no entra una lista.

### robots.txt manda sobre el diseno del barrido

Leido entero, bloque `User-agent: *`. **Prohibe paginar (`_Desde_`), ordenar
(`_OrderId_`) y filtrar por precio (`_PriceRange_`)**, ademas de las facetas de atributo
(`_Cocheras_`, `_Banos_`, `_HAS*GRILL_`). O sea: de cada busqueda se ve UNA pagina de 48,
en el orden que elige el portal.

Por eso el barrido **no pide paginas: pide consultas mas angostas**. Y el segmento de
ruta `/mas-de-3-ambientes/` si esta permitido, baja Villa Urquiza de 414 a 88, y **se
verifico mirando los valores** (vuelven 3, 4 y 5 ambientes = es ">= 3", justo
`ambientes_min`). Casas (13) y PH (26) entran enteros en una pagina: ahi la cobertura es
total. Solo 3 de 21 busquedas tocan el techo de 48.

**Limitacion que queda:** en departamentos ML muestra casi siempre los mismos 48 por
barrio y no hay forma permitida de pedir el resto. Se dice en la salida de cada barrio
(`de 88; el resto no es alcanzable sin paginar`) en vez de recortar en silencio.

### De donde sale cada dato

Dos fuentes en la misma pagina, unidas **por el id MLA y no por posicion** (el `ld+json`
trae 50 items y el HTML 48 tarjetas: cruzarlos por indice desalinea todo).

- **`datePosted` del `ld+json` esta en el 100% de los avisos.** Es la mejor fecha de
  publicacion de los tres portales: en Zonaprop hay que derivarla de "hace N dias" y solo
  viene en la pasada de novedades.
- **`numberOfRooms` son DORMITORIOS, no ambientes.** Medido sobre 170: da `ambientes - 1`
  en el 84% y el resto son monoambientes. Es el unico lugar de donde sale el dormitorio,
  que es filtro duro.
- **`m2 totales` aparece en 6 de 240 (2,5%).** O sea que el exterior —el criterio que mas
  pesa (25) y el duro `departamento_exterior_min_m2`— queda sin dato en casi todos. No se
  inventa: entran sin el campo y score.py los marca "a preguntar".
- **El 100% de las tarjetas trae calle y altura**, pero el 72% redondeada a la cuadra
  ("Al 5200"). No rompe la deduplicacion porque Zonaprop redondea igual.

**Las fotos de ML SI cargan cross-origin**, a diferencia de las de Argenprop. Verificado
en el navegador desde el mismo origen `file://` que usa la pagina, con URLs reales de la
base: Zonaprop CARGA, MercadoLibre CARGA, Argenprop FALLA (`ERR_BLOCKED_BY_ORB`). Por eso
van a `fotos_remotas` y no a `fotos_portal`.

### Resultado

**381 avisos en 21 pedidos.** De esos, 89 quedaron como aviso propio y **268 se fusionaron
solos con Zonaprop** — la clave `(calle, altura, m2/10)` no mira el portal, igual que paso
con Argenprop. La lista corta paso de 145 a **199**, y de los 79 que entraron hoy,
**53 son de MercadoLibre**.

### BUG: `av. Cabildo 2200` normalizaba a `'av'` (preexistente, no era de ML)

`normalizar_direccion` cortaba en el primer punto para sacar la anotacion, y se comia la
abreviatura: **`Av. Cabildo 2200` -> `'av'`**, `Dr. Ricardo Balbin 3200` -> `'dr'`. En la
base habia 28 avisos con clave `'av'`, 10 con `'dr'`, 5 con `'avda'`.

Las dos consecuencias son de las peores que puede tener este sistema: **la deduplicacion
fusionaba propiedades que no tienen nada que ver**, y **el veto por descarte se propagaba
a todas** — habia un descarte de "Av. Cramer 4400" con clave `'av'`, vetando cualquier
avenida que entrara despues. En la corrida siguiente al arreglo los vetados cayeron de
238 a 75. Se protegen las abreviaturas de nomenclatura antes de cortar; radio medido
antes de tocar: 37 avisos y 2 descartes.

### BUG: `altas` daba SIEMPRE cero — el mismo contador, roto al reves

El arreglo de la sesion 11b agrego el parametro `vistos` (ids historicos) a
`reconciliar()`, pero el desempaquetado de la linea siguiente **lo pisaba con un `set()`
vacio** y reusaba el nombre para "los ids de hoy". Como el id se agregaba tres lineas
antes de preguntar si estaba, la condicion daba siempre False.

La corrida de hoy entro 89 avisos de MercadoLibre e informo **"0 avisos nuevos. Hoy no hay
nada."** Son dos conjuntos distintos y ahora se llaman distinto: `historicos` decide que es
un alta, `presentes` decide quien esta ausente.

**Este contador ya mintio dos veces en tres dias, en las dos direcciones** (182 altas todos
los dias el 21, cero altas el 23). Es el numero que decide si vale la pena mirar la pagina:
cuando cambie algo cerca, probarlo con casos, no de vista. Quedaron cinco.

### Contador de barridos POR SITIO

El tope diario contaba barridos de Zonaprop —nacio de sus dos 403— y colgar ML del mismo
contador significaba que, con Zonaprop agotado, ML no se pedia ni una vez en todo el dia
aunque no se lo hubiera tocado. La etiqueta es por sitio: `meta.barridos_ml_por_dia`
lleva su cuenta aparte y respeta el mismo maximo.

## Sesion 13 — GBA Zona Norte (2026-08-24)

Mario: *"tambien podes agregar a esto casas en nuñez, zona norte, olivos, etc"*, y despues
*"dije casas pero tambien pueden ser deptos con las cosas que ya sabes que busco"*.

**Nunez ya estaba, y sus casas tambien**: tiene 21 casas sobre 335 avisos. No faltaba por
un bug del barrido — CABA casi no tiene casas (160 en toda la base contra 2.846
departamentos). Eso es justamente el argumento para cruzar la General Paz.

### Lo que de verdad importa de este cambio: la garantia

`conocimiento/garantia.md` dice que la propietaria de CABA es *"la que piden por defecto"*
y que **su ausencia es el filtro real de este proyecto**. Mario tiene propietaria en
**GBA**. En Zona Norte esa garantia deja de ser el problema y pasa a ser la que
corresponde. Vale mas que el inventario que se sumo.

### DOS LISTAS DE ZONAS, donde antes habia una

`zonas.incluidas` hacia dos trabajos: lo que se PIDE al portal y lo que se ACEPTA en el
duro `zona`. En CABA coinciden. **En GBA no**: se pide el PARTIDO `san-isidro` y vuelven
Martinez, Beccar, Acassuso y La Horqueta.

    zonas.incluidas   lo que se acepta   (score.py)          22 nombres
    zonas.barrido     lo que se pide     (fetch/ap/ml)       10 nombres

Medido: `vicente-lopez` devuelve 229 casas de Olivos/Florida/Munro/La Lucila y
`san-isidro` 334 de Martinez/San Isidro/Beccar/La Horqueta. **Dos pedidos cubren lo que
con localidades sueltas costaria ocho.** Y `la-lucila` suelto devuelve CERO: no va como
slug (igual entra por su partido). Una URL que no trae nada cuesta un pedido igual.

### Lo que hubo que tocar, y por que

- **`lib_config.zonas_a_barrer()` y `es_gba()`**: una sola fuente para las dos preguntas.
- **MercadoLibre tiene DOS geografias**: `capital-federal/<barrio>` y
  `bsas-gba-norte/<partido>`. Se usa la forma canonica que linkea el propio portal y no
  el atajo `/casas/alquiler/olivos/` —que tambien anda— porque con nombres ambiguos
  ("Florida", "San Isidro" es partido Y localidad) no hay forma de saber que resolvio.
- **La localidad real se conserva.** Al pedir el partido, ML dejaba los 84 avisos con
  barrio "Vicente Lopez" y se perdia que 23 son de Olivos y 4 de Munro. Ahora la localidad
  de la tarjeta pisa al partido, pero SOLO si tambien es de GBA Norte: hay anunciantes que
  escriben "Parrilla Y Playroom" en ese campo.

### BUG que introduje y costo una corrida: el canario contra los partidos

`fetch._barrio_coincide()` exige que el barrio devuelto sea IGUAL al pedido. Con un partido
eso no se cumple nunca, asi que dio por muerta la URL de casas de Vicente Lopez —una que
yo mismo habia verificado a mano— y **abandono la cobertura entera de casas en GBA**.

Y era peor de lo que parecia: `muertas` guarda la forma `(tipo, filtro, orden)` para TODA
la corrida, no por barrio. O sea que una zona de GBA podia matar la URL de casas **tambien
para los barrios de CABA** de la misma corrida. Se arreglo relajando el canario solo en
GBA: sigue comprobando que la geografia sea la pedida, pero ahi "la pedida" es el partido.
Probado con cuatro casos (CABA ok, GBA ok, CABA con Pocitos falla, GBA con Pocitos falla).

### Argenprop: la mitigacion de bots tiene dos caras

Devolvio **200 con una pagina de desafio de 2.610 bytes** —title vacio, estilos inline,
cero tarjetas—, no el 202 con cuerpo vacio que ya conociamos. El mensaje decia "la URL no
trae tarjetas" y mandaba a revisar una URL que estaba bien: costo un pedido darse cuenta.
Ahora un cuerpo de menos de 20 KB se reporta como mitigacion, no como URL mala. **No se
reintenta ni se cambia el user-agent**, es la regla del proyecto desde la sesion 7. Se
recupero solo en la corrida siguiente.

### `--solo-zonas`, y por que no es un rodeo del tope

El tope de 2 barridos por dia existe para no pedir LO MISMO muchas veces (dos 403 de
Zonaprop lo pusieron ahi). Cuando se suma una zona al config, esa geografia no se pidio
nunca y esperar al dia siguiente no protege a nadie. `python scripts/main.py
--solo-zonas="Vicente Lopez,San Isidro"` barre solo lo que se nombra, es manual, y suma
al contador igual.

### La lista de zonas de MercadoLibre es INDEPENDIENTE, y se olvido

`portales.mercadolibre_zonas` existe aparte a proposito (Mario no quiere Palermo ni
Almagro en ese portal), pero eso la hace facil de olvidar: al sumar Vicente Lopez y San
Isidro a `zonas.barrido`, ML quedo sin ellos. **Los 288 avisos de GBA que trajo ML el
2026-08-24 entraron solo porque se los forzo con `--solo-zonas`; una corrida normal no
los habria pedido nunca.** Corregido, y `max_requests` subio de 21 a 27 porque son 9
zonas x 3 rutas. Al tocar `zonas.barrido`, mirar tambien esta.

### Cuanto cubre UNA corrida (medido, no supuesto)

    novedades   20 tareas / 40 paginas   ENTRAN SIEMPRE, las 10 zonas, todos los dias
    cobertura   60 tareas                entran ~16 por corrida (50 pedidos / ~3 paginas)

O sea: **lo nuevo se ve todos los dias en todas las zonas**; la cobertura profunda rota.
Simulado sobre 14 dias con el giro por `toordinal()`: cada zona recibe cobertura completa
entre 6 y 10 dias de 14, y **el peor caso de espera es 4 dias** (Belgrano). Antes de GBA
eran 8 zonas y 48 tareas; ahora 10 y 60.

### Resultado, y el efecto secundario que hay que mirar

**877 avisos nuevos.** La lista corta paso de 153 a **456**: 188 de CABA y 268 de GBA
Norte (122 casas, 103 PH, 43 deptos), mediana USD 1.135, y **60% con dato de exterior**
—contra el 2,5% de ML en CABA— porque las casas de Zonaprop si publican m2 totales.

**GBA se lleva el top 15 entero.** No esta mal: el score premia el exterior (peso 25) y
`casa_lote_propio` puntua 100 en tranquilidad, asi que una casa con jardin le gana
estructuralmente a un departamento. Es lo que el perfil pide. Pero **deja los
departamentos de CABA fuera de la primera pantalla**, y eso se arregla en la VISTA, no en
el score: tocar los pesos para "equilibrar" seria falsear lo que Mario dijo que le importa.
Entraron dos chips excluyentes, **Solo CABA** y **Solo Zona Norte**. Verificado en el
navegador: con Solo CABA quedan 0 avisos de GBA.

## Sesion 14 — el corredor termina en Martinez (2026-08-25)

Mario, al ver la lista corta despues de GBA: *"saca de las posibilidades accasuso villa
adelina florida, etc, te dije nuñez, martinez, saavedra, hasta ahi ya tan para el oeste
no... casas q superan los 2k us no entran tampoco"*.

### Abrir por PARTIDO trajo doce localidades que nadie pidio

La sesion 13 pidio `vicente-lopez` y `san-isidro` enteros —decision correcta: dos pedidos
donde harian falta ocho— y **puso las doce localidades que vuelven en `zonas.incluidas`
sin preguntar**. Eso no era leer el perfil, era aceptar lo que devolvia la URL.

De los tres nombres que Mario dio para sacar, ninguno se explica por el mismo eje:
Florida y Villa Adelina son tierra adentro, pero **Acassuso esta sobre el rio**, mejor
ubicado que media Martinez. El criterio que explica los tres a la vez es el otro:
**la distancia, y Martinez es el limite.** Lo que esta mas lejos sale aunque sea
ribereno; lo que esta al oeste sale aunque este cerca.

**Tres pasadas en el mismo dia**, cada una mirando la lista que dejo la anterior:

| | dijo | incluidas |
|---|---|---|
| 1 | *"saca accasuso villa adelina florida, etc... hasta ahi ya tan para el oeste no"* | 22 -> 12 |
| 2 | *"saca tambien olivos y la lucila, san isidro ni hablar, ya es muy lejos, hasta martinez veria"* | 12 -> 9 |
| 3 | *"martinez es lejos, vicente lopes y hasta nuñez llegamos"* | 9 -> 9 (sale Martinez, entra Vicente Lopez) |

**Lo importante es que las tres son la MISMA frontera moviendose hacia CABA**, aunque en
la pasada 2 el motivo que dio no cerrara (Olivos y La Lucila estan mas CERCA que Martinez,
asi que "es muy lejos" no las explicaba). Recien la pasada 3 dejo la lista coherente:

    Nuñez | General Paz | VICENTE LOPEZ | Olivos | La Lucila | Martinez | Acassuso | San Isidro
                          ^^^^^^^^^^^^^ el limite

**De GBA queda un solo escalon: el primero despues de la General Paz.**

**La leccion no es sobre zonas, es sobre de donde salio la lista de ayer.** Ninguna de las
12 localidades que se recortaron hoy la pidio Mario: entraron solas el 2026-08-24 al abrir
los partidos `vicente-lopez` y `san-isidro` enteros y volcar TODO lo que devolvian en
`zonas.incluidas`. Eso no fue leer el perfil, fue aceptar lo que contestaba la URL. **Lo
que se pide y lo que se acepta son dos preguntas distintas — para eso hay dos listas — y
la segunda no se contesta mirando la respuesta de la primera.**

**"Vicente Lopez" es PARTIDO y es LOCALIDAD, y aparece con los dos sentidos en el mismo
config**: en `barrido` es el partido (la unica via de pedirlo) y en `incluidas` es la
localidad (lo unico que se quiere). Las otras seis del partido —Olivos, Florida, Munro,
La Lucila, Villa Martelli, Carapachay— se bajan y se descartan.

**`barrido` se justifica por lo que ACEPTA, no por lo que trae**, y esa regla se estreno
hoy dandose vuelta dos veces en una tarde: a la manana `san-isidro` valia (era la unica
fuente de Martinez) y `vicente-lopez` no rendia nada; despues de la pasada 3 es exacto al
reves. Un partido cuya cosecha util es CERO no es barato: es gastar pedidos todos los dias
para tirar el 100%. `vicente-lopez` es hoy el unico pedido de GBA que queda, en `barrido`
y en `mercadolibre_zonas` (ML: 27 -> 24 pedidos).

*Y rinde poco:* de lo que devuelve el partido, solo 144 avisos son de la localidad Vicente
Lopez y 17 llegan a la lista corta. Con 8 paginas por pedido, **~6 de cada 7 avisos que
bajamos de ahi son de localidades que ya no queremos**, asi que la cobertura real de
Vicente Lopez es una fraccion de esas 8 paginas. Vale medir si el portal acepta un slug
para la localidad sola; el canario ya cubre el riesgo (una URL invalida cae a la busqueda
sin barrio, que devuelve avisos no-GBA y la mata).

`lib_config.GBA_NORTE` **no se toco a proposito**: no es "lo que aceptamos" sino "esto es
GBA Norte", y de eso depende que la localidad de la tarjeta pise al partido. Si sacara
`martinez` de ahi, los avisos de Martinez volverian etiquetados "San Isidro" y fallarian
el duro que acaban de pasar.

### El techo de USD 2.000 por fin es techo

Estaba anotado como **propuesta abierta #1** desde la sesion 6 y hoy Mario lo confirmo.
`presupuesto` no estaba en `filtros_sin_tolerancia`, asi que la seccion "Al limite" le
aplicaba el 15%: **29 de los 70 al_limite estaban ahi solo por precio**, hasta USD 2.288.

```diff
-  filtros_sin_tolerancia: [mascotas, amoblado, uso, zona]
+  filtros_sin_tolerancia: [mascotas, amoblado, uso, zona, presupuesto]
```

Los otros duros numericos (m2, dormitorios, ambientes) siguen con tolerancia: ahi un 10%
de menos es discutible y se mira. En el precio no — un alquiler que no se puede pagar no
es un caso al limite, es un no.

**Lista corta 460 -> 283 -> 212 -> 192**, `al_limite` 70 -> 29.

### "No veo nada de Saavedra, ni Belgrano R" — habia, y la respuesta tiene dos mitades

Mario lo pregunto con la lista de 283 delante. Medido antes de contestar:

**Mitad uno, la vista.** Habia 173 avisos de CABA y 99 casas/PH, pero **el primero de CABA
caia en el puesto 12 y el primero de Saavedra en el 23.** No es un bug del score: el
exterior pesa 25 y `casa_lote_propio` puntua 100 en tranquilidad, asi que una casa de
Martinez con 334 m2 de jardin le gana estructuralmente a un PH de Saavedra con 30. Es lo
que el perfil pide. Pero **283 avisos en una lista plana hacen que una geografia se coma
la primera pantalla, y desde ahi "no hay" y "esta en la pantalla 4" se ven igual.** Al
sacar Olivos y La Lucila la lista quedo en 212 y CABA arranca en el puesto 8.

**Mitad dos, el mercado, y esta no se arregla con la vista.** En Belgrano R y Nuñez las
casas existen y estan arriba del techo:

| barrio | casas/PH que fallan SOLO por precio | la mas barata | mediana |
|---|---|---|---|
| Saavedra | 7 | USD 2.100 | 2.500 |
| Villa Urquiza | 8 | USD 2.092 | 2.807 |
| Colegiales | 8 | USD 2.092 | 2.800 |
| Nuñez | 11 | USD 2.198 | 3.200 |
| **Belgrano R** | **13** | **USD 2.800** | **3.922** |
| Belgrano | 28 | USD 2.500 | 6.000 |

O sea: **en Belgrano R no hay UNA sola casa que cumpla el perfil abajo de USD 2.000**, y
la mas barata que cumple todo lo demas esta 40% arriba. En Saavedra el techo esta a un 5%,
que es la unica zona de CABA donde la conversacion de precio tiene sentido. Y **Coghlan
tiene 2 casas/PH en 97 avisos**: es un barrio de departamentos, no va a aparecer nunca
por mas que se lo busque.

### BUG: 43 avisos con metros de exterior NEGATIVOS

`reglas.py` derivaba `m2_descubiertos = m2_totales - m2_cubiertos` **sin piso**, y hay
avisos donde el portal se contradice: `Av. San Martin 577` declara **7 m2 totales sobre 52
cubiertos** (-45), `Avenida Triunvirato al 4200` da -143. 43 en base, 2 en la lista corta.

Se deja en **`None`, no en 0** — y la diferencia importa. `argenprop.py:192` y
`mercadolibre.py:263` hacen `max(0.0, ...)` sobre lo mismo, que convierte un dato roto en
la afirmacion confiada *"no tiene exterior"*, sobre el criterio de MAYOR peso (25). Si el
aviso resulta tener el jardin mas grande de la lista, un 0 lo hunde y nadie lo vuelve a
mirar. `None` dice "no lo sabemos", score.py lo marca **"a preguntar"** y el techo del
rango queda abierto. Es la misma distincion que `estado: null` vs `sin_clasificar`, ahora
en los metros. La pasada de reglas corre despues y sobre todos los portales, asi que este
valor es el que queda.

### avisos.json miente en `seccion` entre corridas completas

Costo una lectura equivocada: despues de `main.py --sin-red` mire `data/avisos.json` y
segui viendo 404 candidatos con Florida y San Isidro adentro. **`score.procesar()` solo
corre en `main.py` cuando hay red**; sin red lo unico que puntua es `build.py`, y build
escribe el resultado en `web/data.js` — a `avisos.json` solo le vuelve a escribir los
numeros `#N`, antes de puntuar.

O sea que **el campo `seccion` de `avisos.json` es de la ultima corrida CON red**, no del
config de hoy. La pagina esta bien porque lee `data.js`. Al verificar un cambio de config,
mirar `data.js` o correr `score.py`, nunca el `seccion` de `avisos.json`.

### Caido: #1666 Miller 3154, dueno directo

PH 4 ambientes en Villa Urquiza, 70+35 m2, USD 837, **dueno directo**. Era uno de los dos
mejores hallazgos de la sesion 11. Confirmado desaparecido hoy 09:13. Cayeron tambien
#3426 Manzanares al 2000 (Nunez) y #3425 Dr. Emir Mercader 4550 (Villa Urquiza).

## Sesion 15 — "no veo nada de mercado libre" (2026-08-26)

**Habia 69 de 202 en la lista corta — un tercio — y la pagina no lo decia en ningun lado.**
El campo `portal` esta en el 100% de los avisos desde la sesion 7 y vivia UNICAMENTE en el
`title` del link de la foto, que es el tooltip lento del sistema operativo que este proyecto
ya habia decidido no usar. **Un dato que existe y no se ve es un dato que no existe**, y el
sintoma es el que ya paso con el badge del score: no se arregla explicandolo en el chat.

Tres lugares, porque el dato hace falta en tres momentos distintos:

| donde | que dice | para que |
|---|---|---|
| pie de cada **card** | chip mono con el nombre completo | de donde salio ESTA propiedad |
| pie de cada **tile** de Explorar | mismo nombre, compartiendo fila con la direccion | escanear decenas sin abrir nada |
| **pie de la pagina** | `en la lista corta: 117 Zonaprop · 69 MercadoLibre · 16 Argenprop` | si un portal dejo de aportar |

**El conteo del pie va sobre la LISTA CORTA, no sobre el total.** Zonaprop gana el total
siempre por volumen (4.384 de 4.801) y ese numero no informa nada; lo que se quiere saber
es cuanto aporta cada uno a lo que se mira.

**El primer intento lo puso solo en la card, y ese era el agujero peor.** Ninguno de los
avisos de ML es favorito, asi que la pantalla de arranque los muestra en cero: **el portal
secundario vive en Explorar**, que es exactamente la superficie que quedaba sin etiquetar.
Al sumar un dato a la interfaz, la pregunta es en cual de las tres pantallas hace falta —
casi nunca es la primera.

**Los colores del tile son mas claros que los de la card a proposito.** El ambar de la
card (`--ambar`, #9a6c05) sobre el degradado oscuro del tile no se lee. Mismo dato, mismo
lenguaje, dos fondos.

### Ademas ML nunca estuvo parado: la mitad de lo que trae se fusiona y desaparece de vista

368 avisos propios en base **y 363 mas absorbidos por la deduplicacion**: la clave
`(calle, altura, m2/10)` no mira el portal, asi que cuando ML publica un inmueble que ya
estaba por Zonaprop, la card que queda dice Zonaprop. Es el diseño correcto —una card por
propiedad— pero **la mitad del aporte de un portal secundario es invisible por definicion**,
y esa es la otra razon por la que la pregunta tenia sentido.

### `web/data.js` pesa 38 MB, y 30 de esos son avisos que nadie lista

La pagina embebe los 4.801 avisos con descripcion, fotos y desglose completo. Lo que
realmente se lista por defecto son **222 (1,3 MB)**; el resto son `filtrados`, que solo se
ven con el chip "Ver los que no entran". Lo mas pesado: `score_desglose` 7,6 MB,
`descripcion` 6,2, `fotos_remotas` 3,0, `duros` 2,5.

**La medicion de la sesion 6 -"performance: no hay nada que arreglar", DOM listo en 107 ms-
sigue siendo cierta y ya no aplica: era sobre 320 avisos y hoy son 4.801, quince veces
mas.** No esta reportado como problema por Mario todavia. Anotado, no tocado: recortar
`score_desglose` y `descripcion` de los `filtrados` es el corte obvio si algun dia molesta.

### Se cayo el favorito #203 y el aviso quedo "PROPIEDAD RESERVADA"

Colegiales, Jorge Newbery 3273, PH 2 dorm 76+48 m2, USD 1.079. **Se publico el 25 y estaba
reservado el 26**: el slug de la URL cambio a `--propiedad-reservada--`. Es el primer dato
duro de velocidad de mercado del proyecto — un PH bien puesto en Colegiales abajo de USD
1.100 dura **un dia**. Quedan 4 favoritos vigentes.

## Sesion 16 — la cobertura de departamentos no corrio NUNCA (2026-08-31)

Mario: *"por alguna razon no esta barriendo mas, cuando corro el actualizar me salen
carteles q no se puso paginar"*. Las dos mitades del reporte eran ciertas y **no eran la
misma cosa**: los carteles no eran el bug, y el bug no producia carteles.

### El bug: la rotacion giraba en la dimension equivocada

El plan son 72 tareas y el presupuesto alcanza para ~48. La rotacion diaria existe
justamente para eso (desde el 403 del 2026-08-21) — pero **solo giraba los BARRIOS**,
con `for tipo:` y `for slot:` fijos por fuera. O sea que reordenaba DENTRO de cada bloque
de 9 y nunca cambiaba que bloque iba primero:

    #0  casa/novedades      #18 casa/3-amb    #36 casa/mas-de-5
    #9  deptos/novedades    #27 casa/4-amb    #45 DEPTOS/3-amb   <- recien aca
                                              #54 DEPTOS/4-amb   <- jamas
                                              #63 DEPTOS/mas-5   <- jamas

**La cobertura de departamentos empezaba en la tarea #45 de 72, y la corrida muere cerca
de la 48.** Verificado en `data/raw`: 24 archivos de cobertura de deptos el 29 (la unica
corrida que gasto los 90 pedidos) y **CERO el 27, 28, 30 y 31**. Las de 4 y de mas-de-5
ambientes no se bajaron ni un solo dia desde que existen.

Y el costo es exactamente al reves de lo que conviene: **en CABA hay 2.934 departamentos
y 158 casas**. La pasada cuyo proposito es llegar al fondo del inventario gastaba el
presupuesto entero en el tipo que casi no existe.

**El arreglo son tres lineas en `plan_de_barrido`, ninguna toca el presupuesto:**

1. `tipo` pasa a ser el bucle **mas interno** — casa y departamentos quedan pegados, y un
   corte los parte por la mitad a los dos en vez de decapitar a uno.
2. los **slots tambien giran** por dia: sin eso `mas-de-5-ambientes` es el ultimo siempre,
   que es el mismo problema una dimension mas adentro.
3. los barrios siguen girando como antes.

Simulado a 14 dias con el costo real medido de `data/raw`, tareas de cobertura pedidas
(maximo 126 por forma):

| forma | antes | despues |
|---|---|---|
| casa 3-amb / 4-amb / mas-de-5 | 126 · 126 · 126 | 67 · 57 · 75 |
| deptos 3-amb | 70 | 63 |
| **deptos 4-amb** | **0** | **56** |
| **deptos mas-de-5** | **0** | **73** |

Corrida real del 2026-08-31: **37 archivos de cobertura de departamentos** donde antes
habia 0, y 172 avisos nuevos.

**LA LECCION, que es mas general que este bug: una rotacion solo protege la dimension
sobre la que gira.** El comentario del codigo decia "rota para que un corte no castigue
siempre a los mismos" y era verdad de los barrios y falso de todo lo demas. Cuando algo
se corta por presupuesto, la pregunta no es *"esto rota?"* sino **"que dimension decide
quien queda afuera, y esa es la que rota?"**.

### Los carteles: dos advertencias que se encendian siempre

Ninguno era el bug, pero los dos lo TAPABAN — es la regla del chip ambar otra vez, *"una
senal que se enciende en todos deja de ser una senal"*, ahora en la consola.

**1. `"108 paginas, se toman 2"` en NOVEDADES.** Tomar 2 de 108 ahi es el diseno: lo
recien publicado esta arriba por definicion y las otras 106 son historia. Salia para
todos los barrios grandes, todos los dias. Ahora la advertencia sale **solo en cobertura**,
que es donde truncar SI significa inventario que no se mira.

**2. `"(de 288; el resto no es alcanzable sin paginar)"` de MercadoLibre** — este es
literalmente el que Mario leyo. Tampoco es un error: el `robots.txt` de ML prohibe
`_Desde_`, asi que de cada busqueda se ve UNA pagina de 48 y el resto **no es pedible**.
Pero se imprimia en cada busqueda truncada, o sea en casi todas. Ahora va **una sola
linea al final** con el total, que ademas es el numero que importa: cuanto inventario de
ML no se puede ver.

**Y una tercera, que faltaba:** al final del barrido se dice **cuantas tareas quedaron sin
pedir** (`quedaron 24 de 72 tareas sin pedir; las toma la proxima corrida`). Que una
corrida corte por presupuesto es lo normal — el plan entero no entra en 90 pedidos, por
eso rota — pero callarlo hacia que *"corto"* y *"no habia nada"* se leyeran igual. Es el
mismo agujero que la banda de datos viejos de la sesion 11b, en la consola.

### Falsa alarma: los tres favoritos que "faltaban"

`favoritos` cayo de 5 a 3 y #1 Giribone, #7 Cabrera y #203 Jorge Newbery no estaban en la
base. **No se perdio nada: Mario los descarto el 2026-08-30 a las 19:11 desde la web** y
salieron por el veto de descartados, como corresponde. La bitacora lo dice entera. Entro
uno nuevo, **#5131 Galvan al 2800** (Villa Urquiza, USD 1.400).

## Riesgos vigentes

1. **La cobertura ya no es completa por corrida, y es a proposito.** Con el techo de 90
   pedidos, la pasada de cobertura no llega a todos los barrios en un dia: rota y se
   completa en dos o tres corridas. **Si pasan varios dias sin correr, el sistema no
   "espera": simplemente no mira.** Es el mismo agujero que causo el reclamo del 2026-08-21,
   ahora acotado pero no cerrado. Correr todos los dias.
2. **Solo 56 de 1.754 avisos tienen fotos locales**, y sin fotos locales Claude no puede
   mirar nada (`clasificar.py`). Las baja `detalle.py`, 1 pedido por aviso, 15 por corrida.
   A ese ritmo, los 103 candidatos tardan una semana.
3. **La vigencia de los candidatos es vieja.** La unica prueba de que un aviso sigue vivo es
   pedir su URL (`detalle.py --solo-vigencia`). Hoy hay 11 caidos confirmados y ~90
   candidatos sin verificar desde que entraron.
4. **La velocidad del mercado sigue sin poder medirse hacia atras.** Recien ahora, con la
   fecha de publicacion en el 100% de lo nuevo, se puede empezar a medir de verdad.
5. **Argenprop trae 40 avisos y una sola pagina por barrio.** Su formato de paginado sigue
   sin verificarse, asi que de ese portal se ve la punta del inventario.
6. **En MercadoLibre los departamentos son una ventana fija.** robots.txt prohibe paginar
   y ordenar, asi que se ven los mismos 48 por barrio cada dia y no hay forma permitida de
   pedir el resto (Belgrano: 48 de 293). En casas y PH si se ve todo. La unica via para lo
   que queda debajo es que el portal lo suba en su propio orden.
7. **Los avisos de MercadoLibre entran sin dato de exterior** (m2 totales aparece en el
   2,5%). Son el 27% de la lista corta y todos llevan el exterior "a preguntar", que es el
   criterio de mayor peso. Completarlo es trabajo de `detalle.py`, un pedido por aviso.

## Reglas de trabajo

- Al final de cada corrida: actualizar este archivo.
- Despues de cada tanda de descartes: buscar el patron y **proponer** un diff a `config.yaml`.
  Mostrarlo y esperar confirmacion. Nunca aplicarlo solo.
- Registrar tambien los aciertos, no solo los rechazos.
- Reforzar contacto con inmobiliarias que no respondieron **cada diez dias**.
- En el chat: tres lineas. Si no hay nada bueno, "hoy no hay nada". No inflar el reporte.
- Cuando algo valga la pena: no "cumple los filtros", sino "esto lo llamaria hoy y esta es la
  pregunta que haria primero".
- Si el criterio propio se contradice, decirlo.
- **Verificar antes de afirmar.** Este proyecto ya corrigio dos advertencias propias por no
  haberlas probado primero.
