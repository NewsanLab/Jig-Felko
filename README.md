# Sistema de Testeo de Antenas Felko - Documentación

## Descripción General

Sistema de testeo automatizado para antenas automotrices (modelo ANTENAHILUX) que integra hardware embebido con análisis de señales RF. El sistema consta de dos componentes principales que se comunican vía USB CDC:

- **code.py**: Firmware para placa Archi (CircuitPython) - Control de hardware y adquisición de datos
- **felko.py**: Aplicación PC (Python) - Análisis RF, comunicación con analizador de redes y gestión de datos

## Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────┐
│                         INTERFAZ WEB                         │
│                    (Socket.IO Cliente)                       │
└─────────────────────┬───────────────────────────────────────┘
                      │ WebSocket (Puerto 4000)
┌─────────────────────▼───────────────────────────────────────┐
│                        PC (felko.py)                        │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ • Socket.IO Server                                     │ │
│  │ • Control de Analizador de Redes (PyVISA)             │ │
│  │ • Switch RF (mcl_RF_Switch_Controller)                │ │
│  │ • Procesamiento de señales FM/AM                      │ │
│  │ • POST a servidor de trazabilidad                     │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────┬───────────────────────────────────────┘
                      │ USB CDC Serial (115200 baud)
┌─────────────────────▼───────────────────────────────────────┐
│                    ARCHI (code.py)                           │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ • Escáner QR (GM65 - UART 9600)                        │ │
│  │ • Sensor INA260 (I²C) - Voltaje/Corriente             │ │
│  │ • Matriz LED NeoPixel 8x8                              │ │
│  │ • Buzzer para alertas                                  │ │
│  │ • Control de MOSFET y prensa neumática                 │ │
│  │ • Botón de inicio y sensor de barrera                  │ │
│  │ • Botón de emergencia (análogo GP27)                   │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│              Analizador de Redes (Keysight)                  │
│         USB0::0x0957::0x1309::MY49304399::0::INSTR           │
└─────────────────────────────────────────────────────────────┘
```

## 1. Firmware Archi - code.py

### Hardware Requerido

#### Comunicación
- **Escáner QR GM65**: UART en GP4 (TX), GP5 (RX), 9600 baud
- **USB CDC**: Comunicación serial con PC a 115200 baud

#### Sensores y Actuadores
- **INA260**: Sensor I²C de corriente/voltaje en GP17 (SCL), GP16 (SDA)
- **Matriz NeoPixel**: 8x8 LEDs RGB (64 píxeles, brillo 10%)
- **Buzzer**: Señal audible en `board.BUZZER`
- **MOSFET**: Control de alimentación en GP14
- **Prensa**: Actuador neumático en GP8
- **LED Inicio**: Indicador de estado en GP28
- **Barrera**: Sensor de seguridad en GP26 (entrada digital)
- **Botón Inicio**: GP18 con debouncer
- **Botón Emergencia**: Entrada analógica en GP27 (threshold > 10000)
- **Botón A**: `board.A` (función legacy)

### Flujo de Operación

#### 1. Inicialización
```
- Configurar hardware (I²C, UART, GPIO)
- Matriz LED en BLANCO (sistema listo)
- Habilitar LED de inicio
- Lanzar tareas asíncronas (asyncio)
```

#### 2. Escaneo QR
```
Usuario presiona botón de inicio
  └─> Verificar barrera (debe estar abierta)
      └─> Si waiting_reset==True: reiniciar (matriz BLANCO)
      └─> Si waiting_reset==False: iniciar escaneo
          ├─> Enviar SOFT_TRIG_ON al GM65
          ├─> Matriz LED → AZUL (escaneando)
          └─> Timeout 5 segundos
              ├─> QR detectado: procesar código
              └─> Timeout: volver a BLANCO
```

#### 3. Validación y Test
```
QR recibido
  └─> Enviar a PC: "#<qr_code>\n"
      └─> PC valida contra base de datos
          ├─> OK: PC envía "FM-START"
          │   └─> Iniciar test FM/AM
          └─> FAIL: PC envía "NG-DB"
              └─> Matriz ROJO + buzzer 1.5s
```

### Estados de la Matriz LED

| Color | Código RGB | Significado |
|-------|------------|-------------|
| BLANCO | 0xFFFFFF | Sistema listo para escanear |
| AZUL | 0x0000FF | Escaneando QR |
| AMARILLO | 0xFFFF00 | Test en progreso |
| VERDE | 0x33CC00 | Test OK |
| ROJO | 0xFF0000 | Fallo o emergencia |

### Protocolo de Test FM

```python
1. PC envía: "FM-START"
   └─> Archi responde:
       ├─> Matriz LED → AMARILLO
       ├─> Activar MOSFET (alimentación DUT)
       ├─> Activar prensa (1.25s delay)
       └─> Loop de monitoreo:
           ├─> Leer voltaje INA260 (rango: 7-15.99V)
           ├─> Leer corriente INA260 (límite: <120mA)
           ├─> Si fuera de rango: validacion=0
           └─> Esperar comando PC

