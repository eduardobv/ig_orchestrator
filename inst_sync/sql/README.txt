Scripts SQL numerados (001_nombre.sql, 002_...). Cada uno se aplica una sola vez por instancia
(se apunta en estado.json) y antes se guarda una copia de la base en inst_sync\bkp.
Casi nunca hacen falta: las migraciones de esquema son automaticas al abrir la app.
