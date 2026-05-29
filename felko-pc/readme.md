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

# Requisitos del entorno

## 🐍 Python

* Python `3.13.12`

## 📚 Librerías requeridas

Instalar las siguientes librerías:

```bash
pip install eventlet
pip install pyvisa
pip install pyvisa-py
pip install pyserial
pip install python-socketio
pip install requests
pip install pythonnet
```

O bien:

```bash
pip install eventlet pyvisa pyvisa-py pyserial python-socketio requests pythonnet
```

---

# Drivers y dependencias adicionales

## 🔌 Driver CH340/CH341

Descargar e instalar:

https://www.wch-ic.com/downloads/ch341ser_exe.html

## 🧩 Visual C++ Redistributable for Visual Studio 2015

Descargar e instalar:

https://www.microsoft.com/es-es/download/details.aspx?id=48145

## ⚡ Controlador / IO Libraries Suite de Keysight

Descargar e instalar:

https://www.keysight.com/us/en/lib/software-detail/computer-software/io-libraries-suite-downloads-2175637.html

---

Ante cualquier cambio en este comportamiento, actualizar este documento.