2. PC envía resultado:
   ├─> "FM-0" (OK): 
   │   ├─> Si validacion==1: Matriz VERDE, enviar "FM-END-C"
   │   └─> Si validacion==0: Matriz ROJO, enviar "FM-END-E, <current>"
   │
   └─> "FM-2" o "FM-3" (FAIL):
       └─> Matriz ROJO, enviar "FM-END-D", buzzer 1.5s
```

### Protocolo de Test AM

```python
1. PC envía: "AM-START"
   └─> Archi responde:
       ├─> Enviar "AM-RUN"
       ├─> Matriz LED → AMARILLO
       └─> Loop de monitoreo (igual que FM):
           ├─> Validar voltaje: 7-15.99V
           ├─> Validar corriente: <120mA
           └─> Esperar comando PC

2. PC envía resultado:
   ├─> "AM-0" (OK):
   │   ├─> Si validacion==1: Matriz VERDE, enviar "AM-END-C"
   │   └─> Si validacion==0: Matriz ROJO, enviar "AM-END-E, <current>"
   │
   └─> "AM-1" (FAIL):
       └─> Matriz ROJO, enviar "AM-END-D", buzzer 1.5s

3. Finalización:
   ├─> Desactivar prensa (delay 1.3s)
   ├─> Habilitar LED de inicio
   └─> waiting_reset = True (esperar reset del operador)
```

### Tarea de Emergencia (Asíncrona)

```python
Loop infinito (10ms):
  └─> Leer botón emergencia (GP27)
      └─> Si valor > 10000:
          ├─> Matriz LED → ROJO
          ├─> Buzzer 440Hz, 0.3s
          └─> Delay 0.2s
```

### Límites de Seguridad

| Parámetro | Mínimo | Máximo | Acción si Viola |
|-----------|--------|--------|-----------------|
| Voltaje DUT | 7.0 V | 15.99 V | validacion=0, enviar corriente en END-E |
| Corriente DUT | - | 120 mA | validacion=0, enviar corriente en END-E |
| Timeout escaneo | - | 5 s | Cancelar escaneo, volver a BLANCO |

---

## 2. Aplicación PC - felko.py

### Dependencias Principales

```python
pyvisa                  # Control de analizador de redes
pyserial                # Comunicación USB CDC con Archi
python-socketio         # WebSocket server para frontend
eventlet                # Servidor WSGI asíncrono
numpy                   # Procesamiento de datos
requests                # POST a servidor de trazabilidad
pythonnet (clr)         # Interfaz .NET para switch RF
```

### Arquitectura de Comunicación

#### 1. Socket.IO Server (Puerto 4000)

```python
Eventos manejados:
├─> connect: Cliente frontend conectado
├─> start-test: Recibe lista de QRs válidos desde frontend
│   └─> Activa validate_code_db = True
│   └─> Almacena json_data_db
└─> Emite:
    └─> test-result: Resultados de test al frontend
```

#### 2. Serial USB CDC (115200 baud)

```python
Conexión con Archi:
├─> VID: 11914 (0x2E8A)
└─> PID: 4163 (0x1043)

Auto-reconexión:
└─> Si desconectado: buscar puerto cada 1s
```

#### 3. PyVISA - Analizador de Redes

```python
Resource: 'USB0::0x0957::0x1309::MY49304399::0::INSTR'
Timeout: 10000 ms

Estados de configuración:
├─> FM: Carga "FM_ganancia_configurada.sta"
└─> AM: Carga "AM_gain20.sta"
```

#### 4. Switch RF (mcl_RF_Switch_Controller)

```python
Librería .NET: mcl_RF_Switch_Controller_NET45.dll
Configuración:
├─> sw.Set_Switch("A", 0)  # Lado FM
└─> sw.Set_Switch("B", 0)
```

### Flujo de Operación Principal

#### 1. Bucle de Conexión

```python
while True:
    # 1. Verificar conexión serial Archi
    if not ser.is_open:
        buscar_puerto(VID=11914, PID=4163)
        conectar_serial(115200 baud)
    
    # 2. Verificar conexión analizador
    if not network_analyzer:
        conectar_visa('USB0::0x0957::0x1309::...')
        query('*IDN?')  # Validar respuesta
    
    # 3. Heartbeat
    else:
        network_analyzer.query('*OPC?')
