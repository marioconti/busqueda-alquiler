# Garantia, deposito y condiciones de contrato

> Mantenido por el **Documentador**. Dos propiedades al mismo precio pueden costar muy distinto.
> Este archivo existe para que eso se vea antes de la visita, no despues.

## Que hay que extraer de cada aviso

| Campo | Valores tipicos | Por que importa |
|---|---|---|
| Garantias aceptadas | propietaria CABA, propietaria GBA, seguro de caucion, recibo de sueldo, garantia corporativa | Es el filtro que mas propiedades mata en la practica |
| Deposito | meses y moneda | Un deposito de 2 meses en USD es plata inmovilizada |
| Plazo de contrato | 24 / 36 meses, o 12 | 12 meses es senal de que el dueno no quiere alquilar de verdad (seccion 6 del perfil) |
| Indice de ajuste | IPC, ICL, % fijo, sin ajuste | Define el costo real a 2 anos, no a 1 mes |
| Frecuencia de ajuste | trimestral, cuatrimestral, semestral, anual | Con inflacion, la frecuencia pesa casi tanto como el indice |
| Moneda | ARS / USD | USD fijo es previsible; ARS con ajuste no |
| ABL | inquilino / propietario | |
| AYSA | inquilino / propietario | |
| Seguro de incendio | a mi cargo o no | |
| Comision | ver abajo | |

## Situacion de Mario — **CONFIRMADO 2026-08-14**

- **Cobra en dolares como contractor.** Es un activo frente a un propietario que vive afuera
  o que quiere cobrar en USD, y va en la primera linea del mensaje.

**Lo que puede poner:**

| Garantia | Tiene | Consecuencia |
|---|---|---|
| **Seguro de caucion** | SI | La via principal. Preguntar SIEMPRE de que compania la aceptan: no todas aceptan todas |
| **Recibos / facturacion** | SI | Respaldo de ingresos. Casi nunca alcanza como garantia unica, pero refuerza la caucion |
| **Propietaria en GBA** | SI | Muchas inmobiliarias la aceptan; otras piden CABA sin excepcion |
| **Propietaria en CABA** | **NO** | Es la que piden por defecto. Su ausencia es el filtro real de este proyecto |

### Que significa para la busqueda

**El primer filtro de una operacion no es el precio: es si aceptan caucion.** Antes de
invertir tiempo en una propiedad hay que preguntarlo, y conviene hacerlo en el primer mensaje.

**Plaza 2474 (#3) queda practicamente descartada.** Es el favorito mas barato —USD 1.188 por
106 m2 en Belgrano R— y pide *solo* garantia propietaria de CABA, sin aceptar caucion. Ahora
sabemos que eso es exactamente lo que Mario no tiene. Se mantiene como riesgo, no como
descarte, hasta que alguien pregunte si hay excepcion; pero el precio de esa propiedad
probablemente se explique justo por ahi.

**El dueno directo vale mas de lo que dice su peso en el score.** Un propietario que alquila
por su cuenta negocia la garantia; una inmobiliaria aplica su politica. En el inventario hay
28 duenos directos, concentrados en **Villa Urquiza (9)** y **Saavedra (8)**.

## Casos registrados

| Propiedad | Condicion | Estado |
|---|---|---|
| Plaza 2474 (Belgrano R) | Pide **solo garantia propietaria de CABA**, no acepta caucion | **Riesgo, no descarte.** Es el favorito mas barato (USD 1.188 por 106 m2): la garantia imposible probablemente explique el precio. Vale la pregunta antes de descartarlo |
| Besares 2063 (Lomas de Nunez) | USD 1.800 **fijos** (sin ajuste) y acepta mascotas | Descartada por dormitorios, pero el criterio de la inmobiliaria es notable. Ver `inmobiliarias.md` |
| Cabrera 5749 (Palermo Hollywood) | USD 2.000 con **contrato largo** | Descartada por amoblada, con la pregunta pendiente de si lo entrega vacio |

## Comision inmobiliaria — dato a verificar, no certeza

Varios avisos citan que en CABA esta **prohibido cobrarle comision inmobiliaria y gastos de
gestoria de informes al inquilino persona fisica**. Si alguna inmobiliaria pretende cobrarla, hay
que marcarlo.

> **No somos abogados.** Esto se trata como un dato a verificar con un profesional si llega a haber
> un conflicto concreto, no como una certeza legal para discutir en un mostrador.

## Regla de desempate

Cuando dos propiedades quedan **empatadas en score**, el desempate es por **condiciones
contractuales**, y la cuenta que hay que hacer es **a dos anos, no a un mes**:

```
costo_2_anos = (alquiler + expensas) * 24 ajustado por indice y frecuencia
             + deposito inmovilizado (costo de oportunidad)
             + ABL + AYSA + seguro si van por cuenta del inquilino
             + comision si corresponde
```

Ese numero es el que se compara, no el precio publicado.

## Preguntas fijas para cualquier propiedad

- Que garantias acepta **ademas** de la propietaria, y si acepta caucion **de cual compania**
  (no todas las inmobiliarias aceptan todas las companias).
- Si acepta contrato de 2 anos cuando el aviso dice 1.
- Que indice y con que frecuencia ajusta.
- Deposito: cuantos meses y en que moneda.
- ABL y AYSA por cuenta de quien.
