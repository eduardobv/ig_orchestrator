# Patch v1.26.8 - Doble click del catálogo

## Problema

El doble click del catálogo abría el perfil en Chrome, pero no trasladaba la
cuenta seleccionada al campo `Editor > Username`.

## Solución

El mismo evento carga primero el username y sus metadatos históricos en el
editor y después abre el perfil en una pestaña de Chrome.

## Pruebas

Se agrega una prueba de regresión que verifica ambas acciones con una sola
invocación del evento.
