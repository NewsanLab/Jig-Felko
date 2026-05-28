import board
import neopixel
from adafruit_pixel_framebuf import PixelFramebuffer
import usb_cdc
import time
from digitalio import DigitalInOut, Direction, Pull
import simpleio
import busio
from adafruit_debouncer import Debouncer
from adafruit_ina260 import INA260
import asyncio
import digitalio
import analogio

pixeles = neopixel.NeoPixel(board.NEOPIXEL, 64, brightness=0.1, auto_write=False)
matriz = PixelFramebuffer(pixeles, 8, 8, alternating=False)

buzzer = board.BUZZER

i2c_ina260 = busio.I2C(board.GP17, board.GP16)  # SCL, SDA
ina260 = INA260(i2c_ina260) # default address of INA260 0x40

# Comandos GM65
SOFT_TRIG_ON = b"\x7E\x00\x08\x01\x00\x02\x01\xAB\xCD"

# Comunicacion UART con scanner GM65
gm65_scnr = busio.UART(board.GP4, board.GP5, baudrate = 9600, timeout=0.01)

MAX_TIME_SCAN = 5 # tiempo maximo de escaneo en segundos seteado con hoja de cfg del escaner

waiting_reset = False

# Colors
FAIL_COLOR = 0xff0000
OK_COLOR = 0x33cc00
READY_COLOR = 0x0000ff
CLEAR_COLOR = 0x000000
WHITE_COLOR = 0xffffff
TEST_COLOR = 0xffff00

def crear_boton(boton):
  boton_value = DigitalInOut(boton)
  boton_value.direction = Direction.INPUT
  boton_value.pull = Pull.UP
  return boton_value

def pintar_matriz(color):
    matriz.fill(color)
    matriz.display()

async def task_emergency():
    btn_emergency = analogio.AnalogIn(board.GP27)
    while True:
        if (btn_emergency.value > 10000):
            pintar_matriz(FAIL_COLOR)
            simpleio.tone(buzzer, 440, duration = 0.3)
            await asyncio.sleep(0.2)
        await asyncio.sleep(0.01)  

async def test_felko(qr_code):
    global btnA, command, validacion, status, isFinishTestFM, serial, press, start_led, ina260, waiting_reset, mosfet                                                    
    # al iniciar el test, se apaga el led de inicio para indicar que el test esta en proceso, y se vuelve a prender al finalizar el test
    start_led.value = False
    serial.write(f"#{qr_code}\n".encode('utf-8'))
    await asyncio.sleep(0.2)
    validacion = 1 # variable que se setea en 0 si hay un fallo en la medicion de corriente o tension, y se mantiene en 1 si las mediciones son correctas 
    end_test = False 
    while not end_test:
        if serial.in_waiting > 0: 
            command = serial.readline().decode('utf-8').strip()
            # print("command:", command) 
            if command == "FM-START":
                pintar_matriz(TEST_COLOR) 
                mosfet.value = True
                press.value = True
                await asyncio.sleep(1.25)
                while command not in ("FM-0", "FM-2", "FM-3"):
                    pintar_matriz(TEST_COLOR)
                    voltage = ina260.voltage  # voltage on V- (load side)
                    current = ina260.current  # current in mA
                    print(f"voltage: {voltage} - corriente: {current}")
                    if ((voltage < 7)|(voltage > 15.99)):
                        validacion = 0
                    if (current > 120):
                        validacion = 0
                    if serial.in_waiting > 0:
                        command = serial.readline().decode('utf-8').strip()
                    await asyncio.sleep(0.01)

                if command in ("FM-2", "FM-3"):#FM fail
                    pintar_matriz(FAIL_COLOR)
                    serial.write("FM-END-D\n".encode('utf-8'))
                    simpleio.tone(buzzer, 440, duration = 1.5)
                if command == "FM-0":#OK
                    if validacion == 1:
                        pintar_matriz(OK_COLOR)
                        serial.write("FM-END-C\n".encode('utf-8'))
                    else:#current fail
                        pintar_matriz(FAIL_COLOR)
                        serial.write(f"FM-END-E, {current}\n".encode('utf-8'))
                        simpleio.tone(buzzer, 440, duration = 1.5)

            if command == "AM-START":
                serial.write("AM-RUN\n".encode('utf-8'))
                pintar_matriz(TEST_COLOR)
                while command not in ("AM-0", "AM-1"):
                    voltage = ina260.voltage  # voltage on V- (load side)
                    current = ina260.current  # current in mA
                    if ((voltage < 7)|(voltage > 15.99)):
                        validacion = 0
                    if (current > 120):
                        validacion = 0
                    if serial.in_waiting > 0:
                        command = serial.readline().decode('utf-8').strip()
                    await asyncio.sleep(0.01)

                if command == "AM-1":#AM fail
                    pintar_matriz(FAIL_COLOR)
                    serial.write("AM-END-D\n".encode('utf-8'))
                    simpleio.tone(buzzer, 440, duration = 1.5) 
                    end_test = True
                    press.value = False
                    await asyncio.sleep(1.3)
                    start_led.value = True
                    waiting_reset = True
                if command == "AM-0":#OK
                    if validacion == 1:
                        pintar_matriz(OK_COLOR)
                        serial.write("AM-END-C\n".encode('utf-8'))
                    else:#current fail
                        pintar_matriz(FAIL_COLOR)
                        serial.write(f"AM-END-E, {current}\n".encode('utf-8'))
                        simpleio.tone(buzzer, 440, duration = 1.5)
                    end_test = True
                    press.value = False
                    await asyncio.sleep(1.3)
                    start_led.value = True 
                    waiting_reset = True
            if command == "NG-DB":
                pintar_matriz(FAIL_COLOR)
                simpleio.tone(buzzer, 440, duration = 1.5)
                end_test = True
                press.value = False
                await asyncio.sleep(1.3)
                start_led.value = True
                waiting_reset = True
                


