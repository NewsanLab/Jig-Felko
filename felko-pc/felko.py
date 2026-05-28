import eventlet
from eventlet import wsgi
eventlet.monkey_patch()
import os   
os.environ["EVENTLET_NO_GREENDNS"] = "yes"
from datetime import datetime
from simplification.cutil import simplify_coords #añadido para RDP

import numpy as np
import pyvisa
import time
import csv
import serial
import serial.tools.list_ports
import requests
import sys
import threading
import json 
import socketio
import clr
clr.AddReference(r"C:\Users\Traza-Lab\AppData\Local\Programs\trazabilidad-newsan\bin\mcl_RF_Switch_Controller_NET45.dll")
from mcl_RF_Switch_Controller_NET45 import USB_RF_SwitchBox

base_dir = os.path.dirname(os.path.abspath(__file__))
route_folder = os.path.join(base_dir, "datos")

os.makedirs(route_folder, exist_ok=True)

URL = 'http://arushap02:5000/insertar_automotriz'
API_KEY = "uDnNvsMOGW0MsE6OQrsyKF04Sdey0TQKT1albqCEEms"
json_data_db=[]

sio = socketio.Server(cors_allowed_origins="*")
app = socketio.WSGIApp(sio)

@sio.event
def connect(sid, environ):
    print("cliente conectado")


@sio.on("start-test") 
def start_test(sid, data): 
    """
    Manejador del evento 'start-test'.
    Recibe la lista de códigos QR escaneados desde el frontend y activa la bandera
    de validación para comenzar el ciclo de prueba.
    
    Args:
        sid: ID de la sesión del socket.
        data: JSON string con la lista de objetos de los QRs.
    """
    global validate_code_db, json_data_db
    validate_code_db = True
    print(json_data_db)
    json_data_db = json.loads(data)
    print(json_data_db)
    
def socket_func():
    """
    Función que ejecuta el servidor WSGI con Socket.IO en un hilo separado.
    Escucha en el puerto 4000.
    """
    wsgi.server(eventlet.listen(('', 4000)), app, log=sys.stdout)
    
socket_thread = threading.Thread(target=socket_func, daemon=True)
socket_thread.start()

		
def simplificar_curva(freq_list, data_list):
    coords = list(zip(freq_list, [float(v) for v in data_list]))
    umbral = 0.19  # MHz
    coords_critico = [(f, d) for f, d in coords if f < umbral]
    coords_estable = [(f, d) for f, d in coords if f >= umbral]
    critico_simpl = simplify_coords(coords_critico, epsilon=0.002) if coords_critico else []
    estable_simpl = simplify_coords(coords_estable, epsilon=0.015) if coords_estable else []
    curva_final = sorted(critico_simpl + estable_simpl, key=lambda p: p[0])
    return {
        "Frequency_MHz": [round(f, 6) for f, _ in curva_final],
        "Data1":         [round(d, 6) for _, d in curva_final]
    }

def post_data_testing(data):
    global URL, API_KEY
    try:
        response = requests.post(
          URL,
          json=data,
          headers={
            'arushap02-api-key': API_KEY,             
            'Content-Type': 'application/json' 
          },
          timeout=5 #agregado timeout para evitar bloqueos prolongados en caso de problemas de red
        )
        print(f"POST enviado: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Error al enviar POST: {e}")

def find_serial_port(vendor_id, product_id):
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if (port.vid == vendor_id) and (port.pid == product_id):
            return port.device
    return None

def connect_serial(port, baudrate=115200, timeout=1):
    try:
        ser = serial.Serial(port, baudrate, timeout=timeout)
        print(f"CONECTADO: {port}")
        return ser
    except serial.SerialException as e:
        print(f"Error al conectar con {port}: {e}")
        return None 

