# Cambios entre versiones (qué hacer al replicar)

Una entrada por versión que pida algo más que copiar código. `sincronizar.bat` muestra las
entradas posteriores a la versión que tenías. Formato del título: `## vX.Y.Z · resumen`.

## v4.20.0 · Descarga HTTP y bot caído
En cada instancia: *Configuración > Ejecución > Sesión HTTP* → pega la cookie `sessionid` de Instagram (puede ser otra cuenta) y pulsa **Probar sesión**. Sin ella la descarga HTTP no se usa (la detección de bot caído sí). La tabla `http_downloads` se crea sola; no hay SQL. Revisa que la URL de prueba (*Bot caído*) siga existiendo.

## v4.18.1 · inst_sync en dos partes
Desde el PC principal ejecuta `inst_sync\empujar.bat` (la ruta de la instancia está en `inst_sync\destino.txt`): copia el código y avisa si hace falta ejecutar `inst_sync\sincronizar.bat` en la instancia (ahora solo dependencias, SQL y base; ya no necesita `origen.txt`).

## v4.18.0 · inst_sync
Nuevo `sincronizar.bat`. Escribe en `inst_sync\origen.txt` la ruta del PC principal (una vez).
A partir de aquí basta con detener el batch y hacer doble clic.

## v4.17.0 · Renew
Sin pasos manuales. Renew no cambia el esquema de la base.

## v4.16.0 · Pausa entre URLs / bot sin respuesta
Sin pasos manuales. Nuevos ajustes en *Configuración > Ejecución* (se crean con su valor por defecto).

## v4.4.0 · cryptg
`cryptg` es obligatorio para descargas rápidas; el sync lo comprueba y lo instala.
