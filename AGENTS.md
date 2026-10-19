# Distribution builds

- Update the existing application at `dist/SonicForge` in place. Keep the installer at its existing path under `dist`.
- Do not create alternate distribution directories or duplicate application bundles for each change. Intermediate compilation files may stay under `build`.
- Remove obsolete distribution copies after verifying the canonical build. Preserve source files, models, build environments and compilation caches.
- Never terminate an open user session to replace a locked executable; wait until the application is closed.