```

#### 2. Recepción de QR

```python
Archi envía: "#<qr_code>\n"
  └─> PC recibe en buffer
      └─> Si buffer.startswith("#"):
          ├─> Extraer qr_code = buffer[1:]
          ├─> Validar contra json_data_db
          │   ├─> Si código válido: validacion=1
          │   └─> Si código inválido: validacion=0
          │
          └─> Si código == golden_board:
              └─> Ejecutar test con golden sample
```

### Protocolo de Test FM

#### Parámetros de Barrido

```python
POWER_START_DBM = -14.5
POWER_STOP_DBM = -9.7
POWER_STEP_DBM = 0.2

Niveles de potencia:
power_levels = [-14.5, -14.3, -14.1, ..., -9.9, -9.7] dBm
Total: ~25 puntos de medición
```

#### Secuencia de Test FM

```python
1. Enviar a Archi: "FM-START"
   
2. Loop de mediciones (para cada power_level):
   └─> Configurar analizador:
       ├─> Cargar estado "FM_ganancia_configurada.sta"
       ├─> Establecer potencia: f'SOURce1:POWer:LEVel:IMMediate:AMPLitude {power_dbm}'
       ├─> Iniciar barrido: 'INITiate:IMMediate'
       ├─> Esperar OPC
       └─> Guardar datos: 'MMEMory:STORe:FDATa "fm_lectura.csv"'
   
   └─> Leer datos binarios:
       ├─> data = query_binary_values(':MMEMory:TRANsfer? "FM_LECTURA.CSV"')
       └─> Guardar en: "C:\...\fm_comparacion.csv"
   
   └─> Procesar CSV:
       ├─> Leer frecuencias: fm_freq_nuevo (MHz)
       ├─> Leer magnitudes: fm_mag_nuevo (dB)
       └─> Encontrar ganancia en rango 88-99 MHz:
           ├─> gain_real = max(magnitudes[88-99 MHz])
           ├─> gain_ideal = 87.7 + (power_dbm + 14.0) / 4.8 * 16.7
           ├─> gain_dif = abs(gain_real - gain_ideal)
           └─> Si gain_dif < 1.0:
               ├─> validacionAGC = 1
               ├─> Guardar (entrada, salida) para reporte
               └─> Break loop (ganancia encontrada)

3. Enviar resultado a Archi:
   └─> f"FM-{validacionAGC}\n"
       ├─> validacionAGC=1 → "FM-1" (test exitoso)
       └─> validacionAGC=0 → "FM-0" (fallo)

4. Esperar confirmación Archi:
   ├─> "FM-END-C": OK completo
   ├─> "FM-END-D": Fallo RF
   └─> "FM-END-E, <current>": Fallo corriente
```

### Protocolo de Test AM

```python
1. Enviar a Archi: "AM-START"
   
2. Esperar: "AM-RUN" (confirmación de Archi)
   
3. Configurar analizador:
   ├─> Cargar estado "AM_gain20.sta"
   ├─> Delay 2 segundos (estabilización)
   ├─> Guardar datos: 'MMEMory:STORe:FDATa "am_lectura.csv"'
   └─> Transferir: query_binary_values(':MMEMory:TRANsfer? "AM_LECTURA.CSV"')
   
4. Procesar CSV:
   ├─> Leer frecuencias: am_freq_nuevo (kHz)
   ├─> Leer magnitudes: am_mag_nuevo (dB)
   └─> Buscar ganancia en 900-1400 kHz:
       ├─> gain_max = max(magnitudes[900-1400 kHz])
       └─> Si gain_max > 0:
           ├─> validacion = 1 (AM OK)
           └─> Else: validacion = 0

5. Enviar resultado a Archi:
   └─> f"AM-{validacion}\n"

6. Esperar confirmación Archi:
   ├─> "AM-END-C": OK completo
   ├─> "AM-END-D": Fallo RF
   └─> "AM-END-E, <current>": Fallo corriente
```

### Estructura de Datos de Medición

```python
medicion_data = {
    "id_cama": 1,
    "fm": {
        "Frequency_MHz": [88.0, 88.5, ..., 108.0],  # Lista de frecuencias
        "Data1": [65.234, 67.891, ..., 55.123]      # Magnitudes en dB
    },
    "am": {
        "Frequency_MHz": [530.0, 540.0, ..., 1710.0],
        "Data1": [12.456, 15.789, ..., 8.234]
    },
    "agc": {
        "entrada": -12.5,    # dBm de entrada para AGC correcto
        "salida": 87.7       # Ganancia obtenida
    },
    "modos": ["MODOFM-AGC", "MODO AM"],
    "estado": ["OK-FM", "OK-AM"],  # o ["FALLA-FM"], ["FALLA-AM"], ["FALLA-CORRIENTE-FM"]
    "corriente": []  # o ["corriente-fm: 150.5"] si hay falla
}
```

### POST a Servidor de Trazabilidad

```python
URL: '/insertar_automotriz'