async def task_main():
    global btnA, command, validacion, status, isFinishTestFM, serial, press, start_led, waiting_reset, mosfet

    init_btn_start = crear_boton(board.GP18)
    btn_start = Debouncer(init_btn_start) 
    scanning = False
    buffer_gm65 = b"" 
    start_scan_time = 0
    pintar_matriz(WHITE_COLOR)
    press = digitalio.DigitalInOut(board.GP8)
    press.direction = digitalio.Direction.OUTPUT
    start_led = digitalio.DigitalInOut(board.GP28)
    start_led.direction = digitalio.Direction.OUTPUT
    start_led.value = True
    barrier = digitalio.DigitalInOut(board.GP26) 
    barrier.direction = digitalio.Direction.INPUT
    mosfet = DigitalInOut(board.GP14)
    mosfet.direction = Direction.OUTPUT
    mosfet.value = False 

    btnA = crear_boton(board.A) 
    command = 4
    validacion = 1
    status = 0
    serial = usb_cdc.data if usb_cdc.data else usb_cdc.console
    isFinishTestFM = False
    qr_code = ""
    while True:
        btn_start.update()
        if btn_start.fell and not scanning and not barrier.value:
            if waiting_reset:
                pintar_matriz(WHITE_COLOR)
                waiting_reset = False
            else:
                gm65_scnr.reset_input_buffer()
                gm65_scnr.write(SOFT_TRIG_ON)
                pintar_matriz(READY_COLOR)
                print("scan start")
                scanning = True
                start_scan_time = time.monotonic()
            await asyncio.sleep(0.01)

        if scanning:
            chunk = gm65_scnr.read(32)
            if chunk:
                buffer_gm65 += chunk
            # Inicio de Testeo
            if b"\r" in buffer_gm65:
                # print("HEX:", buffer_gm65.hex(" ")) # cant de bytes en hex
                try:
                    end = buffer_gm65.index(b"\r")
                    raw = buffer_gm65[:end]
                    qr_code = raw[7:].decode() # header = 7 bytes, el codigo empieza a partir del byte 8
                    # print("code qr:", qr_code)
                    await test_felko(qr_code)
                    mosfet.value = False
                except Exception as e:
                    print("error:", e)
                gm65_scnr.reset_input_buffer()
                buffer_gm65 = b""
                scanning = False
            # timeout 5 segundos, si pasa ese tiempo sin recibir el qr, se tiene que volver a presionar el boton para escanear
            elif (time.monotonic() - start_scan_time) > MAX_TIME_SCAN:
                gm65_scnr.reset_input_buffer()
                buffer_gm65 = b""
                scanning = False
                pintar_matriz(WHITE_COLOR)
        await asyncio.sleep(0.01)


async def main():
    await asyncio.gather(
        task_main(),
        task_emergency()
    )

asyncio.run(main())
