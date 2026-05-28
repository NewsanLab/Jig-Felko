# Nota sobre el archivo `felko.py`

## ⚠️ Importante

En este repositorio, el archivo se llama **`felko.py`**.
Sin embargo, **en el entorno de producción debe ser renombrado a `yazaki.py`**.

## 📌 Motivo

El sistema en producción depende explícitamente del nombre `yazaki.py` para ejecutar o integrar este módulo.
Por esta razón, el cambio de nombre es obligatorio al momento de subirlo a produccion.

## 🧠 Consideraciones

* En desarrollo y en el repositorio se mantiene el nombre `felko.py` por claridad.
* En producción se utiliza `yazaki.py` por compatibilidad con el sistema existente.
* El contenido del archivo es el mismo; solo cambia el nombre.

## 🚫 No olvidar

* ❌ No ejecutar el sistema en producción con el nombre `felko.py`
* ❌ No subir cambios al repositorio con el nombre `yazaki.py`

---

Ante cualquier cambio en este comportamiento, actualizar este documento.