def main():
    global qr_code, validate_code_db, json_data_db

    # variables en comun AM y FM
    VENDOR_ID = 11914
    PRODUCT_ID = 4163
    sw = USB_RF_SwitchBox()
    sw.Connect()
    network_analyzer = None
    rm = pyvisa.ResourceManager()
    qr_code = ""
    golden_board = 'VA004901250413000000358'
    ser = None
    buffer = ''

    # FM
    POWER_START_DBM = -14.5
    POWER_STOP_DBM = -9.7
    POWER_STEP_DBM = 0.2
    power_levels_dbm = np.arange(POWER_START_DBM, POWER_STOP_DBM + POWER_STEP_DBM, POWER_STEP_DBM)
    ser = None
    gain_str = ''
    gain_real = ''
    gain_float = 0
    gain_ideal = 0
    gain_dif = 0
    validacionAGC = 0

    # para usar switch lado FM
    sw.Set_Switch("A",0)
    sw.Set_Switch("B",0)
    end_test_fm = False
    end_test_am = False
    validate_code_db = False
    status = [] # para agregar los estados de test de fm, am
    current_fail = [] # para agregar falla de corriente FM o AM

    while(True):
        # Conexion serial con Archi
        if ser is None or not ser.is_open:
            port = find_serial_port(VENDOR_ID, PRODUCT_ID)
            if port:
                ser = connect_serial(port, 115200, timeout=0.1)
            else:
                print("DESCONECTADO: Buscando puerto USB...")
            time.sleep(1)

        # Conexion con el analizador de redes
        if network_analyzer is None:
            try:
                network_analyzer = rm.open_resource('USB0::0x0957::0x1309::MY49304399::0::INSTR')
                network_analyzer.timeout = 10000
                idn = network_analyzer.query("*IDN?")
                print(f"CONECTADO: Equipo responde [{idn.strip()}]")

            except Exception as e:
                if "VI_ERROR_RSRC_NFOUND" in str(e):
                    print("DESCONECTADO: Equipo no encontrado")
                else:
                    print(f"DESCONECTADO: PyVISA error -> {e}")
                network_analyzer = None

        else:
            try:
                network_analyzer.query("*OPC?")  # solo para verificar que sigue conectado
            except Exception as e:
                print(f"DESCONECTADO: PyVISA error -> {e}")
                network_analyzer = None

        try:
            if ser and ser.is_open:
                if ser.in_waiting > 0:
                    buffer = ser.readline().decode('utf-8').strip()
                    print("Archi: ", buffer)
                    if buffer.startswith("#"):
                        qr_code = buffer[1:]
                        server_data = {
                             "cama": 1,
                             "code": qr_code,
                             "statusTraza": False,
                             "statusJig": False,
                             "message": ""
                        }
                        sio.emit("start-test", [server_data])
                        while not validate_code_db:
                          time.sleep(0.1)
                        validate_code_db = False
                        #print(json_data_db)
                        status = []
                        current_fail = []
                        if (json_data_db[0]["statusTraza"]):
                            end_test_fm = False
                            end_test_am = False
                            ser.write(b"FM-START\n")
                            # para usar switch lado FM
                            sw.Set_Switch("A",0)
                            sw.Set_Switch("B",0)
                            time.sleep(0.5)
                            if (qr_code!= golden_board):
                                buffer = ''
                                network_analyzer.write('MMEMory:LOAD:STATe "FM_gain20.sta"')
                                network_analyzer.query('*OPC?')
                                time.sleep(0.5)
                                network_analyzer.write('MMEMory:STORe:FDATa "fm_lectura.csv"')
                                fm_name = "FM_LECTURA.CSV"
                                data_fm = network_analyzer.query_binary_values(f':MMEMory:TRANsfer? "{fm_name}"', datatype='B')
                                # Archivo temporal FM para lectura interna (comparacion)
                                fm_file = qr_code + "_fm.csv"
                                with open(fm_file, 'wb') as fm:
                                    fm.write(bytearray(data_fm))
                                fm.close()
                                
                                validacion = 0
                                # Colocar marcador en 98MHz
                                network_analyzer.write(':CALC1:MARK1:X 98E6')
                                network_analyzer.query('*OPC?')
                                network_analyzer.write(f':SOUR1:POW -14.5')
                                time.sleep(0.05)
                                network_analyzer.query('*OPC?')
                                gain_str = network_analyzer.query(':CALC1:MARK1:Y?')
                                gain_real = gain_str.split(",")
                                gain_ideal = float(gain_real[0])
                                validacionAGC = 0

                                # --- AGC: recolectar datos en memoria ---
                                agc_entrada = []
                                agc_salida = []
                                for power in power_levels_dbm:
                                    network_analyzer.write(f':SOUR1:POW {power}')
                                    time.sleep(0.05)
                                    network_analyzer.query('*OPC?')
                                    gain_str = network_analyzer.query(':CALC1:MARK1:Y?')
                                    gain_real = gain_str.split(",")
                                    gain_float = float(gain_real[0])
                                    agc_entrada.append(round(float(power), 6))
                                    agc_salida.append(round(gain_float, 6))
                                    gain_dif = gain_ideal - gain_float
                                    if (0.2 < gain_dif < 0.4):
                                        validacionAGC = 1
                                if validacionAGC == 0:
                                    validacion = 3
                                
                                fm_mag_nuevo = []
                                fm_freq_nuevo = []
                                fm_mag_orig = []
                                fm_minimo = 0
                                flotante = 0
                                with open(fm_file) as fm_nuevo:
                                    heading = next(fm_nuevo)
                                    heading = next(fm_nuevo)
                                    heading = next(fm_nuevo)
                                    reader_obj = csv.reader(fm_nuevo)
                                    for row in reader_obj:
                                        fm_freq_nuevo.append(round(float(row[0]) / 1e6, 6))  # Hz -> MHz
                                        fm_mag_nuevo.append(row[1])
                                os.remove(fm_file)
                                with open(r"C:\Users\Traza-Lab\AppData\Local\Programs\trazabilidad-newsan\bin\fm_comparacion.csv") as fm_original:
                                    heading = next(fm_original)
                                    heading = next(fm_original)
                                    heading = next(fm_original)
                                    reader_obj = csv.reader(fm_original)
                                    for row in reader_obj:
                                        fm_mag_orig.append(row[1])
                                        flotante = float(row[1])
                                        if flotante < fm_minimo:
                                            fm_minimo = flotante
                                fm_index = 0
                                fm_tolerance = 3
                                for line in fm_mag_orig:
                                    value = float(line) + abs(fm_minimo)
                                    compara = float(fm_mag_nuevo[fm_index]) + abs(fm_minimo)
                                    lower = value - fm_tolerance
                                    upper = value + fm_tolerance
                                    fm_index = fm_index + 1
                                    if not (lower <= compara <= upper):
                                        validacion = 2
            
                                ser.write(f"FM-{validacion}\n".encode())
                            if (qr_code == golden_board):
                                buffer = ''
                                network_analyzer.write('MMEMory:LOAD:STATe "FM_gain20.sta"')
                                network_analyzer.query('*OPC?')
                                time.sleep(0.5)
                                network_analyzer.write('MMEMory:STORe:FDATa "fm_lectura.csv"')
                                fm_name = "FM_LECTURA.CSV"
                                data_fm = network_analyzer.query_binary_values(f':MMEMory:TRANsfer? "{fm_name}"', datatype='B')
                                fm_file = r"C:\Users\Traza-Lab\AppData\Local\Programs\trazabilidad-newsan\bin\fm_comparacion.csv"
                                with open(fm_file, 'wb') as fm:
                                    fm.write(bytearray(data_fm))
                                fm.close()
                                
                                validacion = 0
                                ser.write(f"FM-{validacion}\n".encode())
                            while not end_test_fm:
                                if ser.in_waiting > 0:
                                    buffer = ser.readline().decode('utf-8').strip()
                                    print("Archi: ",buffer)
                                if buffer == "FM-END-C":
                                    buffer = ''
                                    print("OK FM\n")
                                    status.append("OK-FM")
                                    ser.write(b"AM-START\n")
                                if buffer == "FM-END-D":
                                    buffer = ''
                                    if validacion == 2:
                                        print("Falla FM\n")
                                        status.append("FALLA-FM")
                                    elif validacion == 3:
                                        print("Falla AGC\n")
                                        status.append("FALLA-AGC")
                                    ser.write(b"AM-START\n")
                                if buffer.startswith("FM-END-E"):
                                    dato_array = buffer.split(",")
                                    current = dato_array[1]
                                    buffer = ''
                                    status.append("FALLA-CORRIENTE-FM")
                                    current_fail.append(f"corriente-fm: {current}")
                                    print ("Falla corriente fm\n")
                                    ser.write(b"AM-START\n")
                                if buffer == "AM-RUN":
                                    # para usar switch lado AM
                                    sw.Set_Switch("A",1)
                                    sw.Set_Switch("B",1)
                                    if (qr_code != golden_board):
                                        buffer = ''
                                        network_analyzer.write('MMEMory:LOAD:STATe "AM_gain20.sta"') # carga la cfg de medicion para AM
                                        network_analyzer.query('*OPC?') # espera a que termine de cargar la cfg
                                        time.sleep(2)
                                        network_analyzer.write('MMEMory:STORe:FDATa "am_lectura.csv"') # ordena al analizador que guarde la medicion en un archivo csv

                                        am_name = "AM_LECTURA.CSV"
                                        data_am = network_analyzer.query_binary_values(f':MMEMory:TRANsfer? "{am_name}"', datatype='B') # transfiere el archivo csv del analizador a la PC
                                        am_file = qr_code + "_am.csv"
                                        # Guarda el archivo csv transferido en la PC con un nombre basado en el código QR escaneado
                                        with open(am_file, 'wb') as am:
                                            am.write(bytearray(data_am))

                                        am.close()

                                        am_mag_nuevo = []
                                        am_freq_nuevo = []
                                        am_mag_orig = []
                                        am_minimo = 0
                                        flotante = 0
                                        validacion = 0
                                        with open(am_file) as am_nuevo:
                                            heading = next(am_nuevo)
                                            heading = next(am_nuevo)
                                            heading = next(am_nuevo)
                                            reader_obj = csv.reader(am_nuevo)
                                            for row in reader_obj:
                                                am_freq_nuevo.append(round(float(row[0]) / 1e6, 6))  # Hz -> MHz
                                                am_mag_nuevo.append(row[1])
                                        os.remove(am_file)
                                        with open(r"C:\Users\Traza-Lab\AppData\Local\Programs\trazabilidad-newsan\bin\am_comparacion.csv") as am_original:
                                            heading = next(am_original)
                                            heading = next(am_original)
                                            heading = next(am_original)
                                            reader_obj = csv.reader(am_original)
                                            for row in reader_obj:
                                                am_mag_orig.append(row[1])
                                                flotante = float(row[1])
                                                if flotante < am_minimo:
                                                    am_minimo = flotante
                                        am_original.close()
                                        am_tolerance = 2
                                        am_index = 0
                                        for line in am_mag_orig:
                                            value = float(line) + abs(am_minimo)
                                            compara = float(am_mag_nuevo[am_index]) + abs(am_minimo)
                                            lower = value - am_tolerance
                                            upper = value + am_tolerance
                                            am_index = am_index + 1
                                            if not (lower <= compara <= upper):
                                                validacion = 1
                                        ser.write(f"AM-{validacion}\n".encode())

                                        # --- Construir CSV unificado (FM | AGC | AM) ---
                                        #unified_file = "datos/" + qr_code + "_medicion.csv"
                                        unified_file = os.path.join(route_folder, qr_code + "_medicion.csv")
                                        fm_data1 = [round(float(v), 6) for v in fm_mag_nuevo]
                                        am_data1 = [round(float(v), 6) for v in am_mag_nuevo]
                                        max_rows = max(len(fm_freq_nuevo), len(agc_entrada), len(am_freq_nuevo))
                                        with open(unified_file, 'w', newline='') as uf:
                                            writer = csv.writer(uf)
                                            writer.writerow([
                                                'FM_Frequency_MHz', 'FM_Data1',
                                                'AGC_Entrada', 'AGC_Salida',
                                                'AM_Frequency_MHz', 'AM_Data1'
                                            ])
                                            for i in range(max_rows):
                                                row = [
                                                    fm_freq_nuevo[i] if i < len(fm_freq_nuevo) else '',
                                                    fm_data1[i]      if i < len(fm_data1)      else '',
                                                    agc_entrada[i]   if i < len(agc_entrada)   else '',
                                                    agc_salida[i]    if i < len(agc_salida)     else '',
                                                    am_freq_nuevo[i] if i < len(am_freq_nuevo)  else '',
                                                    am_data1[i]      if i < len(am_data1)       else '',
                                                ]
                                                writer.writerow(row)
                                    if (qr_code == golden_board):
                                        qr_code = buffer[1:]
                                        buffer = ''
                                        validacion = 0
                                        network_analyzer.write('MMEMory:LOAD:STATe "AM_gain20.sta"')
                                        network_analyzer.query('*OPC?')
                                        time.sleep(2)
                                        network_analyzer.write('MMEMory:STORe:FDATa "am_lectura.csv"')
                                        am_name = "AM_LECTURA.CSV"
                                        data_am = network_analyzer.query_binary_values(f':MMEMory:TRANsfer? "{am_name}"', datatype='B')
                                        am_file = r"C:\Users\Traza-Lab\AppData\Local\Programs\trazabilidad-newsan\bin\am_comparacion.csv"
                                        with open(am_file, 'wb') as am:
                                            am.write(bytearray(data_am))
                                        am.close()
                                        ser.write(f"AM-{validacion}\n".encode())
                                    while not end_test_am:
                                        if ser.in_waiting > 0:
                                            buffer = ser.readline().decode('utf-8').strip()
                                        if buffer == "AM-END-C":
                                            buffer = ''
                                            status.append("OK-AM")
                                            print("OK AM\n")
                                            end_test_am = True
                                            end_test_fm = True
                                            #Realizamos RDP a las curvas FM y AM para reducir puntos y peso
                                            fm_simplificado = simplificar_curva(fm_freq_nuevo, fm_mag_nuevo)
                                            am_simplificado = simplificar_curva(am_freq_nuevo, am_mag_nuevo)
                                            medicion_data = {
                                              "id_cama": 1,
                                              "fm": fm_simplificado,
                                              "am": am_simplificado,
                                              "agc": {
                                                "entrada": agc_entrada,
                                                "salida": agc_salida
                                              },
                                              "modos": ["MODOFM-AGC", "MODO AM"],
                                              "estado": status,
                                              "corriente": current_fail
                                            }
                                            data_json ={
                                                "codigo": qr_code,
                                                "testeo": json.dumps(medicion_data),
                                                "estado": 1 if {"OK-FM", "OK-AM"}.issubset(status) else 0,
                                                "modelo": "FELKO"
                                            }
                                            #print(data_json)
                                            #post_data_testing(data_json)
                                            threading.Thread(target=post_data_testing, args=(data_json,), daemon=True).start() #agregado threading para evitar bloqueos en el envío de datos a la API                                            

                                            server_data = {
                                                 "cama": 1,
                                                 "code": qr_code,
                                                 "statusTraza": True,
                                                 "statusJig": {"OK-FM", "OK-AM"}.issubset(status),
                                                 "message": status
                                            }
                                            sio.emit("test-result", [server_data])
                                        if buffer == "AM-END-D":
                                            buffer = ''
                                            if validacion == 1:
                                                status.append("FALLA-AM")
                                                print("Falla AM\n")
                                                fm_simplificado = simplificar_curva(fm_freq_nuevo, fm_mag_nuevo)
                                                am_simplificado = simplificar_curva(am_freq_nuevo, am_mag_nuevo)                                                
                                                medicion_data = {
                                                  "id_cama": 1,
                                                  "fm": fm_simplificado,
                                                  "am": am_simplificado,
                                                  "agc": {
                                                      "entrada": agc_entrada,
                                                      "salida": agc_salida
                                                  },
                                                  "modos": ["MODOFM-AGC", "MODO AM"],
                                                  "estado": status,
                                                  "corriente": current_fail
                                                }
                                                data_json = {
                                                    "codigo": qr_code,
                                                    "testeo": json.dumps(medicion_data),
                                                    "estado":  1 if {"OK-FM", "OK-AM"}.issubset(status) else 0,
                                                    "modelo": "FELKO"
                                                }
                                                #print(data_json)
                                                #post_data_testing(data_json)
                                                threading.Thread(target=post_data_testing, args=(data_json,), daemon=True).start()
                                                server_data = {
                                                     "cama": 1,
                                                     "code": qr_code,
                                                     "statusTraza": True,
                                                     "statusJig": False,
                                                     "message": status
                                                }
                                                sio.emit("test-result", [server_data])
                                            end_test_am = True
                                            end_test_fm = True 
                                        if buffer.startswith("AM-END-E"):
                                            buffer = ''
                                            status.append("FALLA-CORRIENTE-AM")
                                            current_fail.append(f"corriente-am: {current}")
                                            dato_array = buffer.split(",")
                                            current = dato_array[1]
                                            print("Falla corriente am\n")
                                            end_test_am = True
                                            end_test_fm = True
                                            fm_simplificado = simplificar_curva(fm_freq_nuevo, fm_mag_nuevo)
                                            am_simplificado = simplificar_curva(am_freq_nuevo, am_mag_nuevo)
                                            medicion_data = {
                                                "id_cama": 1,
                                                "fm": fm_simplificado,
                                                "am": am_simplificado,
                                                "agc": {
                                                    "entrada": agc_entrada,
                                                    "salida": agc_salida
                                                },
                                                "modos": ["MODOFM-AGC", "MODO AM"],
                                                "estado": status,
                                                "corriente": current_fail
                                            }
                                            data_json={
                                                "codigo": qr_code,
                                                "testeo": json.dumps(medicion_data),
                                                "estado": 1 if {"OK-FM", "OK-AM"}.issubset(status) else 0,
                                                "modelo": "FELKO"
                                            }
                                            #print(data_json)
                                            #post_data_testing(data_json)
                                            threading.Thread(target=post_data_testing, args=(data_json,), daemon=True).start()
                                            server_data = {
                                                 "cama": 1,
                                                 "code": qr_code,
                                                 "statusTraza": True,
                                                 "statusJig": False,
                                                 "message": status
                                            }
                                            sio.emit("test-result", [server_data])
                        else:
                            ser.write(b"NG-DB\n")
                            server_data = {
                                "cama": 1,
                                "code": qr_code,
                                "statusTraza": True,
                                "statusJig": False,
                                "message": status
                            }
                            sio.emit("test-result", [server_data])

        except (serial.SerialException, OSError):
        #except Exception as e:
            print("USB DESCONECTADO")
            #print(e)
            try:
                ser.close()
            except:
                pass
            ser = None
        sys.stdout.flush()
        time.sleep(1)

main()
