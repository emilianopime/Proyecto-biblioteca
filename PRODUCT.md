# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- Primaria: la bibliotecaria o administradora del laboratorio de cómputo de la biblioteca de la Universidad Autónoma de Chihuahua (UACH). No es técnica. Usa el panel desde una PC de escritorio en el mostrador, de reojo y muchas veces al día, en una sala iluminada.
- Secundaria: quien administra el servidor (Gustavo), que despliega y revisa logs.
- Los alumnos no ven el panel: interactúan con el kiosko de cada máquina, que les pide su matrícula.

## Product Purpose

Monitorear en tiempo real el laboratorio: qué máquinas están libres, cuáles tiene un alumno y cuáles no responden; llevar la bitácora de entradas y salidas; cargar el padrón de alumnos que el kiosko acepta; y producir reportes de uso por periodo para la dirección. Éxito: la bibliotecaria responde "¿dónde siento a este alumno?" en un segundo y puede entregar un reporte mensual sin abrir Excel.

## Positioning

Es la única herramienta que sabe, máquina por máquina y en vivo, quién está usando el laboratorio, porque el kiosko de cada equipo manda su estado al servidor cada 10 segundos. Un sistema de biblioteca o un monitor de red genérico no tienen esa información.

## Operating Context

- Servidor Flask con PostgreSQL en Docker, en una PC del laboratorio; el panel se abre en el navegador en el puerto 8000. Kioskos en Python/Tkinter en cada máquina Windows del laboratorio.
- El padrón sale del sistema de la biblioteca como CSV (columnas Carnet, Apellido(s), Nombre(s), Carrera y otras que se ignoran), una o dos veces por semestre.
- Semestres: enero-julio y agosto-diciembre. Hora local: America/Chihuahua.
- El laboratorio puede tener del orden de 40 equipos.

## Capabilities and Constraints

- Vistas: Equipos, Padrón, Estadísticas (con reporte por periodo en página, PDF y Excel), Bitácora (búsqueda, filtros, descarga CSV) y Ayuda. Login con usuario único.
- Estados de un equipo: libre, en uso, sin conexión, sin información. Un solo estado por máquina.
- Cada carga del padrón conserva el anterior y se puede restaurar.
- Sin dependencias de internet en producción salvo las fuentes de Google; el contenedor no tiene la fuente IBM Plex para el PDF.
- Terminología fija: equipo (no nodo), entrada y salida (no login/logout), padrón, matrícula, kiosko, señal (no latido).
- Sin emojis en la interfaz. Todo en español.

## Brand Commitments

- Marca institucional: escudo de la UACH (anillo morado #8c2889 con el nombre en amarillo #f9ed25, campo verde #23945d con rayo amarillo, cielo azul #6ebde3 y #00aee5 con montañas, rayos blancos) y nombre "Universidad Autónoma de Chihuahua" en serif de mayúsculas color café oscuro #2e200f. Lema: "Luchar para lograr, lograr para dar".
- Restricción explícita del dueño: el morado y el verde NO deben ser el color principal de la app; solo referencias sutiles que recuerden la inspiración. Logo disponible como PNG (pendiente de agregar al repo).
- El producto se firma como "Control de Laboratorio" de la biblioteca de la UACH.
- Decisión del dueño (18 de septiembre de 2026, tras ver seis maquetas alternativas): se conserva la identidad visual actual, azul marino oscuro con acento cian, tema claro equivalente, IBM Plex Sans y Mono. No proponer rediseños de identidad salvo que lo pida.

## Evidence on Hand

- Datos reales: padrón de ~94,000 alumnos cargado en la instancia local; bitácora real pequeña. Datos ficticios de simulación (40 equipos, 900 eventos) disponibles para capturas.
- No hay manual de identidad de la universidad a la mano. No inventar colores oficiales más allá de los extraídos del logo.

## Product Principles

1. La pregunta del mostrador primero: libres, en uso, sin conexión, en un vistazo.
2. Nunca mentir sobre el estado: si el servidor no responde o la máquina está apagada, decirlo.
3. Cada acción con riesgo tiene confirmación y camino de vuelta.
4. Lenguaje de la bibliotecaria, no de red.
5. La identidad institucional se insinúa; la claridad operativa manda.
