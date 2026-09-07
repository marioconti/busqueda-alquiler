# Perfil de busqueda

> Mantenido por el **Asesor**. Se actualiza cuando el bucle de aprendizaje detecta un patron
> confirmado, nunca por intuicion suelta. Ultima actualizacion: 2026-08-14 (carga inicial).

## Filtros duros

> **Corregido por Mario el 2026-08-14.** El perfil original venia del prompt de arranque y
> pedia 3 dormitorios y 90 m2 cubiertos. Sus palabras:
>
> *"no me interesa tanto los metros cuadrados si algo medianamente grande, me interesa mas
> el tema de las habitaciones. minimo 2, 3 amb minimo, idealmente dos banos, o bano y
> toillet, cochera, jardin o terraza amplia"*
>
> El cambio duplico el inventario alcanzable: de 43 a 106 candidatos.

| Filtro | Valor | Nota |
|---|---|---|
| Presupuesto | USD 2.000/mes | **Confirmado: es techo firme.** Alquiler + expensas, al dolar oficial BNA venta del dia, guardando la cotizacion usada |
| Dormitorios reales | **2 minimo** | era 3. Escritorio, entrepiso, playroom y dependencia de servicio **no cuentan**, aunque el aviso los sume |
| Ambientes | **3 minimo** | nuevo |
| M2 cubiertos | **60 minimo** | era 90. **Ya no es un criterio**: es solo un piso de sanidad para que no entre un monoambiente mal etiquetado. "Medianamente grande" lo resuelve el score |
| Amoblado | NO | "amoblado", "equipado", "se entrega con muebles", "apto Airbnb", "listo para ingresar con tu valija" -> afuera |
| Mascotas | SI (hay un gato) | "no acepta mascotas" o "perros si, gatos no" -> afuera. Si no aclara: **a confirmar**, se muestra igual |
| Uso | Vivienda | "apto profesional exclusivamente", "solo uso comercial", temporario -> afuera |
| Estado | bueno o mejor | "a refaccionar", "a reciclar", "con potencial de reciclaje" -> afuera |

### Seccion "Al limite"

Si falla **un solo** duro por menos del 15%, se muestra en una seccion aparte, con el motivo
declarado, y **no se puntua en el mismo ranking**.

Nunca entran a "Al limite": **mascotas, amoblado, uso**. Son binarios.

Precedente que justifica la seccion: Alvarez Thomas 225 tiene 73 m2 cubiertos contra un minimo
de 90 y esta en favoritos, porque 40 m2 de terraza exclusiva mas que compensan. Filtrarlo en
silencio habria sido el peor resultado posible.

> **Contradiccion abierta:** 73 vs 90 es -18,9%, o sea que con la tolerancia del 15% ese mismo
> caso queda afuera. Ver `CLAUDE.md` > Contradicciones abiertas. Hasta que se resuelva, los
> favoritos marcados a mano nunca se filtran.

## Blandos, en orden de peso

1. **Espacio exterior propio y al sol.** Terraza, patio, jardin o parque; todos cuentan y se
   suman. Caminable y utilizable, con lugar para muchas plantas. 40 m2 de terraza descubierta
   valen mas que 40 m2 de quincho techado.
2. **M2 cubiertos por encima de 110.**
3. **Dos o mas banos completos.** El toilette no cuenta.
4. **Tranquilidad.** Prioritario. Contrafrente, calle interna, sin avenida. Chequear:
   sala de maquinas de ascensor arriba o al lado, medianera con local comercial o gastronomico,
   cercania a colegio o club. Si hay direccion exacta, verificar el entorno (Street View).
5. **Pocos vecinos o ninguno.** Casa sobre lote propio = ideal. PH con entrada independiente =
   muy bien. Edificio de 3-4 unidades = aceptable. Torre solo con terraza excepcional.
6. **Sin expensas o expensas bajas.** Sin expensas vale por si mismo: no hay administracion,
   ni asamblea, ni consorcio.
7. **Parrilla propia.**
8. **Luminosidad.** Orientacion norte o noreste, techos altos, vista abierta.
9. **Dueno directo.** Menos friccion en la garantia, menos intermediarios.

## Departamentos

Entran **solo** con terraza propia amplia declarada. Un balcon no alcanza. De ~400 revisados en
Belgrano y Palermo no salio ninguno que valiera la pena: prioridad baja (factor 0,4).

## Zonas

- **Incluidas:** Palermo, Belgrano, Colegiales, Nunez, Saavedra, Almagro.
- **Ampliacion aprobada:** Villa Ortuzar.
- **Excluidas:** Chacarita, Las Canitas.
- Las Canitas se publica como Belgrano y como Palermo: **filtrar por descripcion, no por el
  campo de barrio**.

## Situacion personal (para el mensaje a inmobiliarias)

- Cobra **en dolares como contractor**. Para un propietario que vive afuera, es el inquilino que
  quiere. Eso va en la **primera linea** del mensaje, no al final.
- Tiene **un gato**.
- Garantia: ver `conocimiento/garantia.md`.

## Perfil aprendido (se llena con el uso)

> Objetivo: predecir la respuesta antes de mostrar la propiedad ("85% de match con tu perfil
> aprendido"). Todavia sin datos suficientes: 12 aciertos y 36 descartes de semilla, sin
> atributos completos en la mayoria de los descartes.

**Senales fuertes ya visibles en la semilla:**

- 7 de 12 aciertos estan en **Saavedra**. Ver `conocimiento/mercado.md`: es estructural, no azar.
- El motivo de descarte mas frecuente es **uso comercial exclusivo** (15 casos), que no es una
  preferencia sino un filtro de mercado: hay que evitar gastar corridas en Colegiales-casas.
- Ningun acierto es departamento. Los 12 son casa, PH, duplex o triplex.
- Tolera **1 solo bano** cuando hay terraza grande (Giribone, Vedia, Nunez 2306, Plaza, Alvarez
  Thomas: 5 de 12 aciertos tienen 1 bano). O sea: banos **no** debe subir a duro.
