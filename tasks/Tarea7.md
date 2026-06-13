# Tarea 7 - Clasificador de URLs

Version objetivo: `v1.7.0`

## Objetivo

Implementar clasificacion inicial de URLs de Instagram.

## Archivo

```text
src/ig_orchestrator/input/url_classifier.py
```

## Reglas

```text
/stories/highlights/{id}/ => HIGHLIGHTS
/stories/{username}/ => STORY
/reel/{id}/ => REEL
/p/{id}/ con img_index => POST
/p/{id}/ sin img_index => REEL inicialmente
URL no Instagram => error
```

## Criterios de aceptacion

* Clasificar stories, highlights, reels y posts.
* Mantener `UNKNOWN` solo para casos permitidos por el dominio, no para URLs invalidas.
* Actualizar `CHANGELOG.md`.

## Pruebas minimas

```text
https://www.instagram.com/p/DZPjwEjitxx/?img_index=1 => POST
https://www.instagram.com/reel/ABC123xyz/ => REEL
https://www.instagram.com/p/DZPjwEjitxx/ => REEL inicialmente
https://www.instagram.com/stories/user_name/ => STORY
https://www.instagram.com/stories/highlights/17851330941375169/ => HIGHLIGHTS
https://example.com/foo => error
```
