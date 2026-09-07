# Inteligencia de mercado

> Mantenido por el **Corredor inmobiliario**. Esto no describe avisos, describe **como se
> comporta el mercado**. Cada afirmacion lleva la muestra sobre la que se apoya.
>
> **Actualizado 2026-08-14 con el primer barrido completo: 284 avisos de 7 barrios.**
> Lo anterior se apoyaba en una muestra de 12 propiedades ya filtradas; esto se apoya en
> el universo, incluido lo que NO pasa. Es otra cosa.

---

## La tabla que importa: tasa de candidatos por barrio

De 284 avisos de casas y PH en alquiler, cuantos sobreviven a los filtros duros:

| Barrio | Avisos | Mediana USD | ≤ 2.000 | Candidatos | **Tasa** | Dueno directo |
|---|---:|---:|---:|---:|---:|---:|
| **Almagro** | 25 | 1.122 | 20 | 7 | **28 %** | 4 |
| **Villa Ortuzar** | 11 | 1.300 | 10 | 3 | **27 %** | 1 |
| **Saavedra** | 26 | 1.155 | 23 | 6 | **23 %** | **8** |
| **Colegiales** | 24 | 1.386 | 16 | 5 | **21 %** | 3 |
| Palermo | 99 | 1.452 | 63 | 15 | 15 % | 6 |
| Nunez | 31 | 1.400 | 18 | 3 | 10 % | 1 |
| **Belgrano** | 57 | **3.960** | 14 | 2 | **4 %** | 3 |

**Como leerla:** Palermo aporta el mayor NUMERO de candidatos (15) simplemente porque es
cuatro veces mas grande que los demas. Pero la TASA dice donde conviene mirar primero, y
ahi Palermo es apenas mediocre.

### Tres cosas que esta tabla cambia

**1. Almagro es el hallazgo, y no estaba en el radar.** Mediana de USD 1.122 —el barrio
mas barato del set—, 20 de 25 avisos dentro de presupuesto y la mejor tasa de todas. En la
version anterior de este archivo Almagro solo aparecia en la lista de descartes por estado.
Merece una mirada seria, con la reserva de que el estado ahi hay que verificarlo: los dos
descartes historicos de Almagro (Querandies 4300, Gascon 158) fueron por estado.

**2. Belgrano esta confirmado como cerrado, y con numeros peores de lo que se creia.**
Mediana **USD 3.960** — casi el doble del presupuesto entero. Solo 14 de 57 avisos bajan de
2.000, y de esos solo 2 pasan los filtros. La lectura previa ("de 51 avisos solo dos bajan
de USD 2.000") era demasiado dura en la cuenta pero exacta en la conclusion.

**3. Saavedra es la capital del dueno directo: 8 de 26 (31 %),** contra un 10 % del
universo. Eso confirma que es zona de propietarios que alquilan por su cuenta a familias,
que es exactamente el perfil que menos friccion tiene con la garantia.

---

## Precio

| | USD |
|---|---|
| Mediana del universo | 1.500 |
| Percentil 25 | 904 |
| Percentil 75 | 3.200 |
| Maximo | 18.640 |
| Avisos ≤ 2.000 | 172 de 284 (61 %) |

**USD por m2 cubierto, entre los que entran en presupuesto** (n=100, ≥60 m2):

| min | p25 | mediana | p75 |
|---:|---:|---:|---:|
| 6,1 | 11,6 | **14,0** | 17,1 |

La mediana de 14 coincide exactamente con la que se habia estimado sobre la muestra de 12.
Regla practica: **arriba de 17 USD/m2 hay que poder explicar por que** —terraza grande,
estado a nuevo, dueno directo—. Si no hay explicacion, es caro.

---

## Que deja afuera a los avisos

De los 241 que no pasan (un aviso puede fallar varios filtros):

| Filtro | Falla | **Falla SOLO por esto** |
|---|---:|---:|
| dormitorios (min 3) | 128 | 13 |
| m2 cubiertos (min 90) | 118 | 11 |
| **presupuesto (2.000)** | 107 | **79** |
| amoblado | 24 | 0 |
| uso | 11 | 1 |
| mascotas | 6 | 3 |
| estado | 5 | 1 |

**El presupuesto es, por lejos, el filtro que mas propiedades mata por si solo.** 79 avisos
cumplen TODO lo demas y caen unicamente por precio. Si el tope pasara de 2.000 a 2.500, el
universo de candidatos saltaria de 31 a ~110.

Los otros dos duros son mucho menos sensibles: aflojar dormitorios sumaria 13, aflojar
metros sumaria 11.

---

## Tipo de propiedad por barrio

| Barrio | PH | Casa |
|---|---:|---:|
| Palermo | 74 | 24 |
| Belgrano | 17 | 40 |
| Saavedra | 19 | 7 |
| Colegiales | 19 | 5 |
| Nunez | 16 | 15 |
| Almagro | 15 | 10 |
| Villa Ortuzar | 7 | 4 |

**Belgrano es el unico barrio donde manda la casa entera** — y es tambien el mas caro. En
todos los demas el producto dominante es el PH, que es coherente con la tesis previa: casa
chorizo de los anos veinte a cuarenta, subdividida.

Ojo con esto para la busqueda: el slug `casa-alquiler-` en **singular** es el que trae PH.
El plural devolveria casi solo Belgrano.

---

## Dueno directo

**28 de 284 (10 %).** Distribucion: Saavedra 8, Palermo 6, Almagro 4, Belgrano 3,
Colegiales 3, Lomas de Nunez 2, Nunez 1, Villa Ortuzar 1.

Se detecta de dos formas independientes que coinciden: el prefijo `pa` en la URL del
clasificado y el campo `publisherTypeId` de la ficha.

---

## El canal de las inmobiliarias

Ninguna inmobiliaria concentra el mercado: la que mas publica tiene 8 avisos de 284.

| Avisos | Inmobiliaria |
|---:|---|
| 8 | SHENK INMOBILIARIA |
| 5 | MIGLIORISI Villa Crespo |
| 4 | D'Antonio Propiedades |
| 3 | Florencia Rossi · Eduardo GULESSERIAN · ABITI · Yacoub · Full Host · Otero Propiedades |
| 2 | LAO LUCHETTI · RE/MAX Village · Julieta Mercado |

**LAO LUCHETTI** ya estaba en la lista de contactos de `inmobiliarias.md`, que se armo a
mano antes del barrido: la lista iba bien encaminada.

Que el mercado este tan atomizado refuerza la tesis del canal directo: **no hay un puñado
de jugadores a los que escribirles y cubrir el mercado**. Hay que ir por barrio.

---

## Velocidad del mercado

**Sin datos todavia.** Se llena solo con `estado_aviso: desaparecido`: dias entre
`first_seen` y la desaparicion, por barrio y por rango de precio.

Es el dato que responde la pregunta que importa: **cuanto puedo demorar en decidir**. No se
puede medir hacia atras, solo acumulando corridas. Con este barrido quedaron 284 avisos con
`first_seen` — el reloj arranco hoy.

---

## Pendiente de construir

- [ ] Velocidad de rotacion por barrio y rango (necesita 3-4 semanas de corridas).
- [ ] Barrios adyacentes sin barrer: **Villa Urquiza, Coghlan, Parque Chas, Agronomia**.
      Son el mismo producto que Saavedra y Villa Ortuzar (lote propio, alquiler familiar)
      y no estan en el config.
- [ ] Argenprop: ahi publican las inmobiliarias chicas de barrio, que con un mercado tan
      atomizado es donde puede estar la diferencia.
- [ ] Cuanto se negocia efectivamente sobre el precio publicado.
