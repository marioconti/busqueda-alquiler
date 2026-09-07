# Inmobiliarias y contactos

> Mantenido por el **Secretario**. Este es el canal que mas rinde y el que ningun scraper da: en
> este segmento buena parte del inventario se coloca **antes de publicarse**, o directamente nunca
> se publica.

## Zonas objetivo del canal directo

Saavedra, Villa Ortuzar, Villa Urquiza, Colegiales, Belgrano R. Son las zonas donde el producto que
sirve (casa o PH sobre lote propio, alquiler familiar a dos anos) lo maneja la inmobiliaria chica
de barrio, no el portal.

## Lista de trabajo

Nombres que ya aparecieron en los avisos revisados y manejan este tipo de propiedad. Faltan
matricula, telefono y zona: **se completan leyendo el pie de cada aviso** (Zonaprop publica nombre
del corredor y matricula CUCICBA en la ficha), no buscando por afuera.

| Inmobiliaria | Corredor | Matricula CUCICBA | Zona | Contacto | Maneja | Ultimo contacto | Respondio | Tiempo respuesta |
|---|---|---|---|---|---|---|---|---|
| Axel Eboli | | | | | | | | |
| Navarro Torres | | | | | | | | |
| Gonzalez Neira | | | | | | | | |
| Guidetti | | | | | | | | |
| Estudio Monaco | | | | | | | | |
| Del Campo | | | | | | | | |
| Marting | | | | | | | | |
| Curcio | | | | | | | | |
| Lao Luchetti | | | | | | | | |
| Cippolini Suter | | | | | | | | |
| E. Furio | | | | | | | | |

**Recordatorio activo:** reforzar el contacto **cada diez dias** con las que no respondieron.
Proximo recordatorio: cuando se envie el primer mensaje (todavia no se envio ninguno).

## Como se completa esta tabla

De cada aviso que se scrapea se extrae el bloque del anunciante y se hace upsert en esta tabla.
No se busca informacion de contacto por fuera de los avisos.

Dato adicional que vale la pena registrar aunque la propiedad se descarte: **que criterio maneja la
inmobiliaria**. Ejemplo real de la semilla: la de Besares 2063 publica a **USD 1.800 fijos sin
ajuste** y **acepta mascotas explicitamente**. Esa propiedad se descarto por dormitorios, pero una
inmobiliaria con ese criterio es exactamente a la que hay que preguntarle que mas tiene.

## Mensajes enviados

> Se guarda cada mensaje **con su texto completo y su fecha**, para poder comparar despues que
> version tuvo mejor tasa de respuesta. Todavia no se envio ninguno.

| Fecha | Inmobiliaria | Propiedad | Version del mensaje | Respondio | Dias |
|---|---|---|---|---|---|

### Plantilla v1 (sin usar todavia)

Estructura fija, en este orden y sin parrafos de presentacion:

1. **Quien soy y como cobro** — cobro en dolares como contractor. Para un propietario que vive
   afuera, eso me convierte en el inquilino que quiere. **Va en la primera linea, no al final.**
2. **Que busco**, en una frase.
3. **Tengo un gato.**
4. **Cuando me quiero mudar.**
5. **El pedido concreto de coordinar visita.**

Nada de "quedo a la espera", nada de presentacion larga. Tono de persona real.

## Pendientes del canal directo

- [ ] Completar matricula, zona y contacto de las once de la lista, desde los avisos.
- [ ] Redactar y aprobar la version 1 del mensaje.
- [ ] Primera tanda de contacto.
- [ ] Ampliar la lista con las inmobiliarias que aparezcan en Argenprop (ahi estan justamente las
      chicas de barrio que no publican en Zonaprop).
