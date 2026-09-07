# Busqueda de alquiler — que es cada cosa

Guia en castellano de para que sirve cada archivo de esta carpeta.
(La documentacion tecnica esta en `CLAUDE.md`; esto es el mapa.)

---

## Para usarlo

### `abrir.bat` ← **doble click aca. Es el unico que hace falta.**

Un archivo de texto con comandos de Windows (formato *batch*). Al hacerle doble click:

1. mira si ya se busco hoy en el portal;
2. **si no se busco, busca** (tarda entre 5 y 15 minutos, va contando en la ventana);
3. levanta un servidor chiquito **en tu propia maquina** y abre el navegador.

O sea: no tenes que elegir entre buscar y mirar. Abris esto y esta actualizado.

**Ademas la busqueda corre sola todas las mananas a las 9**, sin ventanas ni navegador
(es una tarea del Programador de tareas de Windows llamada `BusquedaAlquiler-Diaria`).
Por eso lo normal es que `abrir.bat` abra directo, sin esperar. Si la maquina estaba
apagada a esa hora, la tarea corre cuando la prendes.

### `actualizar.bat`

Fuerza una busqueda **aunque ya se haya hecho hoy** — por ejemplo a la tarde, para ver si
salio algo despues de la corrida de la manana. Para el uso normal no hace falta. Hay un
techo de dos busquedas por dia: pasado eso el sistema saltea la red solo, porque al portal
no se le puede insistir.

### Si la pagina te dice que los datos estan viejos

Arriba de todo aparece una banda avisando hace cuantos dias que no se baja nada
(en rojo a partir de tres). Significa que la busqueda no corrio, no que no haya
propiedades nuevas. Se arregla cerrando y abriendo `abrir.bat`.

**La ventana negra que aparece es el servidor.** Mientras este abierta, todo lo que marques
en la pagina (corazon, descarte, nota) **se guarda solo en el disco**. Cuando termines,
cerra la ventana y se apaga.

Existe porque un `index.html` abierto con doble click no tiene permiso para escribir
archivos: el navegador no lo deja, por seguridad. Servido desde `localhost`, si puede.

Si abris `web/index.html` directo, la pagina funciona igual **pero lo que marques queda
solo en ese navegador** hasta que le des a "Exportar decisiones". La pagina te avisa con
una banda roja cuando estas en ese modo.

---

## Lo que ves en la pagina

### Las cinco vistas

| | |
|---|---|
| **Favoritos** | los que marcaste con el corazon. Es la pantalla de arranque |
| **Explorar** | todo el resto, para escanear rapido: fotos grandes y juntas. **Pasa el mouse por una foto y recorre las demas** sin abrir nada |
| **Ultimas 2 semanas** | lo publicado hace 14 dias o menos: la lista para llamar hoy |
| **Descartados** | todo lo que rechazaste, con tus palabras textuales y el aprendizaje |
| **Actividad** | la bitacora completa: cada decision, en orden |

### El numero `#7`

Cada propiedad tiene un numero corto y fijo. Es para que me escribas
**«descarta el 3 porque la cocina esta hecha pelota»** en vez de pasarme un link.
El numero no se reasigna nunca.

### El puntaje `67 / hasta 91`

No es un numero, es un **rango**:

- **67 (piso)** = lo que la propiedad tiene *demostrado* con los datos que hay.
- **hasta 91 (techo)** = lo que daria si lo que todavia no sabemos saliera tan bien
  como lo que ya sabemos.

Cuanto mas datos hay, mas se cierra el rango. Se ordena por el piso.

Se hizo asi porque un numero solo mentia: al normalizar sobre lo conocido, **la falta de
datos subia el puntaje**. Un aviso que no declaraba exterior se salteaba el criterio que
mas pesa y quedaba arriba.

### Las etiquetas de la foto

| | |
|---|---|
| `RECICLADO` / `BUENO` / `COSMETICO` / `SIN DATOS` | estado. `SIN DATOS` = el aviso no dice nada, y eso no es neutro: es sospechoso |
| `AL LIMITE` | falla **un solo** filtro duro por poco. Va aparte, no compite en el mismo ranking |
| `RIESGO` | hay algo que puede voltear la operacion (ej: garantia imposible) |
| `5A PUBLICADO` | lleva mucho tiempo publicado. O el dueno no tiene apuro, o algo lo frena |
| `DUEÑO DIRECTO` | sin inmobiliaria en el medio |
| `CAIDO` | el aviso ya no esta publicado |

### La banda de arriba

Dice que le falta al sistema para darte una respuesta confiable. Hoy dice que **falta el
analisis de fotos**: es el paso que mira las imagenes y decide el estado real (reforma de
verdad vs. mano de pintura), y es el que ordena la lista. Necesita la API de Claude, que
todavia no esta habilitada.

---

## Los archivos de datos

| Archivo | Que es |
|---|---|
| `data/eventos.jsonl` | **tus decisiones.** Una linea por cada cosa que marcaste. Solo se agrega, nunca se pisa. **Es lo unico irreemplazable del proyecto** |
| `data/avisos.json` | los datos de las propiedades, bajados de los portales. Se puede borrar y volver a bajar |
| `data/descartados.json` · `favoritos.json` · `visitas.json` | derivados: se regeneran solos leyendo la bitacora |
| `data/propiedades.csv` | planilla para abrir en Excel. **Solo para mirar**, no se vuelve a importar |
| `data/cotizaciones.json` | historico del dolar BNA, para que los precios viejos sigan siendo comparables |
| `web/fotos/` | las fotos bajadas, una carpeta por propiedad |

## Los archivos de configuracion y memoria

| Archivo | Que es |
|---|---|
| `config.yaml` | los criterios: presupuesto, minimos, pesos del puntaje, zonas. **Se puede editar a mano** |
| `perfil.md` | que buscas, en prosa |
| `CLAUDE.md` | mi memoria entre sesiones: decisiones tomadas, contradicciones abiertas, riesgos |
| `conocimiento/*.md` | lo que fuimos aprendiendo: como funciona Zonaprop, el mercado por barrio, las inmobiliarias, las garantias |
| `corridas/*.md` | que paso cada dia |

## Los scripts

Todos se corren con `python scripts\<nombre>.py` desde esta carpeta.

| Script | Que hace | Cuesta |
|---|---|---|
| `main.py` | la corrida completa, de punta a punta | usa API |
| `fetch.py` + `parse.py` | bajan y leen los listados de los portales | gratis |
| `detalle.py` | abre la ficha de cada aviso: fotos, m² reales, antiguedad. **Tambien chequea que siga publicado** | gratis |
| `cotizacion.py` | trae el dolar BNA del dia y recalcula los precios | gratis |
| `reglas.py` | lee las descripciones y aplica el vocabulario (amoblado, mascotas, uso, estado) | gratis |
| `clasificar.py` | manda texto y **fotos** a la API de Claude para lo que las reglas no pueden | **paga** |
| `score.py` | calcula los puntajes y aplica los filtros duros | gratis |
| `build.py` | regenera lo que lee la pagina | gratis |
| `eventos.py` | la bitacora. Es por donde entran las decisiones que te tomo por chat | gratis |
| `servidor.py` | el servidor local que levanta `abrir.bat` | gratis |