Payload:
{
    "codigo": "<qr_code>",
    "testeo": "<medicion_data en JSON string>",
    "estado": 1,
    "modelo": "ANTENAHILUX"
}
```

### Emisión Socket.IO

```python
server_data = {
    "cama": 1,
    "code": "<qr_code>",
    "statusTraza": True,          # Siempre True si llegó a este punto
    "statusJig": True/False,      # True si {"OK-FM", "OK-AM"} ambos presentes
    "message": ["OK-FM", "OK-AM"] # o estados de falla
}

sio.emit("test-result", [server_data])
```

---

## Protocolo de Comunicación Serial

### Mensajes Archi → PC

| Mensaje | Descripción | Acción PC |
|---------|-------------|-----------|
| `#<qr_code>\n` | Código QR escaneado | Validar en BD, iniciar test |
| `AM-RUN\n` | Archi listo para test AM | Continuar secuencia AM |
| `FM-END-C\n` | FM OK | Guardar estado "OK-FM" |
| `FM-END-D\n` | FM fallo | Guardar estado "FALLA-FM" |
| `FM-END-E, <mA>\n` | FM fallo corriente | Guardar estado "FALLA-CORRIENTE-FM" |
| `AM-END-C\n` | AM OK | Guardar estado "OK-AM", enviar reporte |
| `AM-END-D\n` | AM fallo | Guardar estado "FALLA-AM", enviar reporte |
| `AM-END-E, <mA>\n` | AM fallo corriente | Guardar estado "FALLA-CORRIENTE-AM", enviar reporte |

### Mensajes PC → Archi

| Mensaje | Descripción | Acción Archi |
|---------|-------------|--------------|
| `FM-START\n` | Iniciar test FM | Activar MOSFET/prensa, monitorear corriente |
| `FM-0\n` | FM resultado: FAIL AGC | Evaluar corriente local, enviar END |
| `FM-1\n` | FM resultado: OK AGC | Evaluar corriente local, enviar END |
| `FM-2\n` | FM resultado: FAIL general | Matriz ROJO, enviar FM-END-D |
| `FM-3\n` | FM resultado: FAIL general | Matriz ROJO, enviar FM-END-D |
| `AM-START\n` | Iniciar test AM | Enviar AM-RUN, monitorear corriente |
| `AM-0\n` | AM resultado: OK | Evaluar corriente local, enviar END |
| `AM-1\n` | AM resultado: FAIL | Matriz ROJO, enviar AM-END-D |
| `NG-DB\n` | QR no válido en BD | Matriz ROJO, buzzer, esperar reset |

---

## Configuración de Archivos

### Archivos de Estado del Analizador

Ubicación: Memoria interna del analizador de redes

```
FM_ganancia_configurada.sta  → Configuración para barrido FM (88-108 MHz)
AM_gain20.sta                → Configuración para barrido AM (530-1710 kHz)
```

### Archivos CSV Temporales (PC)

```
C:\Users\Traza-Lab\AppData\Local\Programs\trazabilidad-newsan\bin\
├─> fm_comparacion.csv   # Datos FM por cada nivel de potencia
└─> am_comparacion.csv   # Datos AM (único barrido)
```

### Estructura CSV del Analizador

```csv
Frequency (MHz/kHz), <trace_name>
88.0, 65.234
88.5, 67.891
...
```
---

## Manejo de Errores

### Archi (code.py)

| Condición | Acción |
|-----------|--------|
| Timeout escaneo QR (5s) | Cancelar escaneo, matriz BLANCO |
| Voltaje fuera de rango | `validacion=0`, enviar corriente en END-E |
| Corriente > 120mA | `validacion=0`, enviar corriente en END-E |
| Botón emergencia activado | Matriz ROJO, buzzer continuo |
| Barrera cerrada | No permitir inicio de escaneo |
| Error decodificación QR | Imprimir error, resetear buffer |

### PC (felko.py)

| Condición | Acción |
|-----------|--------|
| Serial desconectado | Bucle de reconexión cada 1s |
| Analizador desconectado | Bucle de reconexión (PyVISA) |
| Código QR no en BD | Enviar `NG-DB` a Archi |
| Error POST trazabilidad | Imprimir error, continuar operación |
| Error query analizador | Desconectar, intentar reconexión |
